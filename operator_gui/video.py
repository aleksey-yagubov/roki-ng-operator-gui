"""Remote stream definitions and shared local receivers, independent of views."""

import time
from urllib.parse import quote

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from .control import scalar
from .video_receiver import Receiver, receiver_description


def video_request(values, source):
    def number(key, low, high, kind="int"):
        return scalar(dict(type=kind, min=low, max=high), values[key])

    settings = source.get("stream_settings", {})
    codec = values["codec"]
    if codec not in settings.get("codecs", []):
        raise ValueError("Кодек не поддерживается источником")
    direct = source["id"] == "direct-gst"
    maximum = settings.get("max_size", [1600, 1300] if direct else [800, 650])
    width, height = number("width", 160, maximum[0]), number("height", 120, maximum[1])
    alignment = settings.get("jpeg_alignment", 8) if codec == "jpeg" else 2
    if width % alignment or height % alignment:
        raise ValueError(f"Размеры должны быть кратны {alignment}")
    low, high = settings.get("max_fps", [1, 120])
    fps = number("fps", low, high, "float")
    result = dict(source=source["id"], output=dict(width=width, height=height, fps=fps),
                  codec=dict(name=codec), mtu=1400)
    if codec == "h264":
        result["codec"]["bitrate"] = number("bitrate", 100000, 20000000)
    if direct:
        sensor = dict(width=number("sensorWidth", 320, 4096),
                      height=number("sensorHeight", 240, 4096), depth=number("depth", 8, 10))
        if sensor["depth"] not in (8, 10) or width > sensor["width"] or height > sensor["height"]:
            raise ValueError("Неверный режим сенсора или выход больше сенсора")
        result["sensor"] = sensor
    else:
        result["max_fps"] = number("max_fps", low, fps, "float")
    return result


class Player(QObject):
    """One decoder per stream. No references to Qt windows or docking items."""
    changed = Signal()
    imageChanged = Signal()

    def __init__(self, manager, ident):
        super().__init__(manager)
        self.manager, self.ident = manager, ident
        self.info, self.media = {}, {}
        self.phase, self.error = "idle", ""
        self.port, self.decoder = 0, ""
        self.intent = "attach"
        self.generation = 0
        self.receiver = None
        self.image = QImage()
        self.image_serial = 0
        self.last_image_at = 0.
        self.changed.connect(manager.changed)
        self.imageChanged.connect(manager.framesChanged)

    @property
    def backend(self):
        return self.info.get("spec", {}).get("source", "")

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(streamId=self.ident, phase=self.phase, error=self.error,
                    source=self.backend, decoder=self.decoder, port=self.port,
                    active=self.phase == "receiving", fps=self.media.get("fps"),
                    size=self.media.get("size", ""), frames=self.media.get("frames", 0),
                    stalled=self.media.get("stalled", False))

    @Slot(object)
    def receive_image(self, image):
        if self.phase not in ("preparing", "joining", "receiving"):
            return
        self.image = image
        self.image_serial += 1
        self.last_image_at = time.monotonic()
        self.imageChanged.emit()

    @Slot(object)
    def status(self, media):
        self.media = media
        self.changed.emit()

    def clear_image(self):
        self.image = QImage()
        self.last_image_at = 0.
        self.media = {}
        self.image_serial += 1
        self.imageChanged.emit()

    def close(self, message=""):
        self.generation += 1
        if self.receiver:
            self.receiver.stop()
        self.phase = "stopped"
        self.error = message
        self.clear_image()
        self.changed.emit()

    def shutdown(self):
        if self.receiver:
            self.receiver.shutdown()


