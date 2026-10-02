import tempfile
import socket
import threading
import time
import unittest
import gc
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QThread, QTimer
from PySide6.QtTest import QTest

from operator_gui.controller import Controller
from tests.fake_robot import FakeRobot
from operator_gui.transport import envelope


def wait_until(predicate, timeout=3000):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(timeout)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "Timed out waiting for condition"


class OperatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        # Collect previous Qt fixtures outside an active event dispatch.
        gc.collect()
        self.tmp = tempfile.TemporaryDirectory()
        self.robot = FakeRobot()
        self.controller = Controller("127.0.0.1", self.robot.port, Path(self.tmp.name))

    def tearDown(self):
        self.controller.shutdown()
        self.robot.close()
        self.assertEqual(self.robot.errors, [])
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.tmp.cleanup()

    def connect(self):
        self.controller.connectRobot("127.0.0.1", self.robot.port)
        wait_until(lambda: self.controller.transport.connected)
        wait_until(lambda: any(m["op"] == "log.subscribe" for m in self.robot.requests))
        wait_until(lambda: "body.power" in self.controller.data_sources.active)

    def test_connection_is_observation_and_worker_is_separate(self):
        QTest.qWait(150)
        self.assertEqual(self.robot.requests, [])
        self.connect()
        wait_until(lambda: any(m["op"] == "session.heartbeat" for m in self.robot.requests))
        self.assertEqual({m["op"] for m in self.robot.requests},
                         {"hello", "log.subscribe", "session.heartbeat", "data.subscribe"})
        self.assertEqual([m["body"] for m in self.robot.requests if m["op"] == "data.subscribe"],
                         [{"topic": "body.power", "rate_hz": 1}])
        self.assertEqual(self.controller.transport.session, 2**60 + 123)
        self.assertNotEqual(self.controller.transport.worker.thread(), QThread.currentThread())
        self.assertEqual(self.controller.logs.thread(), QThread.currentThread())
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        wait_until(lambda: any(m["op"] == "session.close" for m in self.robot.requests))
        self.assertTrue(self.robot.game_running)
        self.assertFalse(any(m["op"] in ("mode.set", "motion.stop_hard", "motion.stop_graceful") for m in self.robot.requests))

    def test_catalogs_parameters_and_exact_retry(self):
        self.connect()
        self.robot.drop_once.add("system.status")
        self.controller.requestStatus()
        wait_until(lambda: self.controller.last_status_at is not None)
        requests = [m for m in self.robot.requests if m["op"] == "system.status"]
        self.assertGreaterEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])
        self.controller.requestCatalog("slots")
        wait_until(lambda: self.controller.slots.rowCount() == 57)
        self.controller.requestCatalog("tests")
        wait_until(lambda: self.controller.tests.rowCount() == 4)
        self.controller.requestCatalog("parameters")
        wait_until(lambda: self.controller.parameters.rowCount() == 3)
        self.controller.inspectParameter("head.field_tilt")
        wait_until(lambda: "value" in self.controller.param_parts and "description" in self.controller.param_parts)
        self.assertEqual(self.controller.param_parts["value"], -1500)

    def test_rtt_and_video_responses_do_not_invalidate_unrelated_panels(self):
        self.connect()
        c = self.controller
        wait_until(lambda: c.control.mode == c.mode)
        changes = []
        c.changed.connect(lambda: changes.append("controller"))
        c.control.changed.connect(lambda: changes.append("control"))
        c.camera.changed.connect(lambda: changes.append("camera"))
        session = c.transport
        state = dict(phase=session.phase, invalid_packets=session.invalid_packets,
                     session=session.session, rtt_ms=1.)
        for i in range(100):
            session._state(dict(state, rtt_ms=float(i)))
            session.response.emit("videostream.list", {"items": []}, "streams:unused")
            session.response.emit("session.heartbeat", {"state": c.control.mode}, "")
        self.assertEqual(changes, [])
        self.assertEqual(session.rtt_ms, 99.)

    def test_logs_pause_filter_gap_and_bounds(self):
        self.connect()
        self.robot.send_log("first")
        wait_until(lambda: any(r["message"] == "first" for r in self.controller.history))
        self.controller.pauseLogs(True)
        before = self.controller.logs.rowCount()
        self.robot.send_log("second", "ERROR", skip=2)
        wait_until(lambda: any(r["message"] == "second" for r in self.controller.history))
        self.assertEqual(self.controller.logs.rowCount(), before)
        self.assertEqual(self.controller.gaps, 2)
        self.controller.pauseLogs(False)
        self.controller.log_filter.configure("ERROR", "second", "camera")
        self.assertEqual(self.controller.log_filter.rowCount(), 1)
        for i in range(2100):
            self.controller._log("DEBUG", str(i))
        self.assertEqual(len(self.controller.history), 2000)
        self.assertEqual(self.controller.logs.rowCount(), 2000)

    def test_loss_does_not_block_ui_or_reconnect(self):
        self.connect()
        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()
        self.robot.silent = True
        self.controller.requestStatus()
        wait_until(lambda: self.controller.transport.phase == "lost", 4000)
        timer.stop()
        self.assertGreater(len(ticks), 50)
        QTest.qWait(300)
        self.assertEqual(sum(m["op"] == "hello" for m in self.robot.requests), 1)
        self.assertTrue(self.robot.game_running)

    def test_spoofed_and_oversized_datagrams_are_ignored(self):
        self.connect()
        self.robot.sock.sendto(b"x" * 1300, self.robot.client)
        wait_until(lambda: any("Invalid datagrams" in r["message"] for r in self.controller.history))
        forged = envelope("event", "FORGED", {}, 0, self.robot.session, self.robot.token + 1)
        self.robot._send(forged)
        import msgpack
        forged["token"] = self.robot.token
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as other:
            other.sendto(msgpack.packb(forged, use_bin_type=True), self.robot.client)
        self.robot.send_log("valid after invalid")
        wait_until(lambda: any(r["message"] == "valid after invalid" for r in self.controller.history))
        self.assertTrue(self.controller.transport.connected)
        self.assertFalse(any("FORGED" in r["message"] for r in self.controller.history))

    def test_log_burst_keeps_gui_event_loop_responsive(self):
        self.connect()
        ticks = []
        timer = QTimer()
        timer.setInterval(20)
        timer.timeout.connect(lambda: ticks.append(time.monotonic()))
        timer.start()

        def burst():
            for i in range(1000):
                self.robot.send_log(f"burst-{i}")

        sender = threading.Thread(target=burst)
        sender.start()
        try:
            wait_until(lambda: not sender.is_alive(), 5000)
        finally:
            sender.join(2)
        wait_until(lambda: len(ticks) >= 30)
        timer.stop()
        self.assertTrue(self.controller.transport.connected)
        self.assertLess(max(b - a for a, b in zip(ticks, ticks[1:])), 0.5)
        self.assertLessEqual(len(self.controller.history), 2000)


if __name__ == "__main__":
    unittest.main()
