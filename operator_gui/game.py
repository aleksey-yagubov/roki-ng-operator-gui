"""Explicit FIRA goalkeeper controls; connection alone never starts a game."""
import json
import math
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot


class Game(QObject):
    changed = Signal()

    def __init__(self, session, control, data_sources, parent=None):
        super().__init__(parent)
        self.session, self.control = session, control
        self.data_sources = data_sources
        data_sources.sampleReceived.connect(self._sample)
        data_sources.changed.connect(self.changed.emit)
        self.state = {}
        self.error = ""
        self.pending = False
        self.received = 0.
        self.prepared_start = None
        self.clock = QTimer(self)
        self.clock.setInterval(250)
        self.clock.timeout.connect(self.changed.emit)
        self.clock.start()
        session.response.connect(self._response)
        session.failed.connect(self._failed)
        session.changed.connect(self._connection)
        control.changed.connect(self.changed.emit)
        control.barrierIssued.connect(self.barrier)

    @Property('QVariantMap', notify=changed)
    def view(self):
        fresh = self.session.connected and self.received > 0 and time.monotonic()-self.received < 2
        ball = self.state.get('ball')
        can_prepare = (self.control.owns and self.control.mode == 'IDLE'
                       and not self.control.pending and not self.control.uncertain
                       and not self.control.moving and not self.control.held)
        blocked = self.control.blocked_reason
        if self.session.connected and self.control.mode == 'GAME':
            if fresh and self.state.get('running'):
                mode = 'Наблюдение уже запущено' if self.state.get('observe_only') else 'Игра с движениями уже запущена'
                blocked = mode + '. Для нового запуска сначала нажмите «Остановить игру».'
                if not self.control.owns:
                    blocked += ' Для остановки получите управление.'
            else:
                blocked = 'Робот в режиме GAME. Нажмите «Запросить статус», чтобы узнать состояние игры.'
        return dict(running=self.state.get('running') is True, fresh=fresh,
                    state=self.state.get('state', 'Статус не запрошен'),
                    observeOnly=self.state.get('observe_only', True),
                    reason=self.state.get('reason') or '', error=self.error,
                    decision=self.state.get('decision', 'hold') if fresh else '—',
                    ball=json.dumps(ball, ensure_ascii=False) if fresh and ball else 'Нет актуального мяча',
                    travel=self.state.get('travel_m', 0), jobId=self.state.get('job_id') or '—',
                    pending=self.pending, canRefresh=self.session.connected and not self.pending,
                    watching='game.state' in self.data_sources.wanted,
                    subscriptionPending=any(t == 'game.state' for _, t in self.data_sources.pending),
                    canStart=not self.control.blocked_reason and not self.state.get('running', False),
                    canObserve=(can_prepare or not self.control.blocked_reason)
                        and not self.state.get('running', False) and self.prepared_start is None,
                    canStop=self.control.owns and self.control.pending != 'game.stop',
                    blockedReason=blocked)

    @Slot(bool, float)
    def start(self, observe_only=True, delay_seconds=0.):
        if (isinstance(delay_seconds, bool) or not math.isfinite(delay_seconds)
                or not float(delay_seconds).is_integer() or not 0 <= delay_seconds <= 30):
            self.error = 'Задержка должна быть целым числом от 0 до 30 секунд.'
        elif self.state.get('running'):
            self.error = 'Сначала остановите текущую игру.'
        elif observe_only and self.control.mode == 'IDLE' and self.view['canObserve']:
            self.prepared_start = (True, int(delay_seconds))
            if self.control.command('mode.set', {'mode': 'MANUAL'}, manual=False,
                                    context='game:prepare-observation'):
                self.error = ''
            else:
                self.prepared_start = None
                self.error = self.control.error
        elif self.control.command('game.start', dict(strategy='FIRA_penalty_Goalkeeper',
                observe_only=observe_only, delay_seconds=int(delay_seconds)), context='game:start'):
            self.error = ''
        else:
            self.error = self.control.error
        self.changed.emit()

    @Slot()
    def stop(self):
        if not self.control.owns or self.control.pending == 'game.stop':
            return
        self.control.stopInput()
        self.control.barrierIssued.emit()
        self.control.pending = 'game.stop'
        self.control.poll_pending = False
        self.error = ''
        self.session.interrupt('game.stop', {'lease_epoch': self.control.lease}, 'game:stop')
        self.control.changed.emit()

    @Slot()
    def refresh(self):
        if self.session.connected and not self.pending:
            self.pending = True
            self.session.request('game.status', {}, 'game:status')
            self.changed.emit()

    @Slot(bool)
    def watch(self, enabled):
        if enabled:
            self.data_sources.subscribe_topic('game.state', 2)
        else:
            self.data_sources.unsubscribe_topic('game.state')

    def _sample(self, topic, sample):
        if topic != 'game.state':
            return
        self.state = dict(sample['data'])
        age = sample.get('age_ms')
        valid_age = type(age) in (int, float) and math.isfinite(age) and age >= 0
        self.received = time.monotonic() - age / 1000 if sample.get('valid') is True and valid_age else 0.
        self.changed.emit()

    def barrier(self):
        self.pending = False
        self.prepared_start = None

    def _connection(self):
        if not self.session.connected:
            self.prepared_start = None
            self.state = {}
            self.received = 0.
            self.pending = False
        self.changed.emit()

    def _response(self, op, result, context):
        if context == 'game:prepare-observation':
            prepared, self.prepared_start = self.prepared_start, None
            if prepared is not None:
                if result.get('state') == 'MANUAL' and self.control.owns:
                    self.start(*prepared)
                else:
                    self.error = 'Не удалось подготовить режим наблюдения.'
            self.changed.emit()
            return
        if op not in ('game.start', 'game.stop', 'game.status'):
            return
        if op == 'game.status':
            self.pending = False
        self.state = dict(result)
        self.received = time.monotonic()
        if op in ('game.start', 'game.stop'):
            self.error = ''
        if op in ('game.start', 'game.stop'):
            self.session.request('system.status')
        self.changed.emit()

    def _failed(self, op, message, context):
        if op.startswith('data.') and context == 'game.state':
            self.error = message
            self.changed.emit()
            return
        if context == 'game:prepare-observation':
            self.prepared_start = None
            self.error = message
            self.changed.emit()
            return
        if op.startswith('game.'):
            self.pending = False
            self.error = message
            if op == 'game.start' and 'outcome unknown' in message:
                self.refresh()
            self.changed.emit()

    def shutdown(self):
        self.clock.stop()