class Streams(QObject):
    changed = Signal()
    framesChanged = Signal()

    def __init__(self, session, control, log, parent=None):
        super().__init__(parent)
        self.session, self.control, self.log = session, control, log
        self.sources, self.streams = [], []
        self.details, self.players = {}, {}
        self.pending = {}
        self.serial = 0
        self.error = ""
        self.last_created = ""
        self.ball_stream = ""
        self.capabilities = {}
        self.watching = False
        self.create_unknown = False
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)
        control.changed.connect(self.changed)
        control.barrierIssued.connect(self.barrier)

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(ballStream=self.ball_stream, sources=self.sources, streams=self.streams,
                    active=[dict(id=k, label=f"{p.backend} · {k}") for k, p in self.players.items()
                            if p.phase == "receiving"],
                    busyKeys=[p[0] for p in self.pending.values()], error=self.error,
                    lastCreated=self.last_created, capabilities=self.capabilities,
                    canManage=self.session.connected and self.control.owns and not self.control.pending,
                    canCreate=self.session.connected and self.control.owns and not self.control.pending
                    and not self.busy("create") and not self.create_unknown,
                    catalogBusy=self.busy("sources") or self.busy("list"))

    def busy(self, key):
        return any(p[0] == key for p in self.pending.values())

    def request(self, op, body, key, success, failure=None):
        if not self.session.connected or self.busy(key):
            return False
        self.serial += 1
        context = f"streams:{self.serial}"
        self.pending[context] = (key, success, failure, op)
        self.session.request(op, body, context)
        self.changed.emit()
        return True

    def problem(self, message):
        self.error = str(message)
        self.log("ERROR", "Стримы: " + self.error)
        self.changed.emit()

    def permitted(self):
        if not self.view["canManage"]:
            self.problem("Нужно получить управление; дождитесь завершения текущей команды.")
            return False
        return True

    def catalog(self, kind, limit):
        if self.busy(kind):
            return
        items = []
        def page(offset=0):
            def received(result):
                items.extend(result["items"])
                cursor = result.get("next_offset")
                if cursor is not None:
                    if cursor <= offset:
                        self.problem("Некорректная пагинация " + kind)
                        return
                    page(cursor)
                else:
                    if kind == "sources":
                        self.sources = items
                    else:
                        self.streams = items
                        # A paginated list can race creation/deletion. Only the
                        # per-stream status poll invalidates an active receiver.
                    self.changed.emit()
            self.request("videostream." + kind, dict(offset=offset, limit=limit), kind, received)
        page()

    @Slot()
    def refresh(self):
        self.error = ""
        self.watching = True
        self.catalog("sources", 1)
        self.catalog("list", 4)
        self.request("videostream.capabilities", {}, "capabilities", self.got_capabilities)

    def got_capabilities(self, result):
        self.capabilities = result
        self.changed.emit()

    @Slot("QVariantMap")
    def create(self, values):
        if not self.permitted() or self.busy("create") or self.create_unknown:
            return
        try:
            source = next(s for s in self.sources if s["id"] == values["source"])
            spec = video_request(values, source)
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            self.problem(str(exc) or "Сначала запросите и выберите источник")
            return
        def created(result):
            self.last_created = result["stream_id"]
            self.remember(result)
            self.catalog("list", 4)
        def failed(reason):
            self.create_unknown = "outcome unknown" in reason
            self.problem(reason + " Обновите список передач перед повторным созданием.")
        self.request("videostream.create", dict(spec, lease_epoch=self.control.lease),
                     "create", created, failed)

    @Slot()
    def acknowledgeUnknownCreate(self):
        # Explicit operator acknowledgement; never silently create a duplicate.
        self.create_unknown = False
        self.changed.emit()

    @Slot(int)
    def showBall(self, port):
        if not self.permitted() or self.busy('create') or self.create_unknown:
            return
        if self.ball_stream:
            self.connectStream(self.ball_stream, port, 'avdec_h264', True)
            return
        def created(result):
            self.ball_stream = result['stream_id']
            self.remember(result)
            self.connectStream(self.ball_stream, port, 'avdec_h264', True)
        def failed(reason):
            self.create_unknown = 'outcome unknown' in reason
            self.problem(reason)
        self.request('videostream.create', dict(source='ball', output=dict(width=800, height=650, fps=30),
                     codec=dict(name='h264', bitrate=2000000), max_fps=15,
                     lease_epoch=self.control.lease), 'create', created, failed)

    def remember(self, result):
        ident = result["stream_id"]
        self.details[ident] = self.details.get(ident, {}) | result
        row = dict(stream_id=ident, source=self.details[ident].get("spec", {}).get("source", ""),
                   **{k: result.get(k) for k in ("state", "run_id", "receivers", "attached")})
        self.streams = [s for s in self.streams if s["stream_id"] != ident]
        if result["state"] != "destroyed":
            self.streams.append(row)
        self.changed.emit()

    @Slot(str, result="QVariantMap")
    def detail(self, ident):
        return self.details.get(ident, {})

    @Slot(str, result="QVariantMap")
    def reception(self, ident):
        p = self.players.get(ident)
        return p.view if p else dict(phase="idle", active=False, error="", frames=0)

    @Slot(str, result=str)
    def imageUrl(self, ident):
        p = self.players.get(ident)
        if p is None or p.phase != "receiving" or p.image.isNull():
            return ""
        return f"image://streams/{quote(ident, safe='')}?frame={p.image_serial}"

    def inspect_result(self, result):
        self.remember(result)
        p = self.players.get(result["stream_id"])
        if p and p.phase == "receiving":
            if result.get("state") not in ("starting", "running") or result.get("attached") is False:
                p.close("Передача остановлена или получатель отключён")
            elif (result.get("run_id"), result.get("ssrc")) != (p.info.get("run_id"), p.info.get("ssrc")):
                p.close("Передача перезапущена. Подключитесь заново.")
                self.detach(p.ident)
            else:
                p.info = result

    @Slot(str)
    def inspect(self, ident):
        if ident:
            self.request("videostream.status", dict(stream_id=ident), ident, self.inspect_result,
                         lambda reason: self.status_failed(ident, reason))

    def status_failed(self, ident, reason):
        if "not_found" in reason and ident in self.players:
            self.players[ident].close(reason)
        self.problem(reason)

    @Slot(str, int, str, bool)
    def connectStream(self, ident, port, decoder, start):
        if not ident or self.busy(ident) or not self.session.connected or (start and not self.permitted()):
            return
        p = self.players.get(ident)
        if p and p.phase in ("inspecting", "preparing", "joining", "receiving", "detaching"):
            return
        if not 1024 <= port <= 65535 or any(q.ident != ident and q.port == port
                and q.phase in ("inspecting", "preparing", "joining", "receiving", "detaching") for q in self.players.values()):
            self.problem("UDP-порт недопустим или занят другим приёмником")
            return
        if p is None:
            p = self.players[ident] = Player(self, ident)
        p.generation += 1
        generation = p.generation
        p.phase, p.error = "inspecting", ""
        p.port, p.decoder, p.intent = port, decoder, "start" if start else "attach"
        p.clear_image()
        def inspected(result):
            if generation != p.generation:
                return
            self.remember(result)
            if not start and result["state"] not in ("starting", "running"):
                p.close("Наблюдатель может подключиться только к запущенной передаче")
                return
            p.info = result
            info = dict(result, rtp_port=port)
            if start and result["state"] not in ("starting", "running"):
                info["ssrc"] = None
            try:
                receiver_description(info, decoder, 30)
                if p.receiver is None:
                    p.receiver = Receiver(p)
                    p.receiver.imageReady.connect(p.receive_image)
                    p.receiver.status.connect(p.status)
                    p.receiver.ready.connect(lambda: self.receiver_ready(p))
                    p.receiver.error.connect(lambda msg: self.receiver_error(p, msg))
                    p.receiver.log.connect(self.log)
                p.phase = "preparing"
                p.receiver.prepare()
                p.receiver.start(info, decoder, 30)
            except Exception as exc:
                self.receiver_error(p, str(exc))
            p.changed.emit()
        self.request("videostream.status", dict(stream_id=ident), ident, inspected, p.close)
        p.changed.emit()

    def receiver_ready(self, p):
        if p.phase != "preparing":
            return
        if not self.session.connected or (p.intent == "start" and not self.control.owns):
            p.close("Управление потеряно до запуска")
            return
        generation = p.generation
        body = dict(stream_id=p.ident, rtp_port=p.port)
        if p.intent == "start":
            body["lease_epoch"] = self.control.lease
        p.phase = "joining"
        def joined(result):
            if generation != p.generation:
                self.detach(p.ident)
                return
            self.remember(result)
            p.info = result
            if result["state"] in ("starting", "running"):
                p.phase = "receiving"
            else:
                p.close(result.get("error") or "Передача не запущена")
            p.changed.emit()
        def failed(reason):
            p.close(reason)
            self.detach(p.ident)
        self.request("videostream." + p.intent, body, p.ident, joined, failed)
        p.changed.emit()

    def receiver_error(self, p, message):
        p.close(message)
        self.problem(message)
        if not self.busy(p.ident):
            self.detach(p.ident)

    @Slot(str)
    def detach(self, ident):
        if self.busy(ident):
            return
        p = self.players.get(ident)
        if p:
            p.close(p.error)
            p.phase = "detaching"
        def done(result):
            self.remember(result)
            if p:
                p.phase = "stopped"
                p.changed.emit()
        def failed(reason):
            if p:
                p.close(reason)
            self.problem(reason)
        if not self.request("videostream.detach", dict(stream_id=ident), ident, done, failed) and p:
            p.close(p.error)

    @Slot(str, str)
    def manage(self, ident, action):
        if action not in ("stop", "destroy") or not self.permitted():
            return
        def done(result):
            self.remember(result)
            if ident in self.players:
                self.players[ident].close("Передача остановлена" if action == "stop" else "Передача удалена")
            self.catalog("list", 4)
        self.request("videostream." + action, dict(stream_id=ident, lease_epoch=self.control.lease),
                     ident, done)

    @Slot(str, str, float)
    def update(self, ident, key, value):
        if key not in ("max_fps", "bitrate") or not self.permitted():
            return
        try:
            value = scalar(dict(type="int" if key == "bitrate" else "float",
                                min=100000 if key == "bitrate" else 1,
                                max=20000000 if key == "bitrate" else 120), value)
        except ValueError as exc:
            self.problem(exc)
            return
        self.request("videostream.update", dict(stream_id=ident, lease_epoch=self.control.lease, **{key: value}),
                     ident, self.inspect_result)

    def poll(self):
        if not self.session.connected:
            return
        if self.watching:
            self.catalog("list", 4)
        for ident, p in self.players.items():
            if p.phase == "receiving":
                self.inspect(ident)

    def response(self, op, result, context):
        pending = self.pending.pop(context, None)
        if pending:
            pending[1](result)
            self.changed.emit()

    def failed(self, op, reason, context):
        pending = self.pending.pop(context, None)
        if pending:
            (pending[2] or self.problem)(reason)
            self.changed.emit()

    def barrier(self):
        # Transport.interrupt retires queued requests. Reconcile rather than replay.
        if self.busy("create"):
            self.create_unknown = True
        self.pending.clear()
        for p in self.players.values():
            if p.phase in ("inspecting", "preparing", "joining", "detaching"):
                p.close("Запрос прерван. Проверьте статус и отключите приёмник перед повтором.")
        self.changed.emit()

    def connection(self):
        if not self.session.connected:
            self.ball_stream = ''
        if not self.session.connected:
            self.pending.clear()
            self.sources, self.streams, self.details = [], [], {}
            self.last_created = ""
            self.watching = False
            self.create_unknown = False
            self.capabilities = {}
            for p in self.players.values():
                p.close("Нет связи")
        self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        for p in self.players.values():
            p.shutdown()
