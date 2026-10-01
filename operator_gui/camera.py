"""Runtime camera and ISP controls. Never creates a video transmission."""
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from .control import scalar


class Camera(QObject):
    changed = Signal()
    catalogChanged = Signal()

    def __init__(self, session, control, parent=None):
        super().__init__(parent)
        self.session, self.control = session, control
        self.state, self.capabilities, self.metas, self.values, self.drafts = {}, {}, {}, {}, {}
        self.pending = set()
        self.notice = "Запросите состояние и настройки камеры."
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.refreshStatus)
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)
        control.changed.connect(self.changed)
        control.barrierIssued.connect(self.barrier)

    @Property("QStringList", notify=catalogChanged)
    def keys(self):
        return list(self.metas)

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(state=self.state, capabilities=self.capabilities, metas=self.metas,
                    requested=self.values, values=self.values | self.drafts,
                    dirty=bool(self.drafts), busy=bool(self.pending), notice=self.notice,
                    watching=self.timer.isActive(),
                    canEdit=self.session.connected and self.control.owns and not self.control.pending
                    and not self.pending)

    def read(self, op, body=None):
        if self.session.connected and op not in self.pending:
            self.pending.add(op)
            self.session.request(op, body or {}, "camera-ui:" + op)
            self.changed.emit()

    @Slot()
    def refresh(self):
        self.read("camera.capabilities")
        self.refreshStatus()
        self.read("camera.controls.list", dict(offset=0, limit=2))

    @Slot()
    def refreshStatus(self):
        self.read("camera.status")

    @Slot(bool)
    def watch(self, enabled):
        if enabled and self.session.connected:
            self.timer.start()
            self.refreshStatus()
        else:
            self.timer.stop()
        self.changed.emit()

    def command(self, op, body, manual=False):
        if not self.control.command(op, body, manual=manual, job=False, context="camera-ui:" + op):
            self.notice = self.control.error
        self.changed.emit()

    @Slot(int)
    def start(self, duration):
        if not 8333 <= duration <= 100000:
            self.notice = "Период кадра: 8333–100000 мкс"
            self.changed.emit()
            return
        self.command("camera.start", dict(frame_duration_us=duration), manual=True)

    @Slot()
    def stop(self):
        self.command("camera.stop", {})

    @Slot(str, "QVariant")
    def edit(self, key, value):
        try:
            if self.metas[key].get("supported") is False:
                raise ValueError("Control не поддерживается")
            self.drafts[key] = scalar(self.metas[key], value)
        except (ValueError, KeyError, TypeError) as exc:
            self.notice = str(exc)
        self.changed.emit()

    @Slot()
    def defaults(self):
        for key, meta in self.metas.items():
            if meta.get("supported") is not False:
                self.drafts[key] = meta["default"]
        self.changed.emit()

    @Slot()
    def discard(self):
        self.drafts.clear()
        self.changed.emit()

    @Slot(bool)
    def apply(self, save):
        if self.drafts and not self.pending:
            self.command("camera.controls.save" if save else "camera.controls.set", dict(values=dict(self.drafts)))

    @Slot(str)
    def freeze(self, group):
        if group in ("exposure", "white_balance", "all"):
            self.command("camera.controls.freeze", dict(group=group))

    def response(self, op, result, context):
        if context != "camera-ui:" + op:
            return
        self.pending.discard(op)
        if op == "camera.controls.list":
            for meta in result["items"]:
                self.metas[meta["key"]] = meta
                self.values[meta["key"]] = meta["value"]
            if result.get("next_offset") is not None:
                self.read(op, dict(offset=result["next_offset"], limit=2))
            else:
                self.catalogChanged.emit()
        elif op == "camera.capabilities":
            self.capabilities = result
        elif op in ("camera.status", "camera.start", "camera.stop"):
            self.state = result
            requested = result.get("requested_controls") or {}
            for wire_key, key in (("exposure_us", "camera.exposure_us"),
                                  ("gain", "camera.analogue_gain"),
                                  ("ae_enabled", "camera.ae_enabled"),
                                  ("awb_enabled", "camera.awb_enabled")):
                if wire_key in requested:
                    self.values[key] = requested[wire_key]
            gains = requested.get("colour_gains")
            if isinstance(gains, (list, tuple)) and len(gains) == 2:
                self.values["camera.white_balance.red_gain"] = gains[0]
                self.values["camera.white_balance.blue_gain"] = gains[1]
            if op != "camera.status":
                self.read("camera.controls.list", dict(offset=0, limit=2))
        elif op.startswith("camera.controls."):
            self.values.update(result["values"])
            if op.endswith(".save"):
                for key, value in result["values"].items():
                    if self.drafts.get(key) == value:
                        self.drafts.pop(key, None)
                self.notice = "Применено и сохранено на роботе."
            else:
                self.drafts.update(result["values"])
                self.notice = "Применено временно. Для записи в профиль нажмите «Сохранить»."
        self.changed.emit()

    def failed(self, op, message, context):
        if context.startswith("camera-ui:"):
            self.pending.discard(op)
            self.notice = message
            self.changed.emit()

    def barrier(self):
        self.pending.clear()
        self.changed.emit()

    def connection(self):
        if not self.session.connected:
            self.timer.stop()
            self.pending.clear()
            self.state, self.capabilities, self.metas, self.values, self.drafts = {}, {}, {}, {}, {}
            self.notice = "Нет связи. Запросите настройки после подключения."
            self.catalogChanged.emit()
        self.changed.emit()

    def shutdown(self):
        self.timer.stop()
