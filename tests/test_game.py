import time
import unittest

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from tests import test_operator
from tests.test_operator import wait_until


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        test_operator.OperatorTests.setUp(self)
        self.game = self.controller.game
        self.control = self.controller.control

    def tearDown(self):
        # Drain deferred QObject deletion outside event dispatch, just like the
        # other Controller fixtures; leaving it to cyclic GC can crash Qt.
        test_operator.OperatorTests.tearDown(self)

    def connect(self):
        self.controller.connectRobot('127.0.0.1', self.robot.port)
        wait_until(lambda: self.controller.transport.connected)

    def manual(self):
        self.connect()
        self.control.acquire()
        wait_until(lambda: self.control.owns)
        self.control.enterManual()
        wait_until(lambda: self.control.mode == 'MANUAL' and not self.control.pending)
        self.robot.game_running = False

    def test_connection_never_starts_or_polls_game(self):
        self.connect()
        QTest.qWait(600)
        self.assertFalse(any(m['op'].startswith('game.') for m in self.robot.requests))

    def test_read_only_status_without_lease(self):
        self.connect()
        self.game.refresh()
        wait_until(lambda: self.game.view['fresh'])
        self.assertTrue(self.game.view['running'])
        self.assertFalse(self.game.view['canStart'])
        self.assertFalse(self.game.view['canStop'])
        self.assertIsNone(self.robot.owner)

    def test_game_hint_explains_status_instead_of_manual_tests(self):
        self.connect()
        self.assertIn('Запросить статус', self.game.view['blockedReason'])
        self.game.refresh()
        wait_until(lambda: self.game.view['fresh'])
        hint = self.game.view['blockedReason']
        self.assertIn('уже запущена', hint)
        self.assertIn('Pick up', hint)
        self.assertNotIn('слот', hint)
        self.assertNotIn('ручной режим', hint)

    def test_roles_start_stop_keep_lease_and_unblock_manual(self):
        self.manual()
        for role in ('FIRA_penalty_Goalkeeper', 'forward'):
            self.game.start(role, 'left', 2.)
            wait_until(lambda: self.game.view['running'] and self.control.mode == 'GAME')
            self.assertTrue(self.control.owns)
            self.assertFalse(self.control.view['ready'])
            self.assertTrue(self.game.view['canStop'])
            self.assertEqual(self.robot.game_role, role)
            wire = [m for m in self.robot.requests if m['op'] == 'game.start'][-1]['body']
            self.assertIs(type(wire['delay_seconds']), int)
            self.assertEqual(wire['delay_seconds'], 2)
            self.assertEqual(wire.get('entry'), 'left' if role == 'forward' else None)
            self.assertFalse(self.control.moving)
            self.game.stop()
            wait_until(lambda: not self.game.view['running'] and self.control.mode == 'MANUAL')
            self.assertFalse(self.control.pending)
            self.assertTrue(self.control.owns)

    def test_invalid_delay_and_missing_ownership_do_not_send(self):
        self.manual()
        for delay in (-1, 31, 1.5, True, float('nan')):
            self.game.start('forward', 'center', delay)
        self.control.release()
        wait_until(lambda: not self.control.owns)
        self.game.start('forward', 'center', 0)
        QTest.qWait(50)
        self.assertFalse(any(m['op'] == 'game.start' for m in self.robot.requests))
        self.assertTrue(self.game.view['error'])

    def test_status_request_bounded_and_failure_visible(self):
        self.connect()
        self.game.refresh()
        self.game.refresh()
        wait_until(lambda: self.game.view['fresh'])
        self.assertEqual(len([m for m in self.robot.requests if m['op'] == 'game.status']), 1)
        self.controller.transport.failed.emit('game.start', 'not_ready: Body unavailable', 'game:start')
        self.assertIn('Body unavailable', self.game.view['error'])
        self.game.received = time.monotonic()-3
        self.assertFalse(self.game.view['fresh'])
        self.assertEqual(self.game.view['decision'], '—')
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertFalse(self.game.view['watching'])

    def test_game_state_subscription_without_lease_or_periodic_status(self):
        self.connect()
        self.game.watch(True)
        wait_until(lambda: 'game.state' in self.controller.data_sources.active)
        self.game.watch(True)
        self.robot.send_data('game.state', 1)
        wait_until(lambda: self.game.view['fresh'])
        self.assertTrue(self.game.view['running'])
        QTest.qWait(650)
        self.assertFalse(any(m['op'].startswith('game.') for m in self.robot.requests))
        self.assertEqual(sum(m['op'] == 'data.subscribe' and m['body']['topic'] == 'game.state'
                             for m in self.robot.requests), 1)
        self.assertIsNone(self.robot.owner)
        self.game.watch(False)
        wait_until(lambda: not self.game.view['watching'])
        self.assertTrue(self.robot.game_running)

    def test_explicit_status_does_not_start_polling(self):
        self.connect()
        self.game.refresh()
        wait_until(lambda: self.game.view['fresh'])
        QTest.qWait(650)
        self.assertEqual(sum(m['op'] == 'game.status' for m in self.robot.requests), 1)

    def test_strategy_job_is_not_manual_motion_and_errors_survive_status(self):
        self.manual()
        self.controller.transport.response.emit('game.start', dict(running=True,
            state='starting', job_id='game1', accepted=True), 'game:start')
        self.assertFalse(self.control.moving)
        self.assertEqual(self.control.mode, 'GAME')
        self.controller.transport.failed.emit('game.start', 'Body unavailable', 'game:start')
        self.controller.transport.response.emit('game.status', self.robot.game_state(), 'game:status')
        self.assertEqual(self.game.view['error'], 'Body unavailable')

    def test_fake_rejects_fractional_wire_delay(self):
        self.robot.owner = self.robot.session
        self.robot.mode = 'MANUAL'
        with self.assertRaises(AssertionError):
            self.robot._result('game.start', dict(lease_epoch=self.robot.lease,
                strategy='FIRA_penalty_Goalkeeper', delay_seconds=2.0))

    def test_game_timeout_allows_finite_job_cleanup(self):
        from operator_gui.transport import Transport
        from unittest.mock import patch
        transport = Transport()
        with patch('operator_gui.transport.time.monotonic', return_value=100):
            for op in ('game.start', 'game.stop', 'game.pause', 'game.pickup'):
                transport._send_request(op, {}, '')
        for request in transport.pending.values():
            minimum = 135 if request['op'] in ('game.start', 'game.stop') else 106
            self.assertGreaterEqual(request['expires'], minimum)

    def test_pickup_cannot_replace_pending_hard_stop_or_release(self):
        self.manual()
        self.game.start('forward', 'left', 0)
        wait_until(lambda: self.game.view['running'] and not self.control.pending)
        for op in ('motion.stop_hard', 'game.stop', 'control.release'):
            self.control.pending = op
            self.assertFalse(self.game.view['canPickup'])
            self.game.pickup()
        QTest.qWait(30)
        self.assertFalse(any(m['op'] == 'game.pickup' for m in self.robot.requests))

    def test_idle_start_never_implicitly_changes_mode(self):
        self.robot.game_running = False
        self.robot.mode = "IDLE"
        self.connect()
        self.control.acquire()
        wait_until(lambda: self.control.owns and not self.control.pending)
        self.robot.game_running = False
        self.assertEqual(self.control.mode, 'IDLE')
        self.assertFalse(self.game.view['canStart'])
        self.game.start('forward', 'center', 0)
        QTest.qWait(50)
        ops = [m['op'] for m in self.robot.requests]
        self.assertNotIn('mode.set', ops)
        self.assertNotIn('game.start', ops)
        self.assertFalse(any(op.startswith('motion.') for op in ops))

    def test_pause_resume_pickup_and_reentry_share_current_contract(self):
        self.manual()
        self.game.start('forward', 'left', 0)
        wait_until(lambda: self.game.view['canPause'])
        self.game.pause()
        wait_until(lambda: self.game.view['canResume'])
        self.assertFalse(self.control.moving)
        self.game.resume()
        wait_until(lambda: self.game.view['canPause'])
        self.robot.game_confirm = True
        self.game.pickup()
        wait_until(lambda: self.game.view['canConfirm'])
        self.assertFalse(self.game.view['canStart'])
        self.assertFalse(self.game.view['canResume'])
        self.game.confirmUpright()
        wait_until(lambda: self.game.view['pickupReady'])
        self.assertTrue(self.game.view['canStart'])
        self.game.start('forward', 'right', 0)
        wait_until(lambda: self.robot.game_entry == 'right' and not self.control.pending)
        self.assertFalse(self.game.view['pickup'])
        self.assertTrue(self.control.owns)

    def test_stale_pickup_ready_does_not_authorize_reentry_or_confirmation(self):
        self.manual()
        self.game.start('forward', 'center', 0)
        wait_until(lambda: self.game.view['running'])
        self.game.pickup()
        wait_until(lambda: self.game.view['pickupReady'])
        self.game.received = time.monotonic() - 3
        self.assertFalse(self.game.view['canStart'])
        self.assertFalse(self.game.view['canConfirm'])
        starts = sum(m['op'] == 'game.start' for m in self.robot.requests)
        self.game.start('forward', 'right', 0)
        QTest.qWait(30)
        self.assertEqual(sum(m['op'] == 'game.start' for m in self.robot.requests), starts)
