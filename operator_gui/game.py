"""Explicit autonomous game controls; connection alone never starts a game."""
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
        running = self.state.get('running') is True
        pickup = self.state.get('pickup') is True
        paused = self.state.get('paused') is True
        reentry = fresh and running and pickup and self.state.get('pickup_ready') is True
        available = self.control.owns and not self.control.pending and not self.control.uncertain
        active = available and fresh and running and self.control.mode == 'GAME'
        blocked = self.control.blocked_reason
        if self.session.connected and self.control.mode == 'GAME':
            if fresh and self.state.get('running'):
                blocked = ('Можно выбрать роль и место повторного ввода.' if reentry else
                           'Игра уже запущена. Для нового ввода используйте Pick up или остановите игру.')
                if not self.control.owns:
                    blocked += ' Для остановки получите управление.'
            else:
                blocked = 'Робот в режиме GAME. Нажмите «Запросить статус», чтобы узнать состояние игры.'
        return dict(running=running, fresh=fresh,
                    state=self.state.get('state', 'Статус не запрошен'),
                    role=self.state.get('role') or '—', phase=self.state.get('phase') or '—',
                    recovery=self.state.get('recovery') or 'none',
                    recoveryAttempt=self.state.get('recovery_attempt', 0),
                    paused=paused, pickup=pickup, pickupReady=fresh and self.state.get('pickup_ready') is True,
                    confirmationRequired=fresh and self.state.get('pickup_confirmation_required') is True,
                    position=json.dumps(self.state.get('position'), ensure_ascii=False) if fresh else '—',
                    correction=json.dumps(self.state.get('last_correction'), ensure_ascii=False) if fresh else '—',
                    reason=self.state.get('reason') or '', error=self.error,
                    decision=self.state.get('decision', 'hold') if fresh else '—',
                    ball=json.dumps(ball, ensure_ascii=False) if fresh and ball else 'Нет актуального мяча',
                    travel=self.state.get('travel_m', 0), jobId=self.state.get('job_id') or '—',
                    pending=self.pending, canRefresh=self.session.connected and not self.pending,
                    watching='game.state' in self.data_sources.wanted,
                    subscriptionPending=any(t == 'game.state' for _, t in self.data_sources.pending),
                    canStart=(not self.control.blocked_reason and not running) or (active and reentry),
                    canPause=active and not paused and not pickup,
                    canResume=active and paused and not pickup,
                    canPickup=self.control.owns and self.control.mode == 'GAME' and not pickup
                        and self.control.pending not in ('game.pickup', 'game.stop', 'motion.stop_hard',
                                                         'control.release', 'control.acquire', 'mode.set'),
                    canConfirm=active and pickup and self.state.get('pickup_confirmation_required') is True,
                    canStop=self.control.owns and self.control.pending != 'game.stop',
                    blockedReason=blocked)

    @Slot(str, str, float)
    def start(self, strategy='FIRA_penalty_Goalkeeper', entry='center', delay_seconds=0.):
        body = dict(strategy=strategy)
        if strategy == 'forward':
            body['entry'] = entry
        if (isinstance(delay_seconds, bool) or not math.isfinite(delay_seconds)
                or not float(delay_seconds).is_integer() or not 0 <= delay_seconds <= 30):
            self.error = 'Задержка должна быть целым числом от 0 до 30 секунд.'
        elif strategy not in ('forward', 'FIRA_penalty_Goalkeeper') or entry not in ('center', 'left', 'right'):
            self.error = 'Неизвестная роль или место ввода.'
        elif not self.view['canStart']:
            self.error = self.view['blockedReason'] or 'Запуск сейчас недоступен.'
        elif self.control.command('game.start', body | dict(delay_seconds=int(delay_seconds)),
                                  manual=self.control.mode != 'GAME', context='game:start'):
            self.error = ''
        else:
            self.error = self.control.error
        self.changed.emit()

    @Slot()
    def pause(self):
        if self.view['canPause']:
            self._barrier('game.pause')

    @Slot()
    def resume(self):
        if self.view['canResume']:
            self.control.command('game.resume', {}, manual=False, job=False, context='game:resume')

    @Slot()
    def pickup(self):
        if self.view['canPickup']:
            self._barrier('game.pickup')

    @Slot()
    def confirmUpright(self):
        if self.view['canConfirm']:
            self.control.command('game.pickup', {'confirm': True}, manual=False, job=False,
                                 context='game:confirm')

    def _barrier(self, op):
        self.control.stopInput()
        self.control.barrierIssued.emit()
        self.control.pending = op
        self.control.poll_pending = False
        self.error = ''
        self.session.interrupt(op, {'lease_epoch': self.control.lease}, 'game:' + op.split('.')[1])
        self.control.changed.emit()

    @Slot()
    def stop(self):
        if not self.control.owns or self.control.pending == 'game.stop':
            return
        self._barrier('game.stop')

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

    def _connection(self):
        if not self.session.connected:
            self.state = {}
            self.received = 0.
            self.pending = False
        self.changed.emit()

    def _response(self, op, result, context):
        if op not in ('game.start', 'game.stop', 'game.status', 'game.pause', 'game.resume', 'game.pickup'):
            return
        if op == 'game.status':
            self.pending = False
        self.state = dict(result)
        self.received = time.monotonic()
        if op != 'game.status':
            self.error = ''
        if op in ('game.start', 'game.stop'):
            self.session.request('system.status')
        self.changed.emit()

    def _failed(self, op, message, context):
        if op.startswith('data.') and context == 'game.state':
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
