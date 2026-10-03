"""Explicit control lease and manual actions. No automatic acquire or mode change."""

import math
import time

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
        self._connected = session.connected
        self.lease = None
        self.mode = ""
        self.pending = ""
        self.uncertain = False
        self.job = {}
        self.error = ""
        self.pan = self.tilt = 0
        self.head_target = None
        self.head_dirty = False
        self.head_edit = 0
        self.head_sent_edit = 0
        self.head_revision = 0
        self.head_sync = ""
        self.head_since = time.monotonic()
        self.head_step = 250
        self.keyboard = False
        self.held = set()
        self.speed = 0.5
        self.crouch = "off"
        self.heading_hold = False
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
        self.job_timer.timeout.connect(self.refreshHead)
        self.job_timer.start()
        self.changed.connect(self.headChanged.emit)
        self.barrierIssued.connect(self._invalidate_head)

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
        return dict(mode=self.mode, owns=self.owns, manual=self.owns and self.mode == "MANUAL",
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

    @Slot()
    def leaveManual(self):
        if not self.owns or self.mode != "MANUAL" or self.pending == "mode.set":
            return
        self.stopInput()
        self.pending = "mode.set"
        self.poll_pending = False
        self.barrierIssued.emit()
        self.session.interrupt("mode.set", {"lease_epoch": self.lease, "mode": "IDLE"})
        self.changed.emit()

    def command(self, op, body, *, manual=True, job=True, context=""):
        if (not self.owns or self.pending or self.uncertain or (manual and self.mode != "MANUAL")
                or (job and (self.moving or self.held))):
            self.reject("Команда не отправлена: нет управления, неверный режим или движение занято")
            return False
        self.pending = op
        if op == "motion.head":
            self.head_sent_edit = self.head_edit
            self.head_revision += 1
            self.head_sync = ""
        elif job and (op.startswith("motion.") or op == "test.start"):
            self._invalidate_head()
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
            body = {"name": name}
            if name == "crouch":
                body["crouch"] = "centered" if self.crouch == "centered" else "on"
            self.command("motion.pose", body)

    @Slot(str)
    def jump(self, direction):
        if direction in ("forward", "backward", "left", "right", "turn_left", "turn_right"):
            self.command("motion.jump", {"direction": direction, "fraction": 1.0,
                                         "crouch": self.crouch})

    @Slot()
    def getUp(self):
        self.command("motion.get_up", {"crouch": self.crouch})

    @Slot(str)
    def splits(self, kind):
        if kind in ("small", "big"):
            self.command("motion.splits", {"kind": kind, "crouch": self.crouch})

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
        allowed = (self.owns and self.mode == "MANUAL" and not self.pending and not self.uncertain
                   and (not self.moving or self.job.get("operation") in ("motion.drive", "test.start")))
        return dict(pan=self.pan, tilt=self.tilt, step=self.head_step,
                    known=self.head_target is not None, dirty=self.head_dirty,
                    canSend=allowed, canNudge=allowed and self.head_target is not None,
                    targetPan=self.head_target["pan"] if self.head_target else None,
                    targetTilt=self.head_target["tilt"] if self.head_target else None)

    def _invalidate_head(self):
        self.head_revision += 1
        self.head_sync = ""
        self.head_target = None
        self.head_dirty = False
        self.pan = self.tilt = 0
        self.head_since = time.monotonic()
        self.headChanged.emit()

    def _head_target(self, target, *, update_draft):
        if not isinstance(target, dict) or not all(
                type(target.get(axis)) is int and low <= target[axis] <= high
                for axis, low, high in (("pan", -2666, 2666), ("tilt", -2600, 950))):
            return
        self.head_target = {axis: target[axis] for axis in ("pan", "tilt")}
        if update_draft:
            self.pan, self.tilt = target["pan"], target["tilt"]
            self.head_dirty = False
        self.headChanged.emit()

    @Slot()
    def refreshHead(self):
        if not self.owns or self.mode != "MANUAL" or self.pending or self.head_sync:
            return
        self.head_sync = f"head-state:{self.head_revision}"
        self.head_requested_at = time.monotonic()
        self.session.request("data.snapshot", {"topic": "motion.state"}, self.head_sync)

    @Slot(str)
    def resetHeadAxis(self, axis):
        if axis in ("pan", "tilt"):
            self.command("motion.head", {axis: 0, "frames": 10}, job=False)

    @Slot(int, int)
    def setHeadUi(self, pan, tilt):
        self.pan = max(-2666, min(2666, pan))
        self.tilt = max(-2600, min(950, tilt))
        self.head_edit += 1
        self.head_dirty = True
        self.headChanged.emit()

    @Slot(int)
    def setHeadStep(self, step):
        self.head_step = max(10, min(1000, step))
        self.headChanged.emit()

    @Slot(int, int)
    def adjustHead(self, pan, tilt):
        if not self.headUi["canNudge"]:
            self.reject("Голова занята или её заданная позиция ещё не получена")
            return
        values = {"frames": 10}
        if pan:
            values["pan"] = max(-2666, min(2666, self.head_target["pan"] + pan))
        if tilt:
            values["tilt"] = max(-2600, min(950, self.head_target["tilt"] + tilt))
        self.command("motion.head", values, job=False)

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
        self.keyboard = enabled
        self.changed.emit()

    @Property("QVariantMap", notify=changed)
    def driveUi(self):
        return dict(speed=self.speed, crouch=self.crouch, headingHold=self.heading_hold)

    @Slot(float, str, bool)
    def driveSettings(self, speed, crouch, heading_hold):
        if crouch not in ("off", "on", "centered"):
            return
        self.speed = max(0.1, min(1.0, speed))
        self.crouch = crouch
        self.heading_hold = heading_hold
        self.changed.emit()

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
            self.changed.emit()

    def _drive(self):
        if not self.owns or self.mode != "MANUAL" or not (self.held or self.zero_remaining):
            self.drive_timer.stop()
            return
        h = self.held
        self.session.drive(dict(lease_epoch=self.lease, x=int("forward" in h)-int("backward" in h),
                                y=int("left" in h)-int("right" in h), yaw=0.0,
                                speed=self.speed, crouch=self.crouch, heading_hold=self.heading_hold))
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
        if not self.keyboard or not self.owns or self.mode != "MANUAL" or not isinstance(watched, QWindow):
            return False
        if event.type() not in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            return False
        key = event.key()
        directions = {Qt.Key.Key_W: "forward", Qt.Key.Key_S: "backward",
                      Qt.Key.Key_A: "left", Qt.Key.Key_D: "right"}
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.MetaModifier):
            # Keep standard shortcuts (including Ctrl+A/C) out of robot controls.
            if event.type() == QEvent.Type.KeyRelease and key in directions and directions[key] in self.held:
                self.hold(directions[key], False)
            return False
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
        if self._connected == self.session.connected:
            return
        self._connected = self.session.connected
        if not self.session.connected:
            self._invalidate_head()
            self.lease = None
            self.pending = ""
            self.uncertain = False
            self.held.clear()
            self.zero_remaining = 0
            self.drive_timer.stop()
            self.job = {}
            self.poll_pending = False
        self.changed.emit()

    @Slot(str, object, str)
    def _response(self, op, result, context):
        if context.startswith("head-state:"):
            if context != self.head_sync:
                return
            self.head_sync = ""
            # Snapshots are cached worker heartbeats. Do not undo a newer command
            # with a state observed before its acknowledgement/job completion.
            age = result.get("age_ms")
            if (result.get("topic") == "motion.state" and result.get("valid") is True
                    and isinstance(age, (int, float)) and 0 <= age <= 1500
                    and age <= (self.head_requested_at - self.head_since) * 1000):
                self._head_target(result.get("data", {}).get("head"), update_draft=not self.head_dirty)
            elif result.get("valid") is not True or not isinstance(age, (int, float)) or not 0 <= age <= 1500:
                self.head_target = None
                self.headChanged.emit()
            return
        relevant = op in ("control.acquire", "control.release", "session.heartbeat", "mode.set",
                          "system.status", "game.start", "game.stop", "game.status", "game.pause",
                          "game.resume", "game.pickup", "motion.head",
                          "job.status", "motion.stop_hard")
        if not relevant and op != self.pending and not (result.get("job_id") and result.get("accepted")):
            return
        if (op == "session.heartbeat" and result.get("state", self.mode) == self.mode
                and (self.mode == "MANUAL" or not self.held)):
            return
        was_moving = self.moving
        was_manual = self.view["manual"]
        if op == self.pending:
            self.pending = ""
        if op == "control.acquire":
            self.lease = result["lease_epoch"]
            self._invalidate_head()
        elif op == "control.release":
            self.lease = None
            self.mode = "IDLE"
            self.stopInput()
        elif op in ("session.heartbeat", "mode.set"):
            self.mode = result.get("state", self.mode)
            if op == "mode.set" and self.mode == "IDLE":
                self.uncertain = False
                self.job = dict(self.job, status="cancelled", reason="Ручной режим выключен")
            if self.mode != "MANUAL":
                self.stopInput()
        elif op == "system.status":
            self.mode = result.get("state", self.mode)
            if self.lease is not None and result.get("owner") != self.session.session:
                self.lease = None
            if not self.owns or self.mode != "MANUAL":
                self.stopInput()
        elif op in ("game.start", "game.stop", "game.status", "game.pause", "game.resume", "game.pickup"):
            if result.get("running") is True:
                self.mode = "GAME"
                self.stopInput()
            if op == "game.stop":
                self.uncertain = False
        elif op == "motion.head":
            self.head_since = time.monotonic()
            self._head_target(result.get("target"), update_draft=self.head_edit == self.head_sent_edit)
        elif op == "job.status":
            self.poll_pending = False
            if result.get("job_id") == self.job.get("job_id"):
                self.job = result
        elif op == "motion.stop_hard":
            self._invalidate_head()
            self.uncertain = False
            self.job = dict(self.job, status="cancelled", reason="Очередь STM сброшена; поза неизвестна")
        elif result.get("job_id") and result.get("accepted"):
            if result["job_id"] != self.job.get("job_id"):
                self.job = dict(job_id=result["job_id"], operation=op, status="accepted")
        if was_moving and not self.moving:
            self._invalidate_head()
        if was_manual != self.view["manual"]:
            self._invalidate_head()
        self.headChanged.emit()
        self.changed.emit()

    def notification(self, op, body):
        if op.startswith("job.") and body.get("job_id"):
            if body["job_id"] == self.job.get("job_id"):
                was_moving = self.moving
                self.job = self.job | body
                if was_moving and not self.moving:
                    self._invalidate_head()
                self.headChanged.emit()
                self.changed.emit()

    @Slot(str, str, str)
    def _failed(self, op, message, context):
        if context.startswith("head-state:"):
            if context == self.head_sync:
                self.head_sync = ""
                self.head_target = None
                self.headChanged.emit()
            return
        if op == self.pending:
            if op == "motion.head":
                self._invalidate_head()
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
