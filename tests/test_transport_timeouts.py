import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication

from operator_gui.transport import Transport


class StartupTimeoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_localisation_waits_for_server_startup_but_remains_bounded(self):
        transport = Transport()
        failures = []
        transport.failed.connect(lambda *args: failures.append(args))
        with patch("operator_gui.transport.time.monotonic", return_value=100):
            transport._send_request("localisation.start", {}, "startup")
        # Exhaust UDP retries while allowing the server's 5-second worker call.
        for elapsed in (0.25, 0.5, 0.75, 1.0, 1.3, 5.5):
            with patch("operator_gui.transport.time.monotonic", return_value=100 + elapsed):
                transport._tick()
        self.assertEqual(failures, [])
        self.assertEqual(len(transport.pending), 1)
        with patch("operator_gui.transport.time.monotonic", return_value=107.1):
            transport._tick()
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0][0], "localisation.start")
        self.assertEqual(transport.pending, {})
