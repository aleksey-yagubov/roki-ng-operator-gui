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
        self.game_observe_only = True
        self.game_running = True
        self.mode = "GAME"
        self.owner = None
        self.lease = 7
        self.jobs = {}
        self.values = {}
        self.head = {"pan": 0, "tilt": 0}
        self.subscriptions = {}
        self.power_sample = dict(valid=True, age_ms=5, data=dict(
            voltage_v=12.04, adc_raw=3253, valid=True, simulated=True, error=None))
        self.streams = {}
        self.camera_running = False
        self.camera_exposure = 8000
        self.localisation_enabled = False
        self.localisation_running = False
        self.localisation_age = 10
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.thread.join(2)
        self.sock.close()

    def _send(self, packet, address=None):
        raw = msgpack.packb(packet, use_bin_type=True)
        assert len(raw) <= 1400, len(raw)
        self.sock.sendto(raw, address or self.client)

    def send_log(self, message="camera ready", level="INFO", skip=0):
        self.sequence += 1 + skip
        self.log_id += 1
        packet = envelope("sample", "log.sample", {"records": [dict(record_sequence=self.log_id,
                          monotonic_ns=self.log_id * 1000000, source="camera", level=level,
                          message=message)], "dropped": 0}, 0, self.session, self.token)
        packet["sequence"] = self.sequence
        self._send(packet)

    def game_state(self):
        return dict(running=self.game_running, state="observing" if self.game_running else "stopped",
                    observe_only=self.game_observe_only, reason="", decision="hold", ball=None,
                    travel_m=0., job_id=None)

    def sample(self, topic):
        if topic == "body.power":
            return dict(topic=topic, **self.power_sample)
        data = ({"camera": {"alive": True, "state": "idle"}} if topic == "system.workers"
                else self.game_state() if topic == "game.state"
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
                raw, address = self.sock.recvfrom(1401)
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
                                capabilities_revision="manual-1", max_datagram=1400)
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
            return dict(revision="manual-1", simulated=True, future=["video", "osd"],
                        **({"localisation":{"mode":"diagnostic_only"}} if self.localisation_enabled else {}))
        if op in ("game.start", "game.stop", "game.status"):
            if op != "game.status":
                assert self.owner == self.session and body['lease_epoch'] == self.lease
            if op == "game.start":
                assert self.mode == "MANUAL"
                assert body['strategy'] == 'FIRA_penalty_Goalkeeper'
                assert type(body['delay_seconds']) is int
                assert 0 <= body['delay_seconds'] <= 30
                self.game_observe_only = body['observe_only']
                assert self.game_observe_only or self.values.get('game.geometry_verified') is True
                self.game_running = True
                self.mode = "GAME"
            elif op == "game.stop":
                self.game_running = False
                self.mode = "MANUAL"
            return self.game_state()
        if op.startswith('localisation.'):
            assert self.localisation_enabled
            if op=='localisation.start':
                assert self.owner==self.session and self.mode=='MANUAL'
                assert body['lease_epoch']==self.lease
                assert len(body['prior'])==3
                self.localisation_running=True
            elif op=='localisation.stop':
                assert body['lease_epoch']==self.lease
                self.localisation_running=False
            return dict(state='ready',running=self.localisation_running,mode='diagnostic_only',
                        age_ms=self.localisation_age,error=None,configuration_id='a'*16,
                        geometry=dict(length=3.35,width=2.35,carpet_length=4.,carpet_width=3.,
                                      paint_width=.05,circle_diameter=.5),
                        result=dict(candidate=[-1.2,-.8,.4],valid=False,fit_state=getattr(self,'localisation_fit','weak'),
                                    lines=5,circle=True,inlier_fraction=.4,median_residual_m=.15,
                                    frame_sequence=123) if self.localisation_running else None)
        if op == "camera.capabilities":
            return dict(sensor=dict(width=1600,height=1300,depth=10),
                        output=dict(width=800,height=650,format="BGR"),geometry_mutable=False,
                        imu_required=True,frame_duration_us=dict(min=8333,max=100000,default=16667))
        if op == "camera.controls.list":
            return dict(items=[dict(key="camera.exposure_us",type="int",min=1,max=16667,
                                    default=8000,value=self.camera_exposure,supported=None,
                                    description="Выдержка, мкс")],next_offset=None)
        if op in ("camera.controls.set","camera.controls.save"):
            self.camera_exposure=body["values"]["camera.exposure_us"]
            return dict(values=body["values"],saved=op.endswith("save"))
        if op in ("camera.start","camera.stop","camera.status"):
            if op!="camera.status":
                assert body["lease_epoch"]==self.lease
                self.camera_running=op=="camera.start"
            return dict(running=self.camera_running,sequence=12,frame_duration_us=16667,
                        requested_controls=dict(exposure_us=self.camera_exposure),
                        imu_sync=dict(state="synced" if self.camera_running else "idle"),error=None)
        if op == "videostream.sources":
            available={"direct-gst":not self.camera_running,"runtime":self.camera_running,"localisation":self.localisation_running}
            items=[dict(id=k,name=k,available=available[k],reason="" if available[k] else "producer_unavailable", stream_settings=dict(codecs=["jpeg","h264"],max_fps=[1,120],max_size=[1600,1300] if k=="direct-gst" else [800,650],jpeg_alignment=8)) for k in available]
            start=body.get("offset",0);limit=body.get("limit",1)
            return dict(items=items[start:start+limit],next_offset=start+limit if start+limit<len(items) else None)
        if op == "videostream.list":
            items=[dict(stream_id=k,source=v["spec"]["source"],state=v["state"],run_id=v["run_id"],receivers=v["receivers"],attached=v["attached"]) for k,v in self.streams.items()]
            start=body.get("offset",0);limit=body.get("limit",4)
            return dict(items=items[start:start+limit],next_offset=start+limit if start+limit<len(items) else None)
        if op == "videostream.capabilities":
            return dict(backends=["direct-gst"], codecs=["h264", "jpeg"])
        if op == "videostream.create":
            assert self.owner == self.session and self.mode == "MANUAL"
            assert "destination" not in body and "backend" not in body
            ident = str(len(self.streams) + 1)
            jpeg = body["codec"]["name"] == "jpeg"
            self.streams[ident] = dict(stream_id=ident, spec=body, state="created", ssrc=None, run_id=None, attached=False, receivers=0,
                                      payload_type=26 if jpeg else 96, clock_rate=90000,
                                      encoding_name="JPEG" if jpeg else "H264")
            return self.streams[ident].copy()
        if op in ("videostream.start", "videostream.attach"):
            if op == "videostream.attach":
                assert self.streams[body["stream_id"]]["state"] in ("starting", "running")
            else:
                assert body["lease_epoch"] == self.lease
            self.streams[body["stream_id"]].update(state="running", ssrc=1234, run_id="run1", attached=True, receivers=1, destination=["127.0.0.1",body["rtp_port"]])
            return self.streams[body["stream_id"]].copy()
        if op == "videostream.detach":
            stream=self.streams[body["stream_id"]]
            stream.update(state="stopped", attached=False, receivers=0)
            return stream.copy()
        if op == "videostream.stop":
            self.streams[body["stream_id"]].update(state="stopped",attached=False,receivers=0)
            return self.streams[body["stream_id"]].copy()
        if op == "videostream.update":
            item=self.streams[body["stream_id"]]
            if "max_fps" in body:item["spec"]["max_fps"]=body["max_fps"]
            if "bitrate" in body:item["spec"]["codec"]["bitrate"]=body["bitrate"]
            return item.copy()
        if op == "videostream.status":
            return self.streams[body["stream_id"]].copy()
        if op == "videostream.destroy":
            self.streams.pop(body["stream_id"], None)
            return dict(stream_id=body["stream_id"], state="destroyed")
        if op == "data.list":
            return {"items": [dict(name=t, kind="state", max_rate_hz=10, schema=1)
                              for t in ("system.workers", "motion.state", "camera.state", "detection.state")]
                    + [dict(name="body.power", kind="state", max_rate_hz=1, schema=1)]}
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
