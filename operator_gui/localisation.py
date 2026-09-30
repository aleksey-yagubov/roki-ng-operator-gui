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
        self.checking = False
        self.checked = False
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
        problems=[]
        if result:
            if result.get('lines',0)<3:problems.append('Недостаточно отрезков для сопоставления')
            if not result.get('circle'):problems.append('Круг не найден или виден неполностью')
            if not result.get('goal_pairs'):problems.append('Нет пригодной пары цветных стоек')
            if result.get('goal_rejected'):problems.append(f"Цветных областей без подтверждения ворот: {result['goal_rejected']} (размер, положение на карте или неопределённая поза)")
            if result.get('fit_state')=='weak' or 'weak_geometry' in result.get('reason',''):problems.append('Линии плохо совпадают с картой: проверьте размеры поля, высоту и калибровку камеры')
            if result.get('ambiguous'):problems.append('Несколько возможных позиций: сторона поля не определена')
            if result.get('reason')=='motion_discontinuity':problems.append('Скачок превышает допустимую скорость: проверьте наблюдения или задайте позу после перестановки')
            if not fresh:problems.append('Оценка устарела: возможна задержка обработки или потеря кадров/IMU')
        return dict(problems='\n'.join(problems),available=self.available, pending=self.pending, checking=self.checking, checked=self.checked,
                    running=self.state.get('running', False), watching=self.timer.isActive(),
                    notice=self.notice, error=self.state.get('error') or '',
                    pose=pose if sane and fresh and not result.get('ambiguous') and result.get('fit_state') not in ('weak','rejected') else [], ageMs=age,
                    fresh=fresh, result=result, geometry=self.state.get('geometry') or {},
                    configurationId=self.state.get('configuration_id') or '',
                    status=('Нет связи' if not self.session.connected else
                            'Проверяю возможности робота…' if self.checking else
                            'Нужно обновить сервис робота: локализация отсутствует' if self.checked and not self.available else
                            'Проверьте возможности робота' if not self.checked else
                            'Локализация доступна — не запущена' if not self.state.get('running') else
                            'Ошибка' if self.state.get('error') else
                            'Отклонён невозможный скачок позиции' if result.get('reason') == 'motion_discontinuity' else
                            'Нет свежей оценки' if not fresh or not sane else
                            'Положение неоднозначно — сторона поля не определена' if result.get('ambiguous') else
                            'Слабое совпадение разметки — положение не определено' if result.get('fit_state') == 'weak' else
                            'Диагностический кандидат — не подтверждённая позиция'))

    @Slot()
    def check(self):
        if self.session.connected and not self.checking:
            self.checking = True
            self.notice = 'Запрашиваю возможности у робота…'
            self.changed.emit()
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
            self.checking = False
            self.checked = True
            self.available = isinstance(result.get('localisation'), dict)
            self.notice = ('Локализация доступна. Камера должна работать с синхронизацией IMU.'
                           if self.available else 'Установленный runtime не поддерживает локализацию.')
            if self.available:
                self.watch(True)
        elif context in ('localisation:status', 'localisation:action'):
            if op.startswith('localisation.'):
                self.pending = False
                self.state = result
                self.received = time.monotonic()
                self.notice = ('Локализация работает. Координаты: начало в центре, +X вдоль поля вверх, +Y влево; yaw от +X.'
                               if result.get('running') else
                               'Проверка успешна: робот поддерживает локализацию. Для запуска получите управление, '
                               'включите MANUAL, нажмите «Камера + IMU», задайте стартовую позу и нажмите «Запустить с этой позой».')
            elif op == 'camera.start':
                self.notice = 'Камера запущена. Дождитесь синхронизации IMU перед запуском локализации.'
        else:
            return
        self.changed.emit()

    def failed(self, op, error, context):
        if context.startswith('localisation:'):
            self.checking = False
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
            self.checking = self.checked = False
            self.timer.stop()
            self.available = False
            self.pending = False
            self.state = {}
            self.received = None
            self.notice = 'Нет соединения с роботом.'
            self.changed.emit()

    @Slot()
    def barrier(self):
        self.pending = self.checking = False
        self.changed.emit()

    def shutdown(self):
        self.timer.stop()
        self.clock.stop()
