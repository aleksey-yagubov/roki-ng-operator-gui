"""Explicit diagnostic localization controls; stale candidates never look current."""
import math
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class Localisation(QObject):
    changed = Signal()

    def __init__(self, session, control, parent=None):
        super().__init__(parent)
        self.session, self.control = session, control
        self.available = False
        self.was_connected = session.connected
        self.state = {}
        self.received = None
        self.pending = False
        self.notice = 'Проверьте доступность локализации на роботе.'
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.refresh)
        self.clock = QTimer(self)
        self.clock.setInterval(250)
        self.clock.timeout.connect(self.changed.emit)
        self.clock.start()
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)

    @Property('QVariantMap', notify=changed)
    def view(self):
        result = self.state.get('result') or {}
        age = self.state.get('age_ms')
        if age is not None and self.received is not None:
            age += round((time.monotonic()-self.received)*1000)
        pose = result.get('candidate')
        sane = (isinstance(pose, list) and len(pose) == 3 and
                all(type(x) in (float, int) and math.isfinite(x) for x in pose))
        fresh = (self.session.connected and self.state.get('running', False) and
                 not self.state.get('error') and age is not None and 0 <= age <= 1500)
        return dict(available=self.available, pending=self.pending,
                    running=self.state.get('running', False), watching=self.timer.isActive(),
                    notice=self.notice, error=self.state.get('error') or '',
                    pose=pose if sane and fresh else [], ageMs=age,
                    fresh=fresh, result=result, geometry=self.state.get('geometry') or {},
                    configurationId=self.state.get('configuration_id') or '',
                    status=('Нет связи' if not self.session.connected else
                            'Остановлена' if not self.state.get('running') else
                            'Ошибка' if self.state.get('error') else
                            'Нет свежей оценки' if not fresh or not sane else
                            'Диагностический кандидат — не подтверждённая позиция'))

    @Slot()
    def check(self):
        if self.session.connected:
            self.session.request('system.capabilities', {}, 'localisation:capabilities')

    @Slot()
    def refresh(self):
        if self.session.connected and self.available and not self.pending:
            self.pending = True
            self.session.request('localisation.status', {}, 'localisation:status')
            self.changed.emit()

    @Slot(bool)
    def watch(self, enabled):
        if enabled and self.available and self.session.connected:
            self.timer.start()
            self.refresh()
        else:
            self.timer.stop()
        self.changed.emit()

    def command(self, op, args, manual=True):
        if not self.control.command(op, args, manual=manual, job=False, context='localisation:action'):
            self.notice = self.control.error
            self.changed.emit()

    @Slot()
    def startCamera(self):
        self.command('camera.start', {'with_imu': True})

    @Slot(float, float, float)
    def start(self, x, y, yaw_degrees):
        if not self.available:
            return
        if not all(math.isfinite(v) for v in (x, y, yaw_degrees)) or abs(yaw_degrees)>180:
            self.notice = 'Введите конечные координаты и угол от −180 до 180°.'
            self.changed.emit()
            return
        self.command('localisation.start', {'prior': [x, y, math.radians(yaw_degrees)]})

    @Slot()
    def stop(self):
        self.command('localisation.stop', {}, manual=False)

    def response(self, op, result, context):
        if context == 'localisation:capabilities':
            self.available = isinstance(result.get('localisation'), dict)
            self.notice = ('Локализация доступна. Камера должна работать с синхронизацией IMU.'
                           if self.available else 'Установленный runtime не поддерживает локализацию.')
            if self.available:
                self.refresh()
        elif context in ('localisation:status', 'localisation:action'):
            if op.startswith('localisation.'):
                self.pending = False
                self.state = result
                self.received = time.monotonic()
                self.notice = 'Координаты: начало в центре, +X вдоль поля вверх, +Y влево; yaw от +X.'
            elif op == 'camera.start':
                self.notice = 'Камера запущена. Дождитесь синхронизации IMU перед запуском локализации.'
        else:
            return
        self.changed.emit()

    def failed(self, op, error, context):
        if context.startswith('localisation:'):
            self.pending = False
            self.notice = str(error)
            self.changed.emit()

    @Slot()
    def connection(self):
        if self.session.connected:
            if not self.was_connected:
                self.notice = 'Проверьте доступность локализации на роботе.'
            self.was_connected = True
            self.changed.emit()
        else:
            self.was_connected = False
            self.timer.stop()
            self.available = False
            self.pending = False
            self.state = {}
            self.received = None
            self.notice = 'Нет соединения с роботом.'
            self.changed.emit()

    @Slot()
    def barrier(self):
        self.pending = False
        self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        self.clock.stop()
