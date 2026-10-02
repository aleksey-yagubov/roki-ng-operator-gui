"""Named worker outputs and shared H.264 receivers; views never own subscriptions."""
import time
from urllib.parse import quote
from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from .control import scalar
from .video_receiver import Receiver, receiver_description

RUNNING = ("starting", "running")
TRANSITIONAL = ("inspecting", "preparing", "joining", "reconciling")


def setting_value(meta, value):
    typed = scalar({k: v for k, v in meta.items() if k != "choices"}, value)
    if "choices" in meta and typed not in meta["choices"]:
        raise ValueError("Выберите значение из списка")
    return typed


class Player(QObject):
    changed = Signal()
    imageChanged = Signal()

    def __init__(self, manager, name):
        super().__init__(manager)
        self.manager, self.ident = manager, name
        self.info, self.media = {}, {}
        self.phase, self.error = "idle", ""
        self.port, self.decoder = 0, ""
        self.generation = 0
        self.receiver = None
        self.stopping = False
        self.image = QImage()
        self.image_serial = 0
        self.last_image_at = 0.
        self.changed.connect(manager.changed)
        self.imageChanged.connect(manager.framesChanged)

    @property
    def backend(self):
        return self.ident

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(name=self.ident, phase=self.phase, error=self.error,
                    source=self.ident, decoder=self.decoder, port=self.port,
                    active=self.phase == "receiving", stopping=self.stopping, fps=self.media.get("fps"),
                    size=self.media.get("size", ""), frames=self.media.get("frames", 0),
                    stalled=self.media.get("stalled", False))

    @Slot(object)
    def receive_image(self, image):
        if self.phase not in ("preparing", "joining", "reconciling", "receiving"):
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
        self.phase, self.error = "stopped", message
        if self.receiver:
            self.stopping = True
            self.receiver.stop()
        self.clear_image()
        self.changed.emit()

    @Slot()
    def receiver_stopped(self):
        self.stopping = False
        self.changed.emit()

    def shutdown(self):
        if self.receiver:
            self.receiver.shutdown()


