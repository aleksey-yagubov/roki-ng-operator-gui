"""Explicit control lease and manual actions. No automatic acquire or mode change."""

import math

from PySide6.QtCore import QObject, Property, QEvent, QTimer, Qt, Signal, Slot
from PySide6.QtGui import QWindow


def scalar(meta, value):
    if "choices" in meta:
        if value not in meta["choices"]:
            raise ValueError("Выберите значение из списка")
        return value
    kind = meta.get("type", "str")
    if kind == 'object':
        if hasattr(value,'toVariant'):value=value.toVariant()
        if not isinstance(value,dict) or set(value)!=set(meta.get('fields',{})):
            raise ValueError('Неверный набор полей')
        result={}
        for key,spec in meta['fields'].items():
            descriptor=({'type':'bool'} if spec=='bool' else
                        {'choices':spec} if isinstance(spec[0],str) else
                        {'type':'float','min':spec[0],'max':spec[1]})
            result[key]=scalar(descriptor,value[key])
        return result
    if kind == "bool":
        if type(value) is not bool:
            raise ValueError("Ожидается да/нет")
        return value
    if kind in ("int", "float"):
        if isinstance(value, bool):
            raise ValueError("Ожидается число")
        text = str(value).strip().replace(",", ".")
        number = float(text)
        if not math.isfinite(number) or (kind == "int" and not number.is_integer()):
            raise ValueError("Ожидается конечное " + ("целое число" if kind == "int" else "число"))
        if meta.get("min") is not None and number < meta["min"]:
            raise ValueError(f"Минимум: {meta['min']}")
        if meta.get("max") is not None and number > meta["max"]:
            raise ValueError(f"Максимум: {meta['max']}")
        return int(number) if kind == "int" else number
    return str(value)


