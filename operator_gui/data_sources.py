"""Read-only datastream inspector. No implicit subscriptions or hardware startup."""

import json
import math
import time

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot

from .models import Rows


def fields(value):
    result = []

    def visit(path, node, depth):
        if len(result) >= 256:
            return
        if depth < 6 and isinstance(node, (dict, list)) and node:
            items = node.items() if isinstance(node, dict) else enumerate(node)
            for key, child in items:
                visit(f"{path}.{key}" if path else str(key), child, depth + 1)
        else:
            text = ("да" if node else "нет") if type(node) is bool else "нет данных" if node is None else (
                json.dumps(node, ensure_ascii=False) if isinstance(node, (dict, list)) else str(node))
            result.append({"name": path or "value", "value": text[:512]})
    visit("", value, 0)
    return result


class DataSources(QObject):
    changed = Signal()
    topicsChanged = Signal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.rows = Rows(self, limit=256)
        self.topics = []
        self.selected = ""
        self.samples = {}
        self.wanted = set()
        self.active = {}
        self.pending = set()
        self.sequences = {}
        self.gaps = {}
        self.error = ""
        session.response.connect(self.response)
        session.failed.connect(self.failed)
        session.changed.connect(self.connection)
        session.welcomed.connect(self.reset)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self.changed.emit)
        self.clock.start()

    @Property("QVariantList", notify=topicsChanged)
    def catalog(self):
        return self.topics

    @Property("QVariantMap", notify=changed)
    def view(self):
        sample, received = self.samples.get(self.selected, ({}, None))
        meta = next((m for m in self.topics if m["name"] == self.selected), {})
        return dict(selected=self.selected, connected=self.session.connected,
                    busy=any(topic == self.selected for _, topic in self.pending),
                    listing=("data.list", "") in self.pending,
                    watching=self.selected in self.wanted, active=self.selected in self.active,
                    subscriptions=len(self.wanted), maxRate=meta.get("max_rate_hz", 10),
                    received=received is not None, valid=sample.get("valid", False),
                    localAge="-" if received is None else str(round(time.monotonic() - received, 1)),
                    sourceAge=str(sample.get("age_ms", "-")), gaps=self.gaps.get(self.selected, 0),
                    rate=self.active.get(self.selected, 0), error=self.error,
                    raw=json.dumps(sample, ensure_ascii=False, indent=2) if sample else "")

    def request(self, op, body, topic=""):
        key = (op, topic)
        if not self.session.connected or key in self.pending:
            return
        self.pending.add(key)
        self.error = ""
        self.session.request(op, body, topic)
        self.changed.emit()

    @Slot()
    def requestList(self):
        self.request("data.list", {})

    @Slot(str)
    def select(self, topic):
        if topic and topic not in {m["name"] for m in self.topics}:
            return
        self.selected = topic
        self.rows.replace(fields(self.samples.get(topic, ({}, None))[0].get("data", {})) if topic in self.samples else [])
        self.changed.emit()

    @Slot()
    def snapshot(self):
        if self.selected:
            self.request("data.snapshot", {"topic": self.selected}, self.selected)

    @Slot(float)
    def subscribe(self, rate):
        if not self.session.connected or not self.selected or self.view["busy"]:
            return
        if not math.isfinite(rate) or not 0.2 <= rate <= self.view["maxRate"]:
            self.error = "Частота вне допустимого диапазона"
            self.changed.emit()
            return
        self.wanted.add(self.selected)
        self.sequences.pop(self.selected, None)
        self.request("data.subscribe", {"topic": self.selected, "rate_hz": rate}, self.selected)

    @Slot()
    def unsubscribe(self):
        if self.selected in self.wanted:
            self.request("data.unsubscribe", {"subscription_id": self.selected}, self.selected)

    @Slot(str, object, str)
    def response(self, op, body, topic):
        if topic.startswith("head-state:"):
            return
        if not op.startswith("data."):
            return
        self.pending.discard((op, topic))
        try:
            if op == "data.list":
                items = body["items"]
                if (not isinstance(items, list) or len(items) > 64
                        or not all(isinstance(item, dict) and isinstance(item.get("name"), str)
                                   and isinstance(item.get("max_rate_hz"), (int, float))
                                   and math.isfinite(item["max_rate_hz"]) and 0.2 <= item["max_rate_hz"] <= 100
                                   for item in items)):
                    raise ValueError("Некорректный каталог источников")
                self.topics = items
                self.topicsChanged.emit()
                self.select(self.selected if self.selected in {m["name"] for m in items}
                            else items[0]["name"] if items else "")
            elif op == "data.snapshot":
                if body.get("topic") != topic:
                    raise ValueError("Ответ относится к другому источнику")
                self._sample(body)
            elif op == "data.subscribe":
                if body.get("subscription_id") != topic:
                    raise ValueError("Ответ относится к другой подписке")
                self.active[topic] = body["rate_hz"]
                self.sequences.pop(topic, None)
            elif op == "data.unsubscribe":
                self.wanted.discard(topic)
                self.active.pop(topic, None)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            self.error = str(exc)
        self.changed.emit()

    def notification(self, body):
        topic = body.get("topic")
        if not isinstance(topic, str) or topic not in self.wanted or ("data.subscribe", topic) in self.pending:
            return
        sequence = body.get("sequence", 0)
        if type(sequence) is not int or sequence <= self.sequences.get(topic, 0):
            return
        previous = self.sequences.get(topic, 0)
        if previous:
            self.gaps[topic] = self.gaps.get(topic, 0) + sequence - previous - 1
        self.sequences[topic] = sequence
        self._sample(body)
        self.changed.emit()

    def _sample(self, body):
        topic = body.get("topic")
        if topic not in {m["name"] for m in self.topics} or not isinstance(body.get("data"), dict):
            return
        self.samples[topic] = (dict(body), time.monotonic())
        if topic == self.selected:
            self.rows.replace(fields(body["data"]))

    @Slot(str, str, str)
    def failed(self, op, message, topic):
        if topic.startswith("head-state:"):
            return
        if op.startswith("data."):
            self.pending.discard((op, topic))
            self.error = f"{op}: {message}"
            self.changed.emit()

    @Slot()
    def connection(self):
        if not self.session.connected:
            self.wanted.clear()
            self.active.clear()
            self.pending.clear()
        self.changed.emit()

    @Slot(object)
    def reset(self, _body):
        self.topics = []
        self.selected = ""
        self.samples.clear()
        self.wanted.clear()
        self.active.clear()
        self.pending.clear()
        self.sequences.clear()
        self.gaps.clear()
        self.error = ""
        self.rows.replace([])
        self.topicsChanged.emit()
        self.changed.emit()

    @Slot()
    def barrier(self):
        # Urgent motion commands retire queued normal requests. Keep subscription
        # intent so an uncertain subscribe can still be explicitly unsubscribed.
        self.pending.clear()
        self.changed.emit()

    def shutdown(self):
        self.clock.stop()
