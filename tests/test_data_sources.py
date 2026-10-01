import unittest

from operator_gui.data_sources import fields
from tests import test_operator
from tests.test_operator import wait_until


class DataSourcesTests(unittest.TestCase):
    setUpClass = classmethod(test_operator.OperatorTests.setUpClass.__func__)
    setUp = test_operator.OperatorTests.setUp
    tearDown = test_operator.OperatorTests.tearDown
    connect = test_operator.OperatorTests.connect

    def sources(self):
        self.connect()
        data = self.controller.data_sources
        self.assertFalse(data.wanted)
        data.requestList()
        wait_until(lambda: len(data.topics) == 4)
        return data

    def test_explicit_read_only_inspection(self):
        data = self.sources()
        data.select("camera.state")
        self.assertEqual([m["op"] for m in self.robot.requests if m["op"].startswith("data.")], ["data.list"])
        data.snapshot()
        wait_until(lambda: data.view["received"])
        self.assertEqual(data.rows.items, [{"name": "state", "value": "idle"}, {"name": "enabled", "value": "нет"}])
        self.assertTrue(data.view["valid"])
        self.assertFalse(data.wanted)
        self.assertIsNone(self.robot.owner)
        self.assertEqual(self.robot.mode, "GAME")
        self.assertFalse(any(m["op"].startswith(("videostream.", "camera.", "motion.")) for m in self.robot.requests))

    def test_subscription_gaps_rate_update_and_unsubscribe(self):
        data = self.sources()
        data.subscribe(2)
        wait_until(lambda: data.view["active"])
        topic = data.selected
        self.robot.send_data(topic, 1)
        wait_until(lambda: data.sequences.get(topic) == 1)
        before = len(self.controller.history)
        self.robot.send_data(topic, 4)
        wait_until(lambda: data.sequences.get(topic) == 4)
        self.assertEqual(data.view["gaps"], 2)
        self.assertEqual(len(self.controller.history), before, "Samples must not flood logs")
        self.robot.send_data(topic, 3)
        self.robot.send_data(topic, 5)
        wait_until(lambda: data.sequences.get(topic) == 5)
        self.assertEqual(data.view["gaps"], 2)
        data.subscribe(5)
        wait_until(lambda: data.view["rate"] == 5 and not data.view["busy"])
        self.robot.send_data(topic, 1)
        wait_until(lambda: data.sequences.get(topic) == 1)
        data.unsubscribe()
        wait_until(lambda: not data.view["watching"])
        old = data.samples[topic]
        self.robot.send_data(topic, 2)
        data.snapshot()
        wait_until(lambda: not data.view["busy"])
        self.assertNotEqual(data.samples[topic], old)
        self.assertEqual(data.sequences[topic], 1)
        self.assertFalse(self.robot.subscriptions)

    def test_switch_source_keeps_explicit_subscriptions_and_disconnect_clears(self):
        data = self.sources()
        data.subscribe(2)
        wait_until(lambda: data.view["active"])
        data.select("motion.state")
        self.assertFalse(data.view["watching"])
        self.assertEqual(data.view["subscriptions"], 1)
        data.subscribe(2)
        wait_until(lambda: data.view["active"])
        self.assertEqual(data.view["subscriptions"], 2)
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertFalse(data.wanted)
        self.assertFalse(data.active)
        self.assertTrue(self.robot.game_running)
        self.connect()
        self.assertFalse(data.topics)
        self.assertFalse(data.wanted)
        self.assertEqual(sum(m["op"] == "data.list" for m in self.robot.requests), 1)

    def test_parameter_groups_search_and_control_reasons(self):
        self.connect()
        self.controller.requestCatalog("parameters")
        wait_until(lambda: self.controller.parameters.rowCount() == 3)
        self.assertEqual(self.controller.parameterGroups, ["Все", "head", "logging", "motion"])
        self.controller.inspectParameter("head.field_tilt")
        wait_until(lambda: "value" in self.controller.param_parts)
        self.controller.filterParameters("motion", "STEP")
        self.assertEqual(self.controller.parameter_filter.rowCount(), 1)
        self.assertEqual(self.controller.param_key, "")
        self.controller.filterParameters("motion", "tilt")
        self.assertEqual(self.controller.parameter_filter.rowCount(), 0)
        self.controller.filterParameters("Все", "")
        self.assertEqual(self.controller.parameter_filter.rowCount(), 3)
        c = self.controller.control
        self.assertIn("Получить управление", c.blocked_reason)
        c.acquire()
        wait_until(lambda: c.owns and not c.pending)
        self.assertIn("ручной режим", c.blocked_reason)
        self.assertTrue(c.view["canEnterManual"])
        c.enterManual()
        wait_until(lambda: c.view["ready"])
        self.assertEqual(c.blocked_reason, "")

    def test_bounded_fields_and_invalid_rate(self):
        data = self.sources()
        data.subscribe(float("nan"))
        self.assertTrue(data.error)
        self.assertFalse(data.wanted)
        self.assertEqual(len(fields(dict.fromkeys(range(300), "x"))), 256)
        data.notification({"topic": []})
        data.response("data.list", {"items": [{}]}, "")
        self.assertIn("Некорректный", data.error)
