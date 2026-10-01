"""Explicit direct-gst video session; never starts hardware on connection."""

import json
import sys
import time
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from .control import scalar
from .video_receiver import Receiver


def video_request(values):
    def integer(key, lo, hi):
        return scalar({"type": "int", "min": lo, "max": hi}, values[key])
    codec = values["codec"]
    if codec not in ("h264", "jpeg"):
        raise ValueError("Неизвестный кодек")
    backend=values.get('backend','direct-gst')
    if backend not in ('direct-gst','runtime','localisation'):raise ValueError('Неизвестный источник видео')
    sw,sh=(1600,1300) if backend in ('runtime','localisation') else (integer("sensorWidth",320,4096),integer("sensorHeight",240,4096))
    width, height = integer("width", 160, 1600), integer("height", 120, 1300)
    depth = 10 if backend in ('runtime','localisation') else integer("depth",8,10)
    if depth not in (8, 10) or width > sw or height > sh or width % 2 or height % 2:
        raise ValueError("RAW8/RAW10; выход должен быть чётным и не больше сенсора")
    if codec == "jpeg" and (width % 8 or height % 8):
        raise ValueError("Для RTP/JPEG обе стороны кратны 8, например 800x648")
    encoding = {"name": codec}
    if codec == "h264":
        encoding["bitrate"] = integer("bitrate", 100000, 20000000)
    if backend in ('runtime','localisation') and (width>800 or height>650):raise ValueError('Runtime: максимум 800×650')
    integer("port", 1024, 65535)
    result=dict(source=backend,
                output=dict(width=width, height=height, fps=scalar({"type": "float", "min": 1, "max": 120}, values["fps"])),
                codec=encoding, mtu=1400)
    if backend=='direct-gst':result['sensor']=dict(width=sw,height=sh,depth=depth)
    return result


