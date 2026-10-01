import tempfile
import time
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QTest

from operator_gui.controller import Controller
from tests.fake_robot import FakeRobot
from tests.test_operator import wait_until


class GameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.robot = FakeRobot()
        self.controller = Controller('127.0.0.1', self.robot.port, Path(self.tmp.name))
        self.game = self.controller.game
        self.control = self.controller.control

    def tearDown(self):
        self.controller.shutdown()
        self.robot.close()
        self.assertEqual(self.robot.errors, [])
        self.tmp.cleanup()

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
        self.assertIn('уже запущено', hint)
        self.assertIn('Остановить игру', hint)
        self.assertNotIn('слот', hint)
        self.assertNotIn('ручной режим', hint)

    def test_observe_and_physical_start_stop_keep_lease_and_unblock_manual(self):
        self.manual()
        for observe in (True, False):
            self.robot.values['game.geometry_verified'] = True
            self.game.start(observe, 2.)
            wait_until(lambda: self.game.view['running'] and self.control.mode == 'GAME')
            self.assertTrue(self.control.owns)
            self.assertFalse(self.control.view['ready'])
            self.assertTrue(self.game.view['canStop'])
            self.assertEqual(self.robot.game_observe_only, observe)
            wire = [m for m in self.robot.requests if m['op'] == 'game.start'][-1]['body']
            self.assertIs(type(wire['delay_seconds']), int)
            self.assertEqual(wire['delay_seconds'], 2)
            self.assertFalse(self.control.moving)
            self.game.stop()
            wait_until(lambda: not self.game.view['running'] and self.control.mode == 'MANUAL')
            self.assertFalse(self.control.pending)
            self.assertTrue(self.control.owns)

    def test_invalid_delay_and_missing_ownership_do_not_send(self):
        self.manual()
        for delay in (-1, 31, 1.5, True, float('nan')):
            self.game.start(True, delay)
        self.control.release()
        wait_until(lambda: not self.control.owns)
        self.game.start(True, 0)
        QTest.qWait(50)
        self.assertFalse(any(m['op'] == 'game.start' for m in self.robot.requests))
        self.assertTrue(self.game.view['error'])

    def test_poll_bounded_and_failure_visible(self):
        self.connect()
        self.game.refresh()
        self.game.refresh()
        wait_until(lambda: self.game.view['fresh'])
        self.assertEqual(len([m for m in self.robot.requests if m['op'] == 'game.status']), 1)
        self.controller.transport.failed.emit('game.start', 'invalid_state: geometry_unverified', 'game:start')
        self.assertIn('geometry_unverified', self.game.view['error'])
        self.game.received = time.monotonic()-3
        self.assertFalse(self.game.view['fresh'])
        self.assertEqual(self.game.view['decision'], '—')
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertFalse(self.game.timer.isActive())

    def test_strategy_job_is_not_manual_motion_and_errors_survive_poll(self):
        self.manual()
        self.controller.transport.response.emit('game.start', dict(running=True,
            state='starting', job_id='game1', accepted=True), 'game:start')
        self.assertFalse(self.control.moving)
        self.assertEqual(self.control.mode, 'GAME')
        self.controller.transport.failed.emit('game.start', 'geometry_unverified', 'game:start')
        self.controller.transport.response.emit('game.status', self.robot.game_state(), 'game:status')
        self.assertEqual(self.game.view['error'], 'geometry_unverified')

    def test_fake_rejects_fractional_wire_delay(self):
        self.robot.owner = self.robot.session
        self.robot.mode = 'MANUAL'
        with self.assertRaises(AssertionError):
            self.robot._result('game.start', dict(lease_epoch=self.robot.lease,
                strategy='FIRA_penalty_Goalkeeper', observe_only=True, delay_seconds=2.0))

    def test_game_start_timeout_budget(self):
        from operator_gui.transport import Transport
        from unittest.mock import patch
        transport = Transport()
        with patch('operator_gui.transport.time.monotonic', return_value=100):
            transport._send_request('game.start', {}, '')
        self.assertGreaterEqual(transport.pending[1]['expires'], 107)

    def test_observe_from_owned_idle_prepares_manual_without_motion(self):
        self.robot.game_running = False
        self.robot.mode = "IDLE"
        self.connect()
        self.control.acquire()
        wait_until(lambda: self.control.owns and not self.control.pending)
        self.robot.game_running = False
        self.assertEqual(self.control.mode, 'IDLE')
        self.assertTrue(self.game.view['canObserve'])
        self.assertFalse(self.game.view['canStart'])
        self.game.start(True, 0)
        wait_until(lambda: self.game.view['running'])
        ops = [m['op'] for m in self.robot.requests]
        self.assertLess(ops.index('mode.set'), ops.index('game.start'))
        self.assertFalse(any(op.startswith('motion.') for op in ops))
        self.assertTrue(self.robot.game_observe_only)

    def test_barrier_discards_prepared_observation(self):
        self.manual()
        self.game.prepared_start = (True, 0)
        self.game.barrier()
        self.game._response('mode.set', {'state': 'MANUAL'}, 'game:prepare-observation')
        QTest.qWait(30)
        self.assertFalse(any(m['op'] == 'game.start' for m in self.robot.requests))
