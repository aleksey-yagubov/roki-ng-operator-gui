import unittest

from operator_gui.control import scalar
from tests import test_operator
from tests.test_operator import wait_until


class ControlTests(unittest.TestCase):
    setUpClass = classmethod(test_operator.OperatorTests.setUpClass.__func__)
    setUp = test_operator.OperatorTests.setUp
    tearDown = test_operator.OperatorTests.tearDown
    connect = test_operator.OperatorTests.connect
    def manual(self):
        self.connect()
        c = self.controller.control
        c.acquire()
        wait_until(lambda: c.owns)
        self.assertEqual(self.robot.mode, "GAME")
        c.enterManual()
        wait_until(lambda: c.view["manual"] and not c.pending)
        return c

    def test_explicit_lease_and_no_motion_backlog(self):
        c = self.manual()
        c.pose("base_stand")
        for _ in range(10):
            c.jump("turn_left")
        wait_until(lambda: c.moving and not c.pending)
        self.assertEqual([m["op"] for m in self.robot.requests if m["op"].startswith("motion.")], ["motion.pose"])
        c.stop(True)
        wait_until(lambda: not c.pending and not c.moving)
        c.jump("turn_left")
        wait_until(lambda: c.moving and not c.pending)
        c.release()
        wait_until(lambda: not c.owns)
        self.assertEqual(self.robot.owner, None)

    def test_drive_stops_on_release_and_never_replays_after_disconnect(self):
        c = self.manual()
        c.hold("forward", True)
        wait_until(lambda: sum(m["op"] == "motion.drive" for m in self.robot.requests) >= 3)
        c.hold("forward", False)
        wait_until(lambda: sum(m["op"] == "motion.drive" and m["body"]["x"] == 0 for m in self.robot.requests) == 3)
        samples = [m for m in self.robot.requests if m["op"] == "motion.drive"]
        self.assertEqual([m["sequence"] for m in samples], list(range(1, len(samples) + 1)))
        c.hold("forward", True)
        self.controller.disconnectRobot()
        wait_until(lambda: not c.owns)
        self.assertFalse(c.held)

    def test_parameter_validation_and_schema_test_forms(self):
        c = self.manual()
        self.controller.inspectParameter("head.field_tilt")
        wait_until(lambda: "value" in self.controller.param_parts)
        self.controller.saveParameter("head.field_tilt", "90000")
        self.assertNotIn("head.field_tilt", self.robot.values)
        self.controller.saveParameter("head.field_tilt", "-1100")
        wait_until(lambda: self.controller.param_parts["value"] == -1100)
        self.controller.requestCatalog("tests")
        wait_until(lambda: len(self.controller.test_schemas) == 4)
        self.controller.startTest("run_test", {"mode": "short", "cycles": 90, "right_leg": False})
        wait_until(lambda: c.moving)
        start = next(m for m in self.robot.requests if m["op"] == "test.start")
        self.assertEqual(start["body"], {"lease_epoch": 7, "name": "run_test", "mode": "short"})
        c.stop(True)
        wait_until(lambda: not c.moving and not c.pending)
        self.controller.startTest("run_test", {"mode": "custom", "cycles": "4", "right_leg": False})
        wait_until(lambda: c.moving)
        start = [m for m in self.robot.requests if m["op"] == "test.start"][-1]
        self.assertEqual(start["body"]["cycles"], 4)
        self.assertIs(start["body"]["right_leg"], False)

    def test_unknown_outcome_blocks_new_motion_until_stop(self):
        c = self.manual()
        c.pending = "motion.jump"
        c._failed("motion.jump", "Response timeout (operation outcome unknown)", "")
        before = len(self.robot.requests)
        c.jump("forward")
        self.assertTrue(c.uncertain)
        self.assertFalse(c.view["ready"])
        self.assertEqual(len(self.robot.requests), before)
        c.stop(True)
        wait_until(lambda: not c.pending)
        self.assertFalse(c.uncertain)

    def test_head_reset_and_directions(self):
        c = self.manual()
        c.setHeadUi(300, -500)
        c.adjustHead(0, -250)
        wait_until(lambda: c.tilt == -750)
        c.head(0, 0)
        wait_until(lambda: c.pan == 0 and c.tilt == 0)
        self.assertEqual(c.headUi["pan"], 0)
        c.nudgeHead("up")
        wait_until(lambda: c.tilt == 250 and not c.pending)
        c.nudgeHead("down")
        wait_until(lambda: c.tilt == 0 and not c.pending)
        c.nudgeHead("left")
        wait_until(lambda: c.pan == 250 and not c.pending)
        c.nudgeHead("right")
        wait_until(lambda: c.pan == 0 and not c.pending)


class ScalarTests(unittest.TestCase):
    def test_types_limits(self):
        self.assertEqual(scalar({"type": "float", "min": 0, "max": 1}, "0,5"), 0.5)
        for bad in ("nan", "inf", "1.5", True, "100"):
            with self.assertRaises(ValueError):
                scalar({"type": "int", "min": -2, "max": 2}, bad)