class Video(QObject):
    changed = Signal()
    showWindow = Signal()
    hideWindow = Signal()
    imageChanged = Signal()

    def __init__(self, session, control, log, parent=None, receiver=None, context="video"):
        super().__init__(parent)
        self.session, self.control, self.log = session, control, log
        self.context = context
        self.receiver = receiver or Receiver(self)
        self.info = {}
        self.pending = ""
        self.error = ""
        self.phase = "idle"
        self.capabilities = {}
        self.media = {}
        self.item = None
        self.cancelled = False
        self.local_busy = False
        self.unknown_create = False
        self.hide_on_stop = False
        self.decoder = "avdec_h264" if sys.platform == "darwin" else "vah264dec"
        self.latency = 30
        self.image = QImage()
        self.image_serial = 0
        self.last_image_at = 0.
        self.backend = 'direct-gst'
        self.port = 5004
        self.observing = False
        self.sources = []
        self.streams = []
        self.catalog_pending = set()
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
        return dict(phase=self.phase, error=self.error, pending=self.pending,backend=self.backend,
                    sources=self.sources, streams=self.streams,
                    catalogBusy=bool(self.catalog_pending),
                    canStart=not reason, startBlockedReason=reason,
                    canEditSettings=not self.info and not self.local_busy and not self.unknown_create
                    and self.pending in ("", "videostream.capabilities"),
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
        if self.unknown_create:
            return "Исход создания потока неизвестен. Переподключитесь для очистки сессии."
        if self.pending:
            return "Ожидается ответ: " + self.pending
        if self.info or self.local_busy:
            return "Перед изменением настроек остановите текущий поток."
        return ""

    @Property(bool, notify=imageChanged)
    def hasImage(self):
        return not self.image.isNull()

    @Property(int, notify=imageChanged)
    def imageSerial(self):
        return self.image_serial

    @Slot(object)
    def receive_image(self, image):
        self.image = image
        self.last_image_at=time.monotonic()
        self.image_serial += 1
        self.imageChanged.emit()

    def request(self, op, body=None):
        self.pending = op
        self.session.request(op, body or {}, self.context)
        self.changed.emit()

    @Slot()
    def getCapabilities(self):
        if self.session.connected and not self.pending:
            self.request("videostream.capabilities")

    @Slot()
    def getCatalogs(self):
        if not self.session.connected or self.catalog_pending:
            return
        self.sources, self.streams = [], []
        for kind, limit in (("sources", 1), ("list", 4)):
            self.catalog_pending.add(kind)
            self.session.request("videostream." + kind, {"offset": 0, "limit": limit}, self.context + ":" + kind)
        self.changed.emit()

    @Slot(str, int, str)
    def watchStream(self, stream_id, port, decoder):
        if not self.session.connected or self.pending or self.info or self.local_busy:
            return
        if not 1024 <= port <= 65535:
            self.local_error("Некорректный UDP-порт")
            return
        self.observing = True
        self.cancelled = False
        self.port, self.decoder = port, decoder
        self.phase = "inspecting"
        self.request("videostream.status", {"stream_id": stream_id})

    @Slot(str, int, str)
    def restartStream(self, stream_id, port, decoder):
        if not self.control.owns or self.control.pending:
            return
        self.watchStream(stream_id, port, decoder)
        if self.phase == 'inspecting':
            self.observing = False

    @Slot(str)
    def destroyStream(self, stream_id):
        if self.control.owns and not self.pending and not self.info:
            self.request('videostream.destroy', {'stream_id':stream_id, 'lease_epoch':self.control.lease})

    @Slot()
    def stopTransmission(self):
        if self.info and self.control.owns and not self.pending:
            self.request("videostream.stop", {"stream_id": self.info["stream_id"], "lease_epoch": self.control.lease})

    @Slot(float)
    def updateFps(self, fps):
        if self.info and self.control.owns and not self.pending:
            self.request("videostream.update", {"stream_id": self.info["stream_id"], "max_fps": fps, "lease_epoch": self.control.lease})

    @Slot("QVariantMap")
    def start(self, values):
        if not self.view["canStart"]:
            return
        try:
            spec = video_request(values)
            self.backend=spec['source']
            self.observing = False
            self.port=int(values['port'])
            self.image=QImage();self.last_image_at=0.;self.image_serial+=1;self.imageChanged.emit()
            self.decoder = values["decoder"]
            from .video_receiver import receiver_description
            receiver_description(dict(encoding_name=spec["codec"]["name"].upper(), payload_type=96, ssrc=0), self.decoder, 30)
            self.receiver.prepare()
            self.cancelled = False
            self.media = {}
            self.error = ""
            self.phase = "creating"
            self.request("videostream.create", dict(spec, lease_epoch=self.control.lease))
        except Exception as exc:
            self.local_error(str(exc))

    @Slot()
    def startLocalisation(self):
        self.start(dict(backend='localisation',width=800,height=650,fps=30,
                        codec='h264',bitrate=2000000,port=5006,decoder='avdec_h264'))

    @Slot(QObject)
    def attach(self, item):
        self.item = item
        window = item.window()
        if window is None:
            item.windowChanged.connect(lambda _window: self.attach(item))
        else:
            self.surface_ready()

    @Slot()
    def surface_ready(self):
        if self.phase != "receiver" or self.cancelled or self.local_busy:
            return
        if not self.item or not self.item.window():
            return
        try:
            self.local_busy = True
            self.receiver.start(dict(self.info, rtp_port=self.port), self.decoder, self.latency)
        except Exception as exc:
            self.local_error(str(exc))
            self.receiver.stop()

    @Slot()
    def local_ready(self):
        if self.cancelled or not self.session.connected or (not self.observing and not self.control.owns):
            self.stop()
        else:
            self.phase = "starting"
            body = dict(stream_id=self.info["stream_id"], rtp_port=self.port)
            if not self.observing:
                body['lease_epoch'] = self.control.lease
            self.request("videostream.attach" if self.observing else "videostream.start", body)

    @Slot()
    def stop(self):
        self.cancelled = True
        self.timer.stop()
        self.receiver.stop()
        if self.info and not self.pending and self.session.connected:
            self.phase = "stopping"
            self.request("videostream.detach", {"stream_id": self.info["stream_id"]})
        elif not self.info and not self.pending:
            self.phase = "idle"
        self.changed.emit()

    @Slot()
    def local_stopped(self):
        self.local_busy = False
        if self.hide_on_stop:
            self.hide_on_stop = False
            self.hideWindow.emit()
        self.changed.emit()

    @Slot()
    def closeWindow(self):
        self.hideWindow.emit()

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
            self.request("videostream.status", {"stream_id": self.info["stream_id"]})

    @Slot(str, object, str)
    def response(self, op, result, context):
        if context in (self.context + ":sources", self.context + ":list"):
            kind = context.split(":")[-1]
            target = self.sources if kind == "sources" else self.streams
            target.extend(result['items'])
            if result.get('next_offset') is not None:
                self.session.request(op, {'offset': result['next_offset'], 'limit': 1 if kind == 'sources' else 4}, context)
            else:
                self.catalog_pending.discard(kind)
            self.changed.emit()
            return
        if context != self.context:
            return
        self.pending = ""
        if op == "videostream.capabilities":
            self.capabilities = result
            self.log("INFO", "Получены возможности видео: " + self.view["capabilitiesSummary"])
        elif op in ("videostream.detach", "videostream.destroy"):
            self.info = {}
            self.phase = "idle"
            self.timer.stop()
        else:
            previous_run = self.info.get('run_id')
            inspecting = self.phase == 'inspecting'
            self.info = result
            if inspecting and self.observing and result.get('state') not in ('starting', 'running'):
                self.info = {}
                self.local_error('Передача не запущена. Наблюдатель может подключиться только к активной передаче.')
                return
            if (op == "videostream.create" or inspecting) and not self.cancelled:
                if not self.observing and result.get('state') not in ('starting', 'running'):
                    self.info = dict(result, ssrc=None, run_id=None)
                self.backend = result['spec']['source']
                self.phase = "receiver"
                self.showWindow.emit()
                if self.item and not self.local_busy:
                    self.attach(self.item)
            elif op in ("videostream.start", "videostream.attach", "videostream.status", "videostream.stop", "videostream.update"):
                self.phase = result.get("state", "unknown")
                self.timer.start()
                if previous_run and result.get('run_id') != previous_run and op == 'videostream.status':
                    self.local_error('Передача перезапущена. Подключитесь заново для очистки очереди видео.')
                    self.stop()
                    return
                if result.get('state') in ('stopped', 'failed'):
                    self.local_error('Поток остановлен на роботе. Проверьте камеру и локализацию, затем запустите видео снова.')
                    self.stop()
                    return
                if result.get("error"):
                    self.local_error(result["error"])
        if self.cancelled and self.info:
            self.stop()
        self.changed.emit()

    @Slot(str, str, str)
    def failed(self, op, reason, context):
        if context in (self.context + ":sources", self.context + ":list"):
            self.catalog_pending.discard(context.split(":")[-1])
            self.local_error(reason)
            return
        if context != self.context:
            return
        self.pending = ""
        self.local_error(f"{op}: {reason}")
        # Do not blindly retry an ambiguous mutation with a new ID.
        self.timer.stop()
        self.receiver.stop()
        if op == "videostream.create":
            self.unknown_create = "timeout" in reason.lower()
            self.error += " Если ответ потерян, проверьте список передач: определение может сохраниться."
        self.changed.emit()

    @Slot()
    def connection(self):
        if not self.session.connected:
            self.catalog_pending.clear()
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
            if self.pending not in ('videostream.create', 'videostream.start'):
                self.pending = ''
                if self.info:
                    self.timer.start()
                self.changed.emit()
                return
            if self.pending == "videostream.create":
                self.unknown_create = True
            self.pending = ""
            self.local_error("Запрос видео прерван командой управления; проверьте статус или остановите видео.")
            self.receiver.stop()
            self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        self.receiver.shutdown()
