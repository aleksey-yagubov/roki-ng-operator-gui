"""Explicit diagnostic localization controls; stale candidates never look current."""
import math
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


def candidate_kind(result):
    pose = result.get('candidate')
    if not (isinstance(pose, list) and len(pose) == 3 and
            all(type(x) in (float, int) and math.isfinite(x) for x in pose)):
        return 'none'
    if (result.get('ambiguous') or result.get('fit_state') in ('weak', 'ambiguous', 'rejected')
            or result.get('reason') in ('motion_discontinuity', 'insufficient_observations')):
        return 'questionable'
    return 'usable'


class Localisation(QObject):
    changed = Signal()

    def __init__(self, session, control, data_sources, parent=None):
        super().__init__(parent)
        self.session, self.control = session, control
        self.data_sources = data_sources
        data_sources.sampleReceived.connect(self.sample)
        data_sources.changed.connect(self.changed.emit)
        self.available = False
        self.was_connected = session.connected
        self.state = {}
        self.received = None
        self.last_pose = []
        self.last_pose_at = None
        self.pending = False
        self.checking = False
        self.checked = False
        self.notice = 'Проверьте доступность локализации на роботе.'
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
        if type(age) not in (int, float) or not math.isfinite(age) or age < 0:
            age = None
        if age is not None and self.received is not None:
            age += round((time.monotonic()-self.received)*1000)
        pose = result.get('candidate')
        kind = candidate_kind(result)
        sane = kind != 'none'
        fresh = (self.session.connected and self.state.get('running', False) and
                 not self.state.get('error') and age is not None and 0 <= age <= 1500)
        current_pose = pose if fresh and kind == 'usable' else []
        last_age = (max(0, round((time.monotonic()-self.last_pose_at)*1000))
                    if self.last_pose_at is not None else None)
        reason = result.get('reason') or ''
        summary = ('Нет результата' if not result else
                   f"Недостаточно наблюдений (insufficient_observations): отрезков {result.get('lines', 0)}, требуется минимум 3"
                   if reason == 'insufficient_observations' else
                   'Отклонён скачок позиции (motion_discontinuity)' if reason == 'motion_discontinuity' else
                   'Неоднозначная позиция (ambiguous)' if result.get('ambiguous') or result.get('fit_state') == 'ambiguous' else
                   'Слабое совпадение разметки (weak)' if result.get('fit_state') == 'weak' else
                   'Оценка отклонена (rejected)' if result.get('fit_state') == 'rejected' else
                   'Согласованный диагностический кандидат (matched)' if kind == 'usable' else
                   'Позиция не определена')
        if result and not fresh:
            summary += ' · нет свежей оценки'
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
                    running=self.state.get('running', False),
                    watching='localisation.state' in self.data_sources.wanted,
                    subscribed='localisation.state' in self.data_sources.active,
                    subscriptionPending=any(t == 'localisation.state' for _, t in self.data_sources.pending),
                    notice=self.notice, error=self.state.get('error') or '',
                    pose=current_pose, ageMs=age,
                    lastPose=self.last_pose, lastPoseAgeMs=last_age,
                    questionablePose=pose if fresh and kind == 'questionable' else [],
                    resultSummary=summary, reason=reason,
                    fresh=fresh, result=result, geometry=self.state.get('geometry') or {},
                    configurationId=self.state.get('configuration_id') or '',
                    status=('Нет связи' if not self.session.connected else
                            'Проверяю возможности робота…' if self.checking else
                            'Нужно обновить сервис робота: локализация отсутствует' if self.checked and not self.available else
                            'Проверьте возможности робота' if not self.checked else
                            'Локализация доступна — не запущена' if not self.state.get('running') else
                            'Ошибка' if self.state.get('error') else
                            summary if reason == 'insufficient_observations' else
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
        if enabled:
            self.data_sources.subscribe_topic('localisation.state', 2)
        else:
            self.data_sources.unsubscribe_topic('localisation.state')

    def sample(self, topic, sample):
        if topic != 'localisation.state':
            return
        state = dict(sample['data'])
        age, transport_age = state.get('age_ms'), sample.get('age_ms')
        # Worker age is measured at its heartbeat; envelope age is elapsed since it.
        numeric = lambda v: type(v) in (int, float) and math.isfinite(v) and v >= 0
        state['age_ms'] = age + transport_age if numeric(age) and numeric(transport_age) else None
        result = state.get('result')
        if isinstance(result, dict):
            state['result'] = dict(result, valid=sample.get('valid') is True and result.get('valid') is True)
        else:
            state['result'] = None
        self.accept_state(state)
        self.notice = 'Получены данные localisation.state. Подписка общая для игры, карты и источников данных.'
        self.changed.emit()

    def accept_state(self, state):
        # Cached coordinates are display-only and belong to one capture/map.
        if any(state.get(k) != self.state.get(k) for k in ('capture_id', 'configuration_id', 'geometry')):
            self.last_pose = []
            self.last_pose_at = None
        self.state = dict(state)
        self.received = time.monotonic()
        result = state.get('result') or {}
        age = state.get('age_ms')
        if (candidate_kind(result) == 'usable' and state.get('running') and not state.get('error')
                and type(age) in (int, float) and math.isfinite(age) and age >= 0):
            self.last_pose = list(result['candidate'])
            self.last_pose_at = self.received - age / 1000

    def command(self, op, args, manual=True):
        if not self.control.command(op, args, manual=manual, job=False, context='localisation:action'):
            self.notice = self.control.error
            self.changed.emit()

    @Slot(float, float, float)
    def start(self, x, y, yaw_degrees):
        if not self.available:
            return
        if not all(math.isfinite(v) for v in (x, y, yaw_degrees)) or abs(yaw_degrees)>180:
            self.notice = 'Введите конечные координаты и угол от −180 до 180°.'
            self.changed.emit()
            return
        self.command('localisation.start', {'prior': [x, y, math.radians(yaw_degrees)]}, manual=self.control.mode != 'GAME')

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
                self.refresh()
        elif context in ('localisation:status', 'localisation:action'):
            if op.startswith('localisation.'):
                self.pending = False
                self.accept_state(result)
                self.notice = ('Локализация работает. Координаты: начало в центре, +X вдоль поля вверх, +Y влево; yaw от +X.'
                               if result.get('running') else
                               'Проверка успешна: робот поддерживает локализацию. Для запуска получите управление, '
                               'включите MANUAL, запустите захват в панели «Камера», задайте стартовую позу и нажмите «Запустить с этой позой».')
        else:
            return
        self.changed.emit()

    def failed(self, op, error, context):
        if context.startswith('localisation:') or (op.startswith('data.') and context == 'localisation.state'):
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
            self.available = False
            self.pending = False
            self.state = {}
            self.received = None
            self.last_pose = []
            self.last_pose_at = None
            self.notice = 'Нет соединения с роботом.'
            self.changed.emit()

    @Slot()
    def barrier(self):
        self.pending = self.checking = False
        self.changed.emit()

    def shutdown(self):
        self.clock.stop()
