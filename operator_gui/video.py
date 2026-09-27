"""Explicit direct-gst video session; never starts hardware on connection."""

import json
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, Qt
from PySide6.QtGui import QImage

from .control import scalar
from .video_receiver import Receiver


def video_request(values):
    def integer(key, lo, hi):
        return scalar({"type": "int", "min": lo, "max": hi}, values[key])
    codec = values["codec"]
    if codec not in ("h264", "jpeg"):
        raise ValueError("Неизвестный кодек")
    sw, sh = integer("sensorWidth", 320, 4096), integer("sensorHeight", 240, 4096)
    width, height = integer("width", 160, 1600), integer("height", 120, 1300)
    depth = integer("depth", 8, 10)
    if depth not in (8, 10) or width > sw or height > sh or width % 2 or height % 2:
        raise ValueError("RAW8/RAW10; выход должен быть чётным и не больше сенсора")
    if codec == "jpeg" and (width % 8 or height % 8):
        raise ValueError("Для RTP/JPEG обе стороны кратны 8, например 800x648")
    encoding = {"name": codec}
    if codec == "h264":
        encoding["bitrate"] = integer("bitrate", 100000, 20000000)
    return dict(backend="direct-gst", sensor=dict(width=sw, height=sh, depth=depth),
                output=dict(width=width, height=height, fps=scalar({"type": "float", "min": 1, "max": 120}, values["fps"])),
                codec=encoding, destination=dict(rtp_port=integer("port", 1024, 65535)), mtu=1400)


