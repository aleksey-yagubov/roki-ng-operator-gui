"""GStreamer receiver, isolated from the control socket and the Qt GUI thread."""

import socket
import time
import threading

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage


def receiver_description(info, decoder, latency):
    codec = info["encoding_name"]
    choices = {"H264": ("vah264dec", "avdec_h264"), "JPEG": ("vajpegdec", "jpegdec")}
    if codec not in choices or decoder not in choices[codec]:
        raise ValueError("Декодер не соответствует кодеку")
    pt = int(info["payload_type"])
    ssrc = info.get("ssrc")
    if ssrc is not None: ssrc = int(ssrc)
    if not 0 <= pt <= 127 or (ssrc is not None and not 0 <= ssrc < 2**32) or not 0 <= latency <= 1000:
        raise ValueError("Некорректные параметры RTP")
    ssrc_caps = f",ssrc=(uint){ssrc}" if ssrc is not None else ""
    depay, parse = ("rtph264depay", "h264parse") if codec == "H264" else ("rtpjpegdepay", "jpegparse")
    tail = ("videoconvert ! video/x-raw,format=RGBA ! appsink name=frames "
            "sync=false max-buffers=1 drop=true emit-signals=true")
    return (f'udpsrc name=network close-socket=false caps="application/x-rtp,media=video,'
            f'encoding-name={codec},payload=(int){pt},clock-rate=(int)90000{ssrc_caps}" '
            f'! rtpjitterbuffer latency={latency} drop-on-latency=true '
            f'! {depay} ! {parse} ! {decoder} name=decoder ! {tail}')


