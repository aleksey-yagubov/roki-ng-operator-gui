import unittest
from unittest.mock import patch

from PySide6.QtTest import QTest

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
        self.assertEqual(data.wanted, {"body.power"})
        data.requestList()
        wait_until(lambda: len(data.topics) == 5)
        return data

    def test_explicit_read_only_inspection(self):
        data = self.sources()
        data.select("camera.state")
        self.assertEqual([m["op"] for m in self.robot.requests if m["op"].startswith("data.")],
                         ["data.subscribe", "data.list"])
        data.snapshot()
        wait_until(lambda: data.view["received"])
        self.assertEqual(data.rows.items, [{"name": "state", "value": "idle"}, {"name": "enabled", "value": "нет"}])
        self.assertTrue(data.view["valid"])
        self.assertEqual(data.wanted, {"body.power"})
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
        self.assertEqual(self.robot.subscriptions, {"body.power": 1})

    def test_switch_source_keeps_explicit_subscriptions_and_disconnect_clears(self):
        data = self.sources()
        data.subscribe(2)
        wait_until(lambda: data.view["active"])
        data.select("motion.state")
        self.assertFalse(data.view["watching"])
        self.assertEqual(data.view["subscriptions"], 2)
        data.subscribe(2)
        wait_until(lambda: data.view["active"])
        self.assertEqual(data.view["subscriptions"], 3)
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertFalse(data.wanted)
        self.assertFalse(data.active)
        self.assertTrue(self.robot.game_running)
        self.connect()
        self.assertFalse(data.topics)
        self.assertEqual(data.wanted, {"body.power"})
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
        self.assertEqual(data.wanted, {"body.power"})
        self.assertEqual(len(fields(dict.fromkeys(range(300), "x"))), 256)
        data.notification({"topic": []})
        data.response("data.list", {"items": [{}]}, "")
        self.assertIn("Некорректный", data.error)

    def test_power_arrives_without_catalog_or_control(self):
        self.connect()
        data = self.controller.data_sources
        self.assertFalse(data.topics)
        self.assertFalse(data.power["valid"])
        self.robot.send_data("body.power", 1)
        wait_until(lambda: data.power["valid"])
        self.assertEqual(data.power["text"], "12.04 В (симуляция)")
        self.assertEqual(data.power["voltage"], 12.04)
        self.assertEqual(data.power["adcRaw"], 3253)
        self.assertIn("3253", data.power["details"])
        self.assertIsNone(self.robot.owner)
        self.assertEqual({m["op"] for m in self.robot.requests} - {"session.heartbeat"},
                         {"hello", "log.subscribe", "data.subscribe"})

    def test_power_expiry_includes_robot_age_without_next_packet(self):
        self.connect()
        data = self.controller.data_sources
        self.robot.power_sample["age_ms"] = 2000
        self.robot.send_data("body.power", 1)
        wait_until(lambda: data.power["valid"])
        _, received = data.samples["body.power"]
        with patch("operator_gui.data_sources.time.monotonic", return_value=received + .999):
            self.assertTrue(data.power["valid"])
        with patch("operator_gui.data_sources.time.monotonic", return_value=received + 1.):
            self.assertTrue(data.power["stale"])
            self.assertIsNone(data.power["voltage"])
        # The one-shot expiry must notify QML even without the periodic clock.
        data.clock.stop()
        expired = []
        data.changed.connect(lambda: expired.append(data.power["stale"]))
        wait_until(lambda: any(expired), timeout=2000)
        self.assertIn("устарели", data.power["text"])
        self.robot.send_data("body.power", 1)  # Duplicate must not refresh age.
        QTest.qWait(30)
        self.assertEqual(data.samples["body.power"][1], received)

    def test_invalid_power_never_becomes_zero_volts(self):
        self.connect()
        data = self.controller.data_sources
        base = self.robot.sample("body.power")
        cases = [dict(base, valid=False), dict(base, age_ms=3000)]
        cases += [dict(base, age_ms=age) for age in (None, -1, True, float("nan"), float("inf"))]
        cases += [dict(base, data=dict(base["data"], voltage_v=v))
                  for v in (None, -1, "12", True, float("nan"), float("inf"))]
        cases += [dict(base, data=dict(base["data"], valid=False)),
                  dict(base, data=dict(base["data"], error="body offline"))]
        for body in cases:
            with self.subTest(body=body):
                data._sample(body)
                self.assertFalse(data.power["valid"])
                self.assertIsNone(data.power["voltage"])
                self.assertNotIn("0.00", data.power["text"])

    def test_power_reconnect_drops_cached_voltage_and_resubscribes(self):
        self.connect()
        data = self.controller.data_sources
        self.robot.send_data("body.power", 1)
        wait_until(lambda: data.power["valid"])
        self.controller.disconnectRobot()
        wait_until(lambda: not self.controller.transport.connected)
        self.assertIsNone(data.power["voltage"])
        self.assertNotIn("body.power", data.samples)
        self.connect()
        self.assertFalse(data.power["valid"])
        subscriptions = [m for m in self.robot.requests if m["op"] == "data.subscribe"]
        self.assertEqual(len(subscriptions), 2)

    def test_power_inspector_reuses_subscription_and_can_disable_it(self):
        data = self.sources()
        data.select("body.power")
        self.assertTrue(data.view["active"])
        self.assertEqual(data.view["maxRate"], 1)
        data.snapshot()
        wait_until(lambda: data.power["valid"])
        data.unsubscribe()
        wait_until(lambda: not data.view["watching"])
        self.assertFalse(self.robot.subscriptions)
        QTest.qWait(1100)
        self.assertEqual(sum(m["op"] == "data.subscribe" for m in self.robot.requests), 1)
        self.assertIn("Подписка отключена", data.power["details"])