class Video(QObject):
    changed = Signal()
    showWindow = Signal()
    hideWindow = Signal()
    imageChanged = Signal()

    def __init__(self, session, control, log, parent=None, receiver=None):
        super().__init__(parent)
        self.session, self.control, self.log = session, control, log
        self.receiver = receiver or Receiver(self)
        self.info = {}
        self.pending = ""
        self.error = ""
        self.phase = "idle"
        self.capabilities = {}
        self.media = {}
        self.item = None
        self.render_window = None
        self.cancelled = False
        self.local_busy = False
        self.unknown_create = False
        self.hide_on_stop = False
        self.decoder = "vah264dec"
        self.latency = 30
        self.output = "image"
        self.image = QImage()
        self.image_serial = 0
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)
        control.changed.connect(self.changed.emit)
        control.barrierIssued.connect(self.barrier)
        self.receiver.ready.connect(self.local_ready)
        self.receiver.stopped.connect(self.local_stopped)
        self.receiver.error.connect(self.media_error)
        self.receiver.status.connect(self.media_status)
        self.receiver.log.connect(log)
        self.receiver.imageReady.connect(self.receive_image)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refresh)

    @Property("QVariantMap", notify=changed)
    def view(self):
        reason = self.start_blocked_reason
        sensor = self.capabilities.get("sensor_default", {})
        output = self.capabilities.get("output_default", {})
        summary = ("Кодеки: " + ", ".join(self.capabilities.get("codecs", []))
                   + f". По умолчанию: сенсор {sensor.get('width', '?')}x{sensor.get('height', '?')} RAW{sensor.get('depth', '?')}; "
                   + f"выход {output.get('width', '?')}x{output.get('height', '?')}, {output.get('fps', '?')} FPS."
                   if self.capabilities else "Возможности ещё не запрошены.")
        return dict(phase=self.phase, error=self.error, pending=self.pending,
                    sink=self.output,
                    canStart=not reason, startBlockedReason=reason,
                    canEditSettings=not self.info and not self.local_busy and not self.unknown_create
                    and self.pending in ("", "video.capabilities"),
                    capabilitiesSummary=summary,
                    canStop=bool(self.info or self.pending or self.local_busy),
                    streamId=self.info.get("stream_id", ""),
                    remoteState=self.info.get("state", "-"), frames=self.media.get("frames", 0),
                    fps=self.media.get("fps"),
                    size=self.media.get("size", ""), stalled=self.media.get("stalled", False),
                    capabilities=json.dumps(self.capabilities, ensure_ascii=False, indent=2))

    @property
    def start_blocked_reason(self):
        if not self.session.connected:
            return "Подключитесь к роботу. Настройки видео можно заполнить заранее."
        if not self.control.owns:
            return "Нажмите «Получить управление» в верхней панели."
        if self.control.pending:
            return "Ожидается ответ: " + self.control.pending
        if self.control.mode != "MANUAL":
            return "Для запуска видео включите ручной режим (MANUAL)."
        if self.unknown_create:
            return "Исход создания потока неизвестен. Переподключитесь для очистки сессии."
        if self.pending:
            return "Ожидается ответ: " + self.pending
        if self.info or self.local_busy:
            return "Перед изменением настроек остановите текущий поток."
        return ""

    @Property(int, notify=imageChanged)
    def imageSerial(self):
        return self.image_serial

    @Slot(object)
    def receive_image(self, image):
        self.image = image
        self.image_serial += 1
        self.imageChanged.emit()

    def request(self, op, body=None):
        self.pending = op
        self.session.request(op, body or {}, "video")
        self.changed.emit()

    @Slot()
    def getCapabilities(self):
        if self.session.connected and not self.pending:
            self.request("video.capabilities")

    @Slot("QVariantMap")
    def start(self, values):
        if not self.view["canStart"]:
            return
        try:
            spec = video_request(values)
            self.decoder = values["decoder"]
            from .video_receiver import receiver_description
            output = values.get("sink", "image")
            receiver_description(dict(encoding_name=spec["codec"]["name"].upper(), payload_type=96, ssrc=0), self.decoder, 30, output)
            self.receiver.prepare(output)
            self.output = output
            self.cancelled = False
            self.media = {}
            self.error = ""
            self.phase = "creating"
            self.request("video.create", dict(spec, lease_epoch=self.control.lease))
        except Exception as exc:
            self.local_error(str(exc))

    @Slot(QObject)
    def attach(self, item):
        self.item = item
        window = item.window()
        if window is None:
            item.windowChanged.connect(lambda _window: self.attach(item))
        elif self.output == "gl":
            self.disconnect_render()
            self.render_window = window
            # A dynamically loaded Gst item needs its first render too, even if
            # the surrounding window's scene graph already existed.
            window.afterRendering.connect(self.surface_ready, Qt.ConnectionType.QueuedConnection)
            window.update()
        else:
            self.surface_ready()

    def disconnect_render(self):
        if self.render_window is not None:
            self.render_window.afterRendering.disconnect(self.surface_ready)
            self.render_window = None

    @Slot()
    def surface_ready(self):
        if self.phase != "receiver" or self.cancelled or self.local_busy:
            return
        if not self.item or not self.item.window() or (self.output == "gl" and not self.item.window().isSceneGraphInitialized()):
            return
        try:
            self.disconnect_render()
            self.local_busy = True
            self.receiver.start(self.item, self.info, self.decoder, self.latency)
        except Exception as exc:
            self.local_error(str(exc))
            self.receiver.stop()

    @Slot()
    def local_ready(self):
        if self.cancelled or not self.session.connected or not self.control.owns:
            self.stop()
        else:
            self.phase = "starting"
            self.request("video.start", dict(stream_id=self.info["stream_id"], lease_epoch=self.control.lease))

    @Slot()
    def stop(self):
        self.disconnect_render()
        self.cancelled = True
        self.timer.stop()
        self.receiver.stop()
        if self.info and not self.pending and self.session.connected:
            self.phase = "stopping"
            self.request("video.destroy", {"stream_id": self.info["stream_id"]})
        elif not self.info and not self.pending:
            self.phase = "idle"
        self.changed.emit()

    @Slot()
    def local_stopped(self):
        self.local_busy = False
        self.receiver.detach()
        if self.hide_on_stop:
            self.hide_on_stop = False
            self.hideWindow.emit()
        self.changed.emit()

    @Slot()
    def closeWindow(self):
        self.hide_on_stop = True
        self.stop()

    @Slot(str)
    def media_error(self, message):
        self.local_error(message)
        self.stop()

    @Slot(str)
    def local_error(self, message):
        self.error = message
        self.phase = "failed"
        self.log("ERROR", "Видео: " + message)
        self.changed.emit()

    @Slot(object)
    def media_status(self, status):
        self.media = status
        self.changed.emit()

    @Slot()
    def refresh(self):
        if self.info and not self.pending and self.session.connected:
            self.request("video.status", {"stream_id": self.info["stream_id"]})

    @Slot(str, object, str)
    def response(self, op, result, context):
        if context != "video":
            return
        self.pending = ""
        if op == "video.capabilities":
            self.capabilities = result
            self.log("INFO", "Получены возможности видео: " + self.view["capabilitiesSummary"])
        elif op == "video.destroy":
            self.info = {}
            self.phase = "idle"
            self.timer.stop()
        else:
            self.info = result
            if op == "video.create" and not self.cancelled:
                self.phase = "receiver"
                self.showWindow.emit()
                if self.item and not self.local_busy:
                    self.attach(self.item)
            elif op in ("video.start", "video.status"):
                self.phase = result.get("state", "unknown")
                self.timer.start()
                if result.get("error"):
                    self.local_error(result["error"])
        if self.cancelled and self.info:
            self.stop()
        self.changed.emit()

    @Slot(str, str, str)
    def failed(self, op, reason, context):
        if context != "video":
            return
        self.pending = ""
        self.local_error(f"{op}: {reason}")
        # Do not blindly retry an ambiguous mutation with a new ID.
        self.timer.stop()
        self.receiver.stop()
        if op == "video.create":
            self.unknown_create = "timeout" in reason.lower()
            self.error += " Если ответ потерян, закройте сессию для удаления неизвестного stream_id."
        self.changed.emit()

    @Slot()
    def connection(self):
        if not self.session.connected:
            self.cancelled = True
            self.pending = ""
            self.info = {}
            self.unknown_create = False
            self.timer.stop()
            self.receiver.stop()
            self.phase = "idle"
        self.changed.emit()

    @Slot()
    def barrier(self):
        if self.pending:
            if self.pending == "video.create":
                self.unknown_create = True
            self.pending = ""
            self.local_error("Запрос видео прерван командой управления; проверьте статус или остановите видео.")
            self.receiver.stop()
            self.changed.emit()

    def shutdown(self):
        self.disconnect_render()
        self.timer.stop()
        self.receiver.shutdown()