class MediaWorker(QObject):
    ready = Signal()
    stopped = Signal()
    error = Signal(str)
    status = Signal(object)
    log = Signal(str, str)
    frameReady = Signal()

    def __init__(self):
        super().__init__()
        self.pipeline = self.socket = self.timer = None
        self.Gst = None
        self.last_frames = 0
        self.last_frame_at = 0
        self.lock = threading.Lock()
        self.image = None
        self.notified = False
        self.copied = 0
        self.fps = None
        self.rate_at = self.rate_frames = 0

    def take_image(self):
        with self.lock:
            image, self.image = self.image, None
            self.notified = False
        return image

    def sample(self, sink):
        Gst = self.Gst
        sample = sink.emit("pull-sample")
        if sample is None:
            return Gst.FlowReturn.EOS
        try:
            info = self.GstVideo.VideoInfo.new_from_caps(sample.get_caps())
            buffer = sample.get_buffer()
            meta = self.GstVideo.buffer_get_video_meta(buffer)
            stride = meta.stride[0] if meta else info.stride[0]
            offset = meta.offset[0] if meta else info.offset[0]
            ok, mapping = buffer.map(Gst.MapFlags.READ)
            if not ok:
                raise RuntimeError("Не удалось прочитать видеобуфер")
            try:
                image = QImage(mapping.data[offset:], info.width, info.height, stride,
                               QImage.Format.Format_RGBA8888).copy()
            finally:
                buffer.unmap(mapping)
            with self.lock:
                self.image = image
                self.copied += 1
                notify = not self.notified
                self.notified = True
            if notify:
                self.frameReady.emit()
            return Gst.FlowReturn.OK
        except Exception as exc:
            self.error.emit(str(exc))
            return Gst.FlowReturn.ERROR

    @Slot(object)
    def start(self, settings):
        try:
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstVideo", "1.0")
            from gi.repository import Gst, Gio, GstVideo
            Gst.init(None)
            self.Gst = Gst
            self.GstVideo = GstVideo
            self.copied = 0
            info = settings["info"]
            launch = receiver_description(info, settings["decoder"], settings["latency"])
            self.log.emit("INFO", "Video receiver: " + launch)
            self.pipeline = Gst.parse_launch(launch)
            self.pipeline.get_by_name("frames").connect("new-sample", self.sample)
            # Own a non-reusable UDP port: another player must not steal packets.
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.bind(("0.0.0.0", info["rtp_port"]))
                self.socket = Gio.Socket.new_from_fd(sock.detach())
            self.pipeline.get_by_name("network").set_property("socket", self.socket)
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("GStreamer отказался запустить приёмник")
            self.last_frames = 0
            self.last_frame_at = time.monotonic()
            self.fps = None
            self.rate_at, self.rate_frames = self.last_frame_at, 0
            self.timer = QTimer(self)
            self.timer.setInterval(100)
            self.timer.timeout.connect(self.poll)
            self.timer.start()
            self.ready.emit()
        except Exception as exc:
            self.error.emit(str(exc))
            self.stop()

    @Slot()
    def poll(self):
        if self.pipeline is None:
            return
        Gst = self.Gst
        for _ in range(32):
            msg = self.pipeline.get_bus().pop()
            if msg is None:
                break
            if msg.type in (Gst.MessageType.ERROR, Gst.MessageType.EOS):
                reason = str(msg.parse_error()) if msg.type == Gst.MessageType.ERROR else "Конец видеопотока"
                self.error.emit(reason)
                self.stop()
                return
            if msg.type == Gst.MessageType.WARNING:
                self.log.emit("WARNING", str(msg.parse_warning()))
        caps = self.pipeline.get_by_name("decoder").get_static_pad("src").get_current_caps()
        sink = self.pipeline.get_by_name("frames")
        frames = sink.get_property("stats").get_value("rendered") or 0
        now = time.monotonic()
        elapsed = now - self.rate_at
        if elapsed >= 0.5:
            self.fps = max(0, frames - self.rate_frames) / elapsed
            self.rate_at, self.rate_frames = now, frames
        if frames != self.last_frames:
            self.last_frame_at = time.monotonic()
            self.last_frames = frames
        size = ""
        if caps and not caps.is_empty():
            structure = caps.get_structure(0)
            size = f"{structure.get_value('width')}x{structure.get_value('height')}"
        self.status.emit(dict(frames=frames, fps=self.fps, size=size, stalled=now - self.last_frame_at > 3))

    @Slot()
    def stop(self):
        if self.timer:
            self.timer.stop()
            self.timer.deleteLater()
            self.timer = None
        if self.pipeline is not None:
            self.pipeline.set_state(self.Gst.State.NULL)
            self.pipeline = None
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.take_image()
        self.stopped.emit()


class Receiver(QObject):
    ready = Signal()
    stopped = Signal()
    error = Signal(str)
    status = Signal(object)
    imageReady = Signal(object)
    log = Signal(str, str)
    startRequested = Signal(object)
    stopRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread = None
        self.Gst = None

    def prepare(self):
        if self.thread is None:
            self.thread = QThread(self)
            self.thread.setObjectName("operator-video")
            self.worker = MediaWorker()
            self.worker.moveToThread(self.thread)
            self.worker.frameReady.connect(self.deliver_image)
            self.startRequested.connect(self.worker.start)
            self.stopRequested.connect(self.worker.stop)
            for name in ("ready", "stopped", "error", "status", "log"):
                getattr(self.worker, name).connect(getattr(self, name))
            self.thread.finished.connect(self.worker.deleteLater)
            self.thread.start()

    def start(self, info, decoder, latency):
        self.startRequested.emit(dict(info=info, decoder=decoder, latency=latency))

    @Slot()
    def deliver_image(self):
        image = self.worker.take_image()
        if image is not None:
            self.imageReady.emit(image)

    def stop(self):
        if self.thread:
            self.stopRequested.emit()
        else:
            self.stopped.emit()

    def shutdown(self):
        if self.thread and self.thread.isRunning():
            from PySide6.QtCore import QMetaObject, Qt
            QMetaObject.invokeMethod(self.worker, "stop", Qt.ConnectionType.BlockingQueuedConnection)
            self.thread.quit()
            self.thread.wait()