class Control(QObject):
    changed = Signal()
    headChanged = Signal()
    barrierIssued = Signal()

    def __init__(self, session, log, parent=None):
        super().__init__(parent)
        self.session, self.log = session, log
        self.lease = None
        self.mode = ""
        self.pending = ""
        self.uncertain = False
        self.job = {}
        self.error = ""
        self.pan = self.tilt = 0
        self.head_step = 250
        self.keyboard = False
        self.held = set()
        self.speed = 0.5
        self.hold_crouch = True
        self.zero_remaining = 0
        self.poll_pending = False
        session.changed.connect(self._connection)
        session.response.connect(self._response)
        session.failed.connect(self._failed)
        self.drive_timer = QTimer(self)
        self.drive_timer.setInterval(50)
        self.drive_timer.timeout.connect(self._drive)
        self.job_timer = QTimer(self)
        self.job_timer.setInterval(500)
        self.job_timer.timeout.connect(self.refreshJob)
        self.job_timer.start()

    @property
    def owns(self):
        return self.session.connected and self.lease is not None

    @property
    def moving(self):
        return self.job.get("status") in ("accepted", "running", "saving")

    @property
    def blocked_reason(self):
        if not self.session.connected:
            return "Нет соединения с роботом."
        if not self.owns:
            return "Нажмите «Получить управление» в верхней панели."
        if self.pending:
            return "Ожидается ответ: " + self.pending
        if self.uncertain:
            return "Исход предыдущей команды неизвестен. Нужен явный сброс очереди."
        if self.mode != "MANUAL":
            return f"Режим {self.mode or 'неизвестен'}. Для тестов и слотов включите ручной режим."
        if self.moving:
            return "Выполняется " + self.job.get("operation", "движение") + ". Дождитесь завершения или остановите его."
        if self.held:
            return "Отпустите кнопки ходьбы перед разовым движением."
        return ""

    @Property("QVariantMap", notify=changed)
    def view(self):
        return dict(owns=self.owns, manual=self.owns and self.mode == "MANUAL",
                    ready=not self.blocked_reason, blockedReason=self.blocked_reason,
                    canEnterManual=self.owns and self.mode != "MANUAL" and not self.pending and not self.uncertain and not self.moving and not self.held,
                    pending=self.pending, moving=self.moving, keyboard=self.keyboard,
                    error=self.error, pan=self.pan, tilt=self.tilt,
                    jobOperation=self.job.get("operation", "Нет задания"),
                    jobStatus=self.job.get("status", ""), jobProgress=str(self.job.get("progress", "")),
                    jobReason=str(self.job.get("reason") or ""), jobStage=str(self.job.get("stage", "")))

    @Slot()
    def acquire(self):
        if self.session.connected and not self.pending and not self.owns:
            self.pending = "control.acquire"
            self.session.request(self.pending)
            self.changed.emit()

    @Slot()
    def release(self):
        self.stopInput()
        if self.owns:
            self.pending = "control.release"
            self.barrierIssued.emit()
            self.session.interrupt(self.pending, {"lease_epoch": self.lease})
            self.changed.emit()

    @Slot()
    def enterManual(self):
        self.command("mode.set", {"mode": "MANUAL"}, manual=False)

    def command(self, op, body, *, manual=True, job=True, context=""):
        if (not self.owns or self.pending or self.uncertain or (manual and self.mode != "MANUAL")
                or (job and (self.moving or self.held))):
            self.reject("Команда не отправлена: нет управления, неверный режим или движение занято")
            return False
        self.pending = op
        self.error = ""
        self.session.request(op, dict(body, lease_epoch=self.lease), context)
        self.changed.emit()
        return True

    def reject(self, text):
        self.error = text
        self.log("WARNING", text)
        self.changed.emit()

    @Slot(str)
    def pose(self, name):
        if name in ("base_stand", "stand", "crouch", "head_field"):
            self.command("motion.pose", {"name": name})

    @Slot(str)
    def jump(self, direction):
        if direction in ("forward", "backward", "left", "right", "turn_left", "turn_right"):
            self.command("motion.jump", {"direction": direction, "fraction": 1.0})

    @Slot(str, int)
    def kick(self, leg, power):
        if leg in ("left", "right") and 1 <= power <= 100:
            self.command("motion.kick", {"leg": leg, "power": power})

    @Slot(str, float)
    def slot(self, name, speed):
        self.command("motion.slot", {"name": name, "speed_factor": speed})

    @Slot(int, int)
    def head(self, pan, tilt):
        if -2666 <= pan <= 2666 and -2600 <= tilt <= 950:
            self.command("motion.head", {"pan": pan, "tilt": tilt, "frames": 10}, job=False)

    @Property("QVariantMap", notify=headChanged)
    def headUi(self):
        return dict(pan=self.pan, tilt=self.tilt, step=self.head_step)

    @Slot(int, int)
    def setHeadUi(self, pan, tilt):
        self.pan = max(-2666, min(2666, pan))
        self.tilt = max(-2600, min(950, tilt))
        self.headChanged.emit()

    @Slot(int)
    def setHeadStep(self, step):
        self.head_step = max(10, min(1000, step))
        self.headChanged.emit()

    @Slot(int, int)
    def adjustHead(self, pan, tilt):
        self.head(max(-2666, min(2666, self.pan + pan)), max(-2600, min(950, self.tilt + tilt)))

    @Slot(str)
    def nudgeHead(self, direction):
        axes = {"up": (0, 1), "down": (0, -1), "left": (1, 0), "right": (-1, 0)}
        if direction in axes:
            pan, tilt = axes[direction]
            self.adjustHead(pan * self.head_step, tilt * self.head_step)

    @Slot(bool)
    def stop(self, hard):
        self.stopInput()
        if not self.owns:
            return
        op = "motion.stop_hard" if hard else "motion.stop_graceful"
        self.pending = op
        self.poll_pending = False
        self.barrierIssued.emit()
        self.session.interrupt(op, {"lease_epoch": self.lease})
        self.changed.emit()

    @Slot()
    def refreshJob(self):
        if self.session.connected and self.moving and not self.poll_pending and not self.pending:
            self.poll_pending = True
            self.session.request("job.status", {"job_id": self.job["job_id"]})

    @Slot(bool)
    def setKeyboard(self, enabled):
        self.stopInput()
        self.keyboard = enabled and self.owns and self.mode == "MANUAL"
        self.changed.emit()

    @Slot(float, bool)
    def driveSettings(self, speed, hold):
        self.speed = max(0.1, min(1.0, speed))
        self.hold_crouch = hold

    @Slot(str, bool)
    def hold(self, direction, pressed):
        if direction not in ("forward", "backward", "left", "right"):
            return
        if pressed:
            if not self.owns or self.mode != "MANUAL" or self.pending or self.uncertain:
                return
            if self.moving and self.job.get("operation") != "motion.drive":
                return
            self.held.add(direction)
        else:
            self.held.discard(direction)
            self.zero_remaining = 3
        if not self.drive_timer.isActive():
            self.drive_timer.start()
        self._drive()
        self.changed.emit()

    @Slot()
    def stopInput(self):
        if self.held:
            self.held.clear()
            self.zero_remaining = 3
            self.drive_timer.start()
            self._drive()
        self.keyboard = False
        self.changed.emit()

    def _drive(self):
        if not self.owns or self.mode != "MANUAL" or not (self.held or self.zero_remaining):
            self.drive_timer.stop()
            return
        h = self.held
        self.session.drive(dict(lease_epoch=self.lease, x=int("forward" in h)-int("backward" in h),
                                y=int("left" in h)-int("right" in h), yaw=0.0,
                                speed=self.speed, hold_crouch=self.hold_crouch))
        if not h:
            self.zero_remaining -= 1
            if not self.zero_remaining:
                self.drive_timer.stop()

    def install_keyboard(self, app):
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self._application_state)

    @Slot(Qt.ApplicationState)
    def _application_state(self, state):
        if state != Qt.ApplicationState.ApplicationActive:
            self.stopInput()

    def eventFilter(self, watched, event):
        # Handle once at the application window, not once per QtQuick child.
        if not self.keyboard or not isinstance(watched, QWindow):
            return False
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        key = event.key()
        directions = {Qt.Key.Key_W: "forward", Qt.Key.Key_S: "backward",
                      Qt.Key.Key_A: "left", Qt.Key.Key_D: "right"}
        turns = {Qt.Key.Key_Q: "turn_left", Qt.Key.Key_E: "turn_right"}
        arrows = {Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
                  Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right"}
        if key not in directions and key not in turns and key not in arrows and key != Qt.Key.Key_Space:
            return False
        if event.isAutoRepeat():
            return True
        pressed = event.type() == QEvent.Type.KeyPress
        if key in directions:
            if pressed and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.jump(directions[key])
            else:
                self.hold(directions[key], pressed)
        elif pressed and key in turns:
            self.jump(turns[key])
        elif pressed and key in arrows:
            self.nudgeHead(arrows[key])
        elif pressed:
            self.stop(True)
        return True

    @Slot()
    def _connection(self):
        if not self.session.connected:
            self.lease = None
            self.pending = ""
            self.uncertain = False
            self.keyboard = False
            self.held.clear()
            self.zero_remaining = 0
            self.drive_timer.stop()
            self.job = {}
            self.poll_pending = False
        self.changed.emit()

    @Slot(str, object, str)
    def _response(self, op, result, context):
        if op == self.pending:
            self.pending = ""
        if op == "control.acquire":
            self.lease = result["lease_epoch"]
        elif op == "control.release":
            self.lease = None
            self.mode = "IDLE"
            self.stopInput()
        elif op in ("session.heartbeat", "mode.set"):
            self.mode = result.get("state", self.mode)
            if self.mode != "MANUAL":
                self.stopInput()
        elif op == "system.status":
            self.mode = result.get("state", self.mode)
            if self.lease is not None and result.get("owner") != self.session.session:
                self.lease = None
            if not self.owns or self.mode != "MANUAL":
                self.stopInput()
        elif op == "motion.head":
            self.pan = result.get("target", {}).get("pan", self.pan)
            self.tilt = result.get("target", {}).get("tilt", self.tilt)
            self.headChanged.emit()
        elif op == "job.status":
            self.poll_pending = False
            if result.get("job_id") == self.job.get("job_id"):
                self.job = result
        elif op == "motion.stop_hard":
            self.uncertain = False
            self.job = dict(self.job, status="cancelled", reason="Очередь STM сброшена; поза неизвестна")
        elif result.get("job_id") and result.get("accepted"):
            if result["job_id"] != self.job.get("job_id"):
                self.job = dict(job_id=result["job_id"], operation=op, status="accepted")
        self.changed.emit()

    def notification(self, op, body):
        if op.startswith("job.") and body.get("job_id"):
            if body["job_id"] == self.job.get("job_id"):
                self.job = self.job | body
                self.changed.emit()

    @Slot(str, str, str)
    def _failed(self, op, message, context):
        if op == self.pending:
            self.pending = ""
            self.error = message
            if "outcome unknown" in message:
                self.uncertain = True
                self.error += ". Исход команды неизвестен; выполните сброс очереди перед новым движением."
            self.stopInput()
        if op == "job.status":
            self.poll_pending = False
        if message.startswith("not_owner"):
            self.lease = None
            self.stopInput()
        self.changed.emit()

    def shutdown(self):
        self.stopInput()
        self.drive_timer.stop()
        self.job_timer.stop()
