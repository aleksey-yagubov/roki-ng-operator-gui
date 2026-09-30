import unittest
from PySide6.QtCore import Qt

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
        wait_until(lambda: c.headUi["known"])
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

    def test_keyboard_preference_survives_input_stop_and_disconnect(self):
        c = self.manual()
        c.setKeyboard(True)
        c.hold("forward", True)
        c._application_state(Qt.ApplicationState.ApplicationInactive)
        self.assertTrue(c.keyboard)
        self.assertFalse(c.held)
        wait_until(lambda: not c.drive_timer.isActive())
        c._application_state(Qt.ApplicationState.ApplicationActive)
        self.assertFalse(c.held)
        self.assertFalse(c.drive_timer.isActive())
        c.stop(True)
        wait_until(lambda: not c.pending)
        self.assertTrue(c.keyboard)
        c.release()
        wait_until(lambda: not c.owns)
        self.assertTrue(c.keyboard)
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertTrue(c.keyboard)
        self.assertFalse(c.held)
        c.setKeyboard(False)
        self.assertFalse(c.keyboard)

    def test_leave_manual_interrupts_job_but_keeps_control_and_keyboard(self):
        c = self.manual()
        c.setKeyboard(True)
        c.pose("crouch")
        wait_until(lambda: c.moving and not c.pending)
        ident = c.job["job_id"]
        c.leaveManual()
        wait_until(lambda: c.mode == "IDLE" and not c.pending)
        self.assertTrue(c.owns)
        self.assertTrue(c.keyboard)
        self.assertFalse(c.moving)
        self.assertFalse(c.held)
        self.assertFalse(c.view["manual"])
        self.assertEqual(self.robot.jobs[ident]["status"], "cancelled")
        self.assertEqual(self.robot.owner, self.robot.session)
        c.enterManual()
        wait_until(lambda: c.view["manual"] and not c.pending)
        self.assertFalse(c.held)

    def test_leave_manual_releases_held_drive(self):
        c = self.manual()
        c.hold("forward", True)
        c.leaveManual()
        wait_until(lambda: c.mode == "IDLE" and not c.pending)
        self.assertFalse(c.held)
        wait_until(lambda: not c.drive_timer.isActive())

    def test_jumps_and_turns_send_crouch_mode(self):
        c = self.manual()
        for crouch in ("off", "on", "centered"):
            c.driveSettings(0.5, crouch, False)
            for direction in ("forward", "backward", "left", "right", "turn_left", "turn_right"):
                with self.subTest(crouch=crouch, direction=direction):
                    c.jump(direction)
                    wait_until(lambda: c.moving and not c.pending)
                    request = [m for m in self.robot.requests if m["op"] == "motion.jump"][-1]
                    self.assertEqual(request["body"], dict(direction=direction, fraction=1.0,
                                                          crouch=crouch, lease_epoch=7))
                    c.stop(True)
                    wait_until(lambda: not c.moving and not c.pending)

    def test_drive_modes_heading_and_zero_samples(self):
        c = self.manual()
        self.assertEqual(c.driveUi, dict(speed=0.5, crouch="off", headingHold=False))
        for crouch in ("off", "on", "centered"):
            for heading in (False, True):
                c.driveSettings(0.7, crouch, heading)
                begin = len(self.robot.requests)
                c.hold("forward", True)
                wait_until(lambda: any(m["op"] == "motion.drive" for m in self.robot.requests[begin:]))
                c.hold("forward", False)
                wait_until(lambda: sum(m["op"] == "motion.drive" and m["body"]["x"] == 0
                                      for m in self.robot.requests[begin:]) == 3)
                for request in self.robot.requests[begin:]:
                    if request["op"] == "motion.drive":
                        self.assertEqual(request["body"]["crouch"], crouch)
                        self.assertIs(request["body"]["heading_hold"], heading)
                        self.assertNotIn("hold_crouch", request["body"])
                        self.assertNotIn("auto_prepare", request["body"])

    def test_get_up_splits_crouch_and_busy_rejection(self):
        c = self.manual()
        for crouch in ("off", "on", "centered"):
            c.driveSettings(0.5, crouch, True)
            for action, op, args in (
                    (c.getUp, "motion.get_up", {"crouch": crouch}),
                    (lambda: c.splits("small"), "motion.splits", {"kind": "small", "crouch": crouch}),
                    (lambda: c.splits("big"), "motion.splits", {"kind": "big", "crouch": crouch}),
                    (lambda: c.pose("crouch"), "motion.pose",
                     {"name": "crouch", "crouch": "centered" if crouch == "centered" else "on"})):
                action()
                wait_until(lambda: c.moving and not c.pending)
                request = [m for m in self.robot.requests if m["op"] == op][-1]
                self.assertEqual(request["body"], dict(args, lease_epoch=7))
                before = sum(m["op"].startswith("motion.") for m in self.robot.requests)
                c.getUp()
                c.splits("big")
                self.assertEqual(sum(m["op"].startswith("motion.") for m in self.robot.requests), before)
                c.stop(True)
                wait_until(lambda: not c.moving and not c.pending)

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
        c.head(300, -500)
        wait_until(lambda: not c.pending and c.head_target == {"pan": 300, "tilt": -500})
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

    def test_head_draft_is_not_applied_by_arrows_or_axis_reset(self):
        c = self.manual()
        c.head(300, -500)
        wait_until(lambda: not c.pending)
        c.setHeadUi(1500, -1000)
        c.nudgeHead("up")
        wait_until(lambda: not c.pending)
        request = [m for m in self.robot.requests if m["op"] == "motion.head"][-1]
        self.assertEqual(request["body"], {"tilt": -250, "frames": 10, "lease_epoch": 7})
        self.assertEqual(self.robot.head, {"pan": 300, "tilt": -250})
        c.setHeadUi(-1500, -2000)
        c.resetHeadAxis("pan")
        wait_until(lambda: not c.pending)
        self.assertEqual(self.robot.head, {"pan": 0, "tilt": -250})
        request = [m for m in self.robot.requests if m["op"] == "motion.head"][-1]
        self.assertNotIn("tilt", request["body"])
        c.setHeadUi(1000, -2000)
        c.resetHeadAxis("tilt")
        wait_until(lambda: not c.pending)
        self.assertEqual(self.robot.head, {"pan": 0, "tilt": 0})

    def test_head_snapshot_keeps_draft_and_rejects_stale_state(self):
        c = self.manual()
        c.job_timer.stop()
        c.setHeadUi(1200, -1800)
        c.refreshHead()
        wait_until(lambda: not c.head_sync)
        self.assertEqual((c.pan, c.tilt), (1200, -1800))
        self.assertTrue(c.head_dirty)
        self.assertEqual(c.head_target, {"pan": 0, "tilt": 0})
        c.head(300, -500)
        c.setHeadUi(1000, -1000)  # Edit again before the previous command replies.
        wait_until(lambda: not c.pending)
        self.assertEqual((c.pan, c.tilt), (1000, -1000))
        self.assertEqual(c.head_target, {"pan": 300, "tilt": -500})
        c.head_sync = f"head-state:{c.head_revision}"
        c.head_requested_at = c.head_since + 0.1
        c._response("data.snapshot", dict(self.robot.sample("motion.state"), age_ms=500,
                    data={"head": {"pan": 0, "tilt": 0}}), c.head_sync)
        self.assertEqual(c.head_target, {"pan": 300, "tilt": -500})
        self.assertEqual(self.controller.data_sources.error, "")

    def test_head_updates_after_pose_and_drops_old_session_state(self):
        c = self.manual()
        for name, target in (("head_field", {"pan": 0, "tilt": -1500}),
                             ("base_stand", {"pan": 0, "tilt": 0})):
            c.pose(name)
            wait_until(lambda: c.moving and not c.pending)
            self.assertFalse(c.headUi["canNudge"])
            self.robot.head = target.copy()
            self.robot.jobs[c.job["job_id"]]["status"] = "completed"
            c.refreshJob()
            wait_until(lambda: not c.moving)
            wait_until(lambda: c.head_target == target and c.headUi["canNudge"])
            self.assertEqual((c.pan, c.tilt), (target["pan"], target["tilt"]))
        old_context = f"head-state:{c.head_revision}"
        self.controller.disconnectRobot()
        wait_until(lambda: not c.owns)
        self.assertFalse(c.headUi["known"])
        c._response("data.snapshot", self.robot.sample("motion.state"), old_context)
        self.assertFalse(c.headUi["known"])
        self.robot.head = {"pan": -300, "tilt": -900}
        self.connect()
        c.acquire()
        wait_until(lambda: c.owns and not c.pending)
        c.enterManual()
        wait_until(lambda: c.head_target == self.robot.head)
        self.assertEqual((c.pan, c.tilt), (-300, -900))


class ScalarTests(unittest.TestCase):
    def test_types_limits(self):
        self.assertEqual(scalar({"type": "float", "min": 0, "max": 1}, "0,5"), 0.5)
        for bad in ("nan", "inf", "1.5", True, "100"):
            with self.assertRaises(ValueError):
                scalar({"type": "int", "min": -2, "max": 2}, bad)