class Streams(QObject):
    changed = Signal()
    framesChanged = Signal()
    outputsChanged = Signal()
    receiversChanged = Signal()
    openView = Signal(str)

    def __init__(self, session, control, log, parent=None):
        super().__init__(parent)
        self.session, self.control, self.log = session, control, log
        self.details, self.players, self.pending = {}, {}, {}
        self.names, self._outputs, self._receivers = [], [], []
        self.cleanup = set()
        self.serial = 0
        self.error = ""
        self.capabilities = {}
        self.operations = set()
        self.watching = False
        self.selected = ""
        self.boot_id = None
        self._connected = session.connected
        self._permissions = (session.connected, control.owns, bool(control.pending))
        self.changed.connect(self._sync_catalogs)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)
        session.welcomed.connect(self.welcome)
        control.changed.connect(self.permissions_changed)
        control.barrierIssued.connect(self.barrier)

    @Property("QVariantList", notify=outputsChanged)
    def outputs(self):
        return self._outputs

    @Property("QVariantList", notify=receiversChanged)
    def receivers(self):
        return self._receivers

    def _sync_catalogs(self):
        outputs = [dict(name=n, label=f"{self.details[n].get('title', n)} · {n}") for n in self.names]
        receivers = [dict(id=n, label=self.details.get(n, {}).get("title", n))
                     for n, p in self.players.items() if p.phase == "receiving"]
        for attr, value, signal in (("_outputs", outputs, self.outputsChanged),
                                    ("_receivers", receivers, self.receiversChanged)):
            if getattr(self, attr) != value:
                setattr(self, attr, value)
                signal.emit()

    def permissions_changed(self):
        permissions = (self.session.connected, self.control.owns, bool(self.control.pending))
        if permissions != self._permissions:
            self._permissions = permissions
            self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(active=self._receivers, busyKeys=[p[0] for p in self.pending.values()],
                    error=self.error, capabilities=self.capabilities,
                    supported="videostream.subscribe" in self.operations,
                    canManage=self.session.connected and self.control.owns and not self.control.pending,
                    catalogBusy=self.busy("catalog") or self.busy("operations"))

    def busy(self, key):
        return any(p[0] == key for p in self.pending.values())

    def request(self, op, body, key, success, failure=None):
        if not self.session.connected or self.busy(key):
            return False
        self.serial += 1
        context = f"streams:{self.serial}"
        self.pending[context] = (key, success, failure)
        self.session.request(op, body, context)
        self.changed.emit()
        return True

    def problem(self, message):
        self.error = str(message)
        self.log("ERROR", "Стримы: " + self.error)
        self.changed.emit()

    def pages(self, op, key, limit, done):
        items = []
        def page(offset=0):
            def received(result):
                batch, cursor = result["items"], result.get("next_offset")
                if not isinstance(batch, list) or len(items) + len(batch) > 512:
                    raise ValueError("Некорректный каталог")
                items.extend(batch)
                if cursor is not None:
                    if type(cursor) is not int or cursor <= offset:
                        raise ValueError("Некорректная пагинация")
                    page(cursor)
                else:
                    done(items)
            self.request(op, dict(offset=offset, limit=limit), key, received)
        page()

    @Slot()
    def refresh(self):
        if not self.session.connected or self.view["catalogBusy"]:
            return
        self.error, self.watching = "", True
        if self.operations:
            self.catalog()
        else:
            def operations(items):
                self.operations = set(items)
                required = {"videostream.list", "videostream.status", "videostream.subscribe",
                            "videostream.unsubscribe", "videostream.update", "videostream.stop"}
                if not required <= self.operations:
                    self.operations.clear()
                    self.watching = False
                    self.problem("На роботе нет нужных операций videostream. Обновите runtime вместе с GUI.")
                    return
                self.request("videostream.capabilities", {}, "capabilities", self.got_capabilities)
                self.catalog()
            self.pages("system.operations", "operations", 12, operations)

    def got_capabilities(self, result):
        self.capabilities = result
        self.changed.emit()

    def catalog(self):
        if self.busy("catalog"):
            return
        def loaded(items):
            if not all(isinstance(s, dict) and isinstance(s.get("name"), str)
                       and isinstance(s.get("settings"), dict) and isinstance(s.get("controls"), dict)
                       for s in items):
                raise ValueError("Некорректное описание видеовыхода")
            names = [s["name"] for s in items]
            if len(set(names)) != len(names):
                raise ValueError("Повтор имени видеовыхода")
            self.names = names
            for s in items:
                self.details[s["name"]] = self.details.get(s["name"], {}) | s
            for n in list(self.details):
                if n not in names:
                    del self.details[n]
                    if n in self.players:
                        self.players[n].close("Видеовыход больше не объявлен")
            self.changed.emit()
            if self.selected in names:
                self.inspect(self.selected)
        self.pages("videostream.list", "catalog", 1, loaded)

    def remember(self, result):
        name = result["name"]
        self.details[name] = self.details.get(name, {}) | result
        self.changed.emit()

    @Slot(str, result="QVariantMap")
    def detail(self, name):
        return self.details.get(name, {})

    @Slot(str, result="QVariantMap")
    def reception(self, name):
        p = self.players.get(name)
        return p.view if p else dict(phase="idle", active=False, error="", frames=0)

    @Slot(str, result=str)
    def imageUrl(self, name):
        p = self.players.get(name)
        if p is None or p.phase != "receiving" or p.image.isNull():
            return ""
        return f"image://streams/{quote(name, safe='')}?frame={p.image_serial}"

    @Slot(str)
    def select(self, name):
        self.selected = name
        if name in self.details:
            self.inspect(name)

    def inspect_result(self, result):
        self.remember(result)
        p = self.players.get(result["name"])
        if p and p.phase == "receiving":
            if result.get("state") not in RUNNING or not result.get("subscribed"):
                p.close(result.get("error") or "Передача остановлена или подписка снята")
            elif (result.get("run_id"), result.get("ssrc")) != (p.info.get("run_id"), p.info.get("ssrc")):
                p.close("Передача перезапущена. Нажмите «Смотреть» заново.")
                self.unsubscribe(p.ident)
            else:
                p.info = result

    @Slot(str)
    def inspect(self, name):
        if name:
            self.request("videostream.status", dict(name=name), name, self.inspect_result,
                         lambda reason: self.status_failed(name, reason))

    def status_failed(self, name, reason):
        p = self.players.get(name)
        if p and p.phase in (*TRANSITIONAL, "receiving"):
            self.receiver_error(p, reason)
        else:
            self.problem(reason)

    @Slot(str, str, result=bool)
    def editable(self, name, key):
        info = self.details.get(name, {})
        meta = info.get("controls", {}).get(key)
        return bool(self.view["canManage"] and not self.busy(name) and meta
                    and not meta.get("fixed") and (info.get("state") in ("stopped", "failed")
                    or (info.get("state") in RUNNING and meta.get("live") is True)))

    @Slot(str, str, "QVariant")
    def update(self, name, key, value):
        if not self.editable(name, key):
            self.problem("Поле недоступно: нужны управление и подходящее состояние выхода.")
            return
        try:
            info = self.details[name]
            value = setting_value(info["controls"][key], value)
            settings = info["settings"] | {key: value}
            if "max_fps" in settings and settings["max_fps"] > settings["fps"]:
                raise ValueError("max_fps не может превышать fps")
        except (ValueError, TypeError, KeyError) as exc:
            self.problem(exc)
            return
        def updated(result):
            self.inspect_result(result)
            self.inspect(name)
        self.error = ""
        self.request("videostream.update", dict(name=name, lease_epoch=self.control.lease,
                     settings={key: value}), name, updated, lambda reason: self.operation_failed(name, reason))

    def operation_failed(self, name, reason):
        self.problem(reason)
        self.inspect(name)

    @Slot(str, int, str)
    def watch(self, name, port, decoder):
        if (name not in self.details or not self.view["supported"] or not self.session.connected
                or self.busy(name) or name in self.cleanup):
            return
        p = self.players.get(name)
        if p and p.stopping:
            return
        if p and p.phase == "receiving":
            self.openView.emit(name)
            return
        if p and p.phase in TRANSITIONAL:
            return
        if (port != 0 and not 1024 <= port <= 65535) or (port and any(
                q.ident != name and q.port == port and q.phase in (*TRANSITIONAL, "receiving")
                for q in self.players.values())):
            self.problem("UDP-порт недопустим или занят другим приёмником")
            return
        if p is None:
            p = self.players[name] = Player(self, name)
        p.generation += 1
        generation = p.generation
        p.phase, p.error, self.error = "inspecting", "", ""
        p.port, p.decoder = port, decoder
        p.clear_image()
        def inspected(result):
            if generation != p.generation:
                return
            self.remember(result)
            running = result["state"] in RUNNING
            if not running and (not self.view["canManage"] or not result.get("available")):
                p.close(result.get("reason") or "Для запуска получите управление")
                return
            p.info = result
            info = dict(result, rtp_port=port)
            if not running:
                info["ssrc"] = None
            try:
                receiver_description(info, decoder, 30)
                if p.receiver is None:
                    p.receiver = Receiver(p)
                    p.receiver.imageReady.connect(p.receive_image)
                    p.receiver.status.connect(p.status)
                    p.receiver.stopped.connect(p.receiver_stopped)
                    p.receiver.ready.connect(lambda bound: self.receiver_ready(p, bound))
                    p.receiver.error.connect(lambda msg: self.receiver_error(p, msg))
                    p.receiver.log.connect(self.log)
                p.phase = "preparing"
                p.receiver.prepare()
                p.receiver.start(info, decoder, 30)
            except Exception as exc:
                self.receiver_error(p, str(exc))
            p.changed.emit()
        self.request("videostream.status", dict(name=name), name, inspected, p.close)
        p.changed.emit()

    def receiver_ready(self, p, port):
        if p.phase != "preparing":
            return
        if not self.session.connected or (p.info["state"] not in RUNNING and not self.control.owns):
            p.close("Нет управления для запуска")
            return
        p.port = port
        generation = p.generation
        body = dict(name=p.ident, rtp_port=port)
        if self.control.owns:
            body["lease_epoch"] = self.control.lease
        # Apply settings explicitly via update; never overwrite shared settings
        # with an old draft during subscribe, including concurrent start races.
        p.phase = "joining"
        def joined(result):
            if generation != p.generation:
                return
            self.remember(result)
            p.info = result
            if result["state"] in RUNNING and result.get("subscribed"):
                p.phase = "receiving"
                self.openView.emit(p.ident)
            else:
                self.receiver_error(p, result.get("error") or "Подписка не подтверждена")
            p.changed.emit()
        def failed(reason):
            if generation != p.generation:
                return
            self.problem(reason)
            if "outcome unknown" in reason:
                p.phase = "reconciling"
                self.request("videostream.status", dict(name=p.ident), p.ident, joined,
                             lambda error: self.receiver_error(p, error))
            else:
                p.close(reason)
                self.inspect(p.ident)
        self.request("videostream.subscribe", body, p.ident, joined, failed)
        p.changed.emit()

    def receiver_error(self, p, message):
        p.close(message)
        self.problem(message)
        self.cleanup.add(p.ident)
        self.flush_cleanup()

    @Slot(str)
    def unsubscribe(self, name):
        if name in self.players:
            self.players[name].close(self.players[name].error)
        self.cleanup.add(name)
        self.flush_cleanup()

    def flush_cleanup(self):
        for name in list(self.cleanup):
            if self.busy(name) or not self.session.connected:
                continue
            self.cleanup.remove(name)
            self.request("videostream.unsubscribe", dict(name=name), name, self.remember,
                         lambda reason: self.problem("Отписка не подтверждена: " + reason))

    @Slot(str)
    def stop(self, name):
        if not self.view["canManage"] or self.busy(name):
            return
        self.request("videostream.stop", dict(name=name, lease_epoch=self.control.lease),
                     name, self.inspect_result, lambda reason: self.operation_failed(name, reason))

    def poll(self):
        if not self.session.connected:
            return
        if self.watching and self.operations:
            self.catalog()
        for name, p in self.players.items():
            if p.phase == "receiving":
                self.inspect(name)

    def response(self, op, result, context):
        if op == "system.status" and self.boot_id and result.get("boot_id") != self.boot_id:
            self.reset(result.get("boot_id"))
            return
        pending = self.pending.pop(context, None)
        if pending:
            try:
                pending[1](result)
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                self.problem(f"Некорректный ответ {op}: {exc}")
            self.flush_cleanup()
            self.changed.emit()

    def failed(self, op, reason, context):
        pending = self.pending.pop(context, None)
        if pending:
            (pending[2] or self.problem)(reason)
            self.flush_cleanup()
            self.changed.emit()

    def barrier(self):
        self.pending.clear()
        for name, p in self.players.items():
            if p.phase in TRANSITIONAL:
                p.close("Запрос прерван; подписка снимается")
                self.cleanup.add(name)
        QTimer.singleShot(0, self.flush_cleanup)
        self.changed.emit()

    def welcome(self, body):
        self.reset(body.get("boot_id"))

    def reset(self, boot_id):
        self.boot_id = boot_id
        self.pending.clear()
        self.cleanup.clear()
        self.details, self.names, self.operations, self.capabilities = {}, [], set(), {}
        for p in self.players.values():
            p.close("Новая сессия или перезапуск робота")
        self.changed.emit()
        if self.watching:
            self.refresh()

    def connection(self):
        if self._connected == self.session.connected:
            return
        self._connected = self.session.connected
        if not self.session.connected:
            self.pending.clear()
            self.cleanup.clear()
            self.details, self.names = {}, []
            for p in self.players.values():
                p.close("Нет связи")
        self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        for p in self.players.values():
            p.shutdown()
