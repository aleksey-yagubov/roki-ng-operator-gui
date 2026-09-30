"""Loopback-only protocol fixture. Never connects to physical hardware."""

import socket
import threading

import msgpack

from operator_gui.transport import envelope


class FakeRobot:
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.05)
        self.port = self.sock.getsockname()[1]
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.requests = []
        self.errors = []
        self.client = None
        self.session = 2**60 + 123
        self.token = 2**61 + 456
        self.cache = {}
        self.drop_once = set()
        self.silent = False
        self.sequence = 0
        self.log_id = 0
        self.game_running = True
        self.mode = "GAME"
        self.owner = None
        self.lease = 7
        self.jobs = {}
        self.values = {}
        self.head = {"pan": 0, "tilt": 0}
        self.subscriptions = {}
        self.streams = {}
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.thread.join(2)
        self.sock.close()

    def _send(self, packet, address=None):
        raw = msgpack.packb(packet, use_bin_type=True)
        assert len(raw) <= 1200, len(raw)
        self.sock.sendto(raw, address or self.client)

    def send_log(self, message="camera ready", level="INFO", skip=0):
        self.sequence += 1 + skip
        self.log_id += 1
        packet = envelope("sample", "log.sample", {"records": [dict(record_sequence=self.log_id,
                          monotonic_ns=self.log_id * 1000000, source="camera", level=level,
                          message=message)], "dropped": 0}, 0, self.session, self.token)
        packet["sequence"] = self.sequence
        self._send(packet)

    def sample(self, topic):
        data = ({"camera": {"alive": True, "state": "idle"}} if topic == "system.workers"
                else {"head": dict(self.head)} if topic == "motion.state"
                else {"state": "idle", "enabled": False})
        return dict(topic=topic, valid=True, source_mono_ns=123456, age_ms=5, data=data)

    def send_data(self, topic, sequence):
        self.sequence += 1
        body = dict(self.sample(topic), subscription=topic, sequence=sequence)
        packet = envelope("sample", "data.sample", body, 0, self.session, self.token)
        packet["sequence"] = self.sequence
        self._send(packet)

    def _run(self):
        while not self.stop_event.is_set():
            try:
                raw, address = self.sock.recvfrom(1201)
            except socket.timeout:
                continue
            try:
                message = msgpack.unpackb(raw, raw=False)
                self.requests.append(message)
                if self.silent:
                    continue
                self.client = address
                op, ident = message["op"], message["id"]
                if message["kind"] == "sample":
                    assert op == "motion.drive" and message["body"]["lease_epoch"] == self.lease
                    continue
                if op == "hello":
                    body = dict(robot_id="LOCAL-TEST", boot_id="fake-boot", heartbeat_ms=500,
                                session_timeout_ms=2000, drive_timeout_ms=350, state="GAME",
                                capabilities_revision="manual-1", max_datagram=1200)
                    self._send(envelope("welcome", "hello", body, ident, self.session, self.token), address)
                    continue
                assert message["session"] == self.session and message["token"] == self.token
                key = (address, ident)
                if key not in self.cache:
                    self.cache[key] = envelope("response", op, {"result": self._result(op, message["body"])},
                                               ident, self.session, self.token)
                if op in self.drop_once:
                    self.drop_once.remove(op)
                    continue
                self._send(self.cache[key], address)
            except Exception as exc:
                self.errors.append(repr(exc))

    def _result(self, op, body):
        if op == "session.heartbeat":
            return {"state": self.mode}
        if op == "session.close":
            return {"closing": True}
        if op == "log.subscribe":
            return {"subscription_id": "logs", "after": self.log_id}
        if op == "system.status":
            return dict(state=self.mode, owner=self.owner, boot_id="fake-boot", counters={},
                        workers={"motherboard": {"alive": True, "state": "ready"}})
        if op == "system.capabilities":
            return dict(revision="manual-1", simulated=True, future=["video", "osd"])
        if op == "video.capabilities":
            return dict(backends=["direct-gst"], codecs=["h264", "jpeg"])
        if op == "video.create":
            assert self.owner == self.session and self.mode == "MANUAL"
            ident = str(len(self.streams) + 1)
            jpeg = body["codec"]["name"] == "jpeg"
            self.streams[ident] = dict(stream_id=ident, spec=body, state="created", ssrc=1234,
                                      payload_type=26 if jpeg else 96, clock_rate=90000,
                                      encoding_name="JPEG" if jpeg else "H264")
            return self.streams[ident].copy()
        if op == "video.start":
            assert body["lease_epoch"] == self.lease
            self.streams[body["stream_id"]]["state"] = "running"
            return self.streams[body["stream_id"]].copy()
        if op == "video.status":
            return self.streams[body["stream_id"]].copy()
        if op == "video.destroy":
            self.streams.pop(body["stream_id"], None)
            return dict(stream_id=body["stream_id"], state="destroyed")
        if op == "data.list":
            return {"items": [dict(name=t, kind="state", max_rate_hz=10, schema=1)
                              for t in ("system.workers", "motion.state", "camera.state", "detection.state")]}
        if op == "data.snapshot":
            return self.sample(body["topic"])
        if op == "data.subscribe":
            self.subscriptions[body["topic"]] = body["rate_hz"]
            return dict(subscription_id=body["topic"], rate_hz=body["rate_hz"])
        if op == "data.unsubscribe":
            self.subscriptions.pop(body["subscription_id"], None)
            return {}
        if op in ("motion.slots", "params.keys"):
            items = ([f"slot_{i:02}" for i in range(57)] if op == "motion.slots"
                     else ["head.field_tilt", "motion.max_step_mm", "logging.stdout_enabled"])
            start, limit = body.get("offset", 0), body.get("limit", 8)
            end = min(len(items), start + limit)
            return {"items": items[start:end], "total": len(items), "next_offset": end if end < len(items) else None}
        if op == "test.list":
            return {"items": ["run_test", "jump_test", "rotation_test", "kick_test"]}
        if op == "test.describe":
            return dict(name=body["name"], title="Ходьба", parameters={
                "mode": {"choices": ["short", "long", "custom"], "default": "short"},
                "cycles": {"type": "int", "min": 1, "max": 100, "default": 10, "when": "custom"},
                "right_leg": {"type": "bool", "default": True, "when": "custom"}})
        if op == "params.describe":
            return dict(key=body["key"], type="int", default=-1500, min=-2600, max=950,
                        apply="next_operation", description="Положение головы для поля")
        if op == "params.get":
            return {"key": body["key"], "value": self.values.get(body["key"], -1500)}
        if op == "control.acquire":
            self.owner = self.session
            return {"lease_epoch": self.lease}
        if op == "job.status":
            return self.jobs[body["job_id"]]
        if op in ("mode.set", "params.set", "test.start", "control.release") or op.startswith("motion."):
            assert self.owner == self.session and body["lease_epoch"] == self.lease
            if op == "mode.set":
                self.mode = body["mode"]
                if self.mode == "IDLE":
                    for job in self.jobs.values():
                        if job["status"] == "running":
                            job["status"] = "cancelled"
                return {"state": self.mode}
            if op == "control.release":
                self.owner = None
                self.mode = "IDLE"
                return {"released": True}
            if op == "params.set":
                self.values[body["key"]] = body["value"]
                return {"key": body["key"], "value": body["value"], "apply": "next_job"}
            if op.startswith("motion.stop"):
                for job in self.jobs.values():
                    job["status"] = "cancelled"
                return {"stopped": True}
            if op == "motion.head":
                self.head.update({axis: body[axis] for axis in ("pan", "tilt") if axis in body})
                return {"accepted": True, "target": dict(self.head)}
            assert self.mode == "MANUAL"
            job_id = str(len(self.jobs) + 1)
            self.jobs[job_id] = dict(job_id=job_id, operation=op, status="running", progress=0)
            return {"accepted": True, "job_id": job_id}
        raise AssertionError(f"Unexpected operation: {op}")
