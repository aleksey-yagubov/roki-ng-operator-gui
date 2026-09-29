"""Nonblocking manual-1 UDP transport owned by the Qt event loop."""

from collections import deque
import ipaddress
import socket
import sys
import time
import uuid

import msgpack
from PySide6.QtCore import QObject, QSocketNotifier, QThread, QTimer, Qt, Signal, Slot

LIMIT = 1200


def envelope(kind, op, body, ident, session=0, token=0):
    return dict(v=1, kind=kind, op=op, body=body, id=ident, session=session,
                token=token, sequence=0, robot_mono_ns=0)


def decode(data):
    if len(data) > LIMIT:
        raise ValueError("Datagram exceeds 1200 bytes")
    value = msgpack.unpackb(data, raw=False, strict_map_key=True, max_array_len=256,
                           max_map_len=128, max_str_len=LIMIT, max_bin_len=LIMIT,
                           max_ext_len=0)
    if not isinstance(value, dict) or value.get("v") != 1:
        raise ValueError("Unsupported envelope")
    if not isinstance(value.get("body"), dict) or not isinstance(value.get("op"), str):
        raise ValueError("Invalid body/op")
    for key in ("id", "session", "token"):
        n = value.get(key)
        if type(n) is not int or not 0 <= n < 2**64:
            raise ValueError(f"Invalid {key}")
    return value


class Transport(QObject):
    changed = Signal()
    stateChanged = Signal(object)
    finished = Signal()
    welcomed = Signal(object)
    response = Signal(str, object, str)
    failed = Signal(str, str, str)
    notification = Signal(object)
    diagnostic = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sock = self.notifier = None
        self.address = None
        self.phase = "disconnected"
        self.session = self.token = self.ident = 0
        self.drive_sequence = 0
        self.pending = {}
        self.queue = deque()
        self.last_rx = self.next_heartbeat = 0
        self.heartbeat_seconds = 0.5
        self.timeout_seconds = 2.0
        self.rtt_ms = None
        self.invalid_packets = 0
        self.inbox = deque(maxlen=256)
        self.inbox_dropped = 0
        self.delivery_pending = False
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self._tick)
        self.changed.connect(self._publish)

    @Slot()
    def _publish(self):
        self.stateChanged.emit(dict(phase=self.phase, rtt_ms=self.rtt_ms,
                                    invalid_packets=self.invalid_packets, session=self.session))

    @property
    def connected(self):
        return self.phase == "connected"

    @Slot(str, int)
    def connect_to(self, host, port):
        if self.sock is not None:
            return
        try:
            address = (str(ipaddress.IPv4Address(host.strip())), int(port))
            if not 1 <= address[1] <= 65535:
                raise ValueError("Port must be 1..65535")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock = sock
            if sys.platform.startswith("linux"):
                sock.setsockopt(socket.IPPROTO_IP, getattr(socket, "IP_MTU_DISCOVER", 10), 2)
            elif sys.platform == "darwin":
                # Darwin SDK netinet/in.h: IP_DONTFRAG = 28.
                sock.setsockopt(socket.IPPROTO_IP, getattr(socket, "IP_DONTFRAG", 28), 1)
            elif sys.platform == "win32":
                sock.setsockopt(socket.IPPROTO_IP, getattr(socket, "IP_DONTFRAGMENT", 14), 1)
            else:
                raise OSError("DF configuration has not been implemented for this OS")
            sock.setblocking(False)
            sock.bind(("0.0.0.0", 0))
            self.address = address
            self.notifier = QSocketNotifier(sock.fileno(), QSocketNotifier.Type.Read, self)
            self.notifier.activated.connect(self._read)
            self.phase = "connecting"
            self.ident = self.session = self.token = 0
            self.drive_sequence = 0
            self.rtt_ms = None
            self.invalid_packets = 0
            self.timer.start()
            self._send_request("hello", {"versions": [1], "client_name": "roki-ng-operator",
                                         "client_instance": uuid.uuid4().hex}, "", "hello")
            self.changed.emit()
        except (ValueError, OSError) as exc:
            self.close(notify_peer=False)
            self.diagnostic.emit("ERROR", str(exc))

    @Slot(bool, str)
    def close(self, notify_peer=True, reason="disconnected"):
        if self.sock is not None and self.connected and notify_peer:
            self.ident += 1
            packet = envelope("request", "session.close", {}, self.ident, self.session, self.token)
            try:
                self.sock.sendto(msgpack.packb(packet, use_bin_type=True), self.address)
            except OSError:
                pass
        self.timer.stop()
        if self.notifier:
            self.notifier.setEnabled(False)
            self.notifier.deleteLater()
            self.notifier = None
        if self.sock is not None:
            self.sock.close()
            self.sock = None
        self.pending.clear()
        self.queue.clear()
        self.inbox.clear()
        self.inbox_dropped = 0
        self.session = self.token = 0
        self.phase = reason
        self.rtt_ms = None
        self.changed.emit()

    @Slot(str, object, str)
    def request(self, op, body=None, context=""):
        if not self.connected:
            self.failed.emit(op, "Not connected", context)
            return
        if len(self.queue) >= 32:
            self.failed.emit(op, "Request queue is full", context)
            return
        self.queue.append((op, body or {}, context))
        self._drain()

    @Slot()
    def shutdown(self):
        self.close()
        self.finished.emit()

    @Slot(object)
    def drive(self, update):
        # Never replay drive samples queued before a UI stall or a reconnect.
        if (not self.connected or update["session"] != self.session
                or time.monotonic() - update["at"] > 0.15):
            return
        self.drive_sequence += 1
        packet = envelope("sample", "motion.drive", update["body"], 0, self.session, self.token)
        packet["sequence"] = self.drive_sequence
        self._write(msgpack.packb(packet, use_bin_type=True))

    @Slot(str, object, str)
    def interrupt(self, op, body, context):
        if not self.connected:
            self.failed.emit(op, "Not connected", context)
            return
        # Retire old commands before issuing the barrier. Never retry them after stop.
        self.queue.clear()
        self.pending.clear()
        self._send_request(op, body, context)

    @Slot()
    def delivery_done(self):
        self.delivery_pending = False

    def _drain(self):
        # One application request in flight; heartbeat must not wait behind it.
        if self.connected and self.queue and not any(p["op"] != "session.heartbeat"
                                                     for p in self.pending.values()):
            self._send_request(*self.queue.popleft())

    def _send_request(self, op, body, context, kind="request"):
        self.ident += 1
        packet = msgpack.packb(envelope(kind, op, body, self.ident, self.session, self.token), use_bin_type=True)
        if len(packet) > LIMIT:
            self.failed.emit(op, "Message exceeds 1200 bytes", context)
            return
        now = time.monotonic()
        self.pending[self.ident] = dict(op=op, context=context, packet=packet, attempts=1,
                                       sent=now, deadline=now + 0.25,
                                       expires=now + (20.0 if op == "camera.start" else 1.25))
        self._write(packet)

    def _write(self, packet):
        if self.sock is None:
            return
        try:
            self.sock.sendto(packet, self.address)
        except OSError as exc:
            self.close(False, "lost")
            self.diagnostic.emit("ERROR", f"UDP: {exc}")

    def _tick(self):
        now = time.monotonic()
        if self.connected and now - self.last_rx > self.timeout_seconds:
            self.close(False, "lost")
            self.diagnostic.emit("ERROR", "Connection lost; reconnect explicitly")
            return
        for ident, pending in list(self.pending.items()):
            if pending["deadline"] > now:
                continue
            if pending["attempts"] >= 5:
                if now < pending["expires"]:
                    pending["deadline"] = pending["expires"]
                    continue
                del self.pending[ident]
                self.failed.emit(pending["op"], "Response timeout (operation outcome unknown)", pending["context"])
                if self.phase == "connecting":
                    self.close(False, "lost")
                    return
            else:
                pending["attempts"] += 1
                pending["deadline"] = now + 0.25
                self._write(pending["packet"])
                if self.sock is None:
                    return
        if self.connected and now >= self.next_heartbeat:
            self.next_heartbeat = now + self.heartbeat_seconds
            if not any(p["op"] == "session.heartbeat" for p in self.pending.values()):
                self._send_request("session.heartbeat", {}, "")
        self._drain()
        if self.connected and self.inbox and not self.delivery_pending:
            messages = [self.inbox.popleft() for _ in range(min(32, len(self.inbox)))]
            self.delivery_pending = True
            dropped, self.inbox_dropped = self.inbox_dropped, 0
            self.notification.emit(dict(session=self.session, messages=messages, dropped=dropped))

    def _read(self, *_):
        # Bound each event-loop turn so malformed/flooding traffic cannot monopolize Qt.
        for _ in range(32):
            if self.sock is None:
                return
            try:
                data, address = self.sock.recvfrom(LIMIT + 1)
            except BlockingIOError:
                break
            except OSError as exc:
                self.close(False, "lost")
                self.diagnostic.emit("ERROR", str(exc))
                break
            if address != self.address:
                continue
            try:
                message = decode(data)
                self._accept(message)
            except (ValueError, TypeError, KeyError, msgpack.UnpackException):
                self.invalid_packets += 1
                if self.invalid_packets == 1 or self.invalid_packets % 64 == 0:
                    self.diagnostic.emit("WARNING", f"Invalid datagrams: {self.invalid_packets}")

    def _accept(self, message):
        kind, op, ident = message.get("kind"), message["op"], message["id"]
        pending = self.pending.get(ident)
        if self.phase == "connecting":
            if (kind != "welcome" or op != "hello" or not pending
                    or pending["op"] != "hello" or not message["session"] or not message["token"]):
                return
            body = message["body"]
            heartbeat = body.get("heartbeat_ms", 500)
            timeout = body.get("session_timeout_ms", 2000)
            if (type(heartbeat) is not int or type(timeout) is not int
                    or not 100 <= heartbeat <= 5000 or not heartbeat * 2 <= timeout <= 30000):
                raise ValueError("Invalid heartbeat settings")
            self.pending.pop(ident)
            self.session, self.token = message["session"], message["token"]
            self.phase = "connected"
            self.heartbeat_seconds, self.timeout_seconds = heartbeat / 1000, timeout / 1000
            self.last_rx = time.monotonic()
            self.next_heartbeat = self.last_rx + self.heartbeat_seconds
            self.changed.emit()
            self.welcomed.emit(body)
            return
        if (not self.connected or message["session"] != self.session
                or message["token"] != self.token):
            return
        if kind == "response" and pending and pending["op"] == op:
            body = message["body"]
            if not isinstance(body.get("error", body.get("result")), dict):
                raise ValueError("Invalid response")
            self.last_rx = time.monotonic()
            if pending["attempts"] == 1:
                self.rtt_ms = round((self.last_rx - pending["sent"]) * 1000, 1)
            del self.pending[ident]
            if "error" in body:
                error = body["error"]
                self.failed.emit(op, f"{error.get('code')}: {error.get('message')}", pending["context"])
            else:
                self.response.emit(op, body["result"], pending["context"])
            self.changed.emit()
            self._drain()
        elif kind in ("event", "sample") and ident == 0:
            self.last_rx = time.monotonic()
            if len(self.inbox) == self.inbox.maxlen:
                self.inbox_dropped += 1
            self.inbox.append(message)


class Session(QObject):
    """GUI-thread facade. Socket, retries and MessagePack all live in the worker."""

    changed = Signal()
    welcomed = Signal(object)
    response = Signal(str, object, str)
    failed = Signal(str, str, str)
    notification = Signal(object)
    diagnostic = Signal(str, str)
    connectRequested = Signal(str, int)
    requestRequested = Signal(str, object, str)
    closeRequested = Signal(bool, str)
    shutdownRequested = Signal()
    deliveryDone = Signal()
    driveRequested = Signal(object)
    interruptRequested = Signal(str, object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.phase = "disconnected"
        self.rtt_ms = None
        self.invalid_packets = 0
        self.session = 0
        self.thread = QThread(self)
        self.thread.setObjectName("operator-udp")
        self.worker = Transport()
        self.worker.moveToThread(self.thread)
        self.connectRequested.connect(self.worker.connect_to)
        self.requestRequested.connect(self.worker.request)
        self.closeRequested.connect(self.worker.close)
        self.shutdownRequested.connect(self.worker.shutdown)
        self.deliveryDone.connect(self.worker.delivery_done)
        self.driveRequested.connect(self.worker.drive)
        self.interruptRequested.connect(self.worker.interrupt)
        self.worker.stateChanged.connect(self._state)
        for name in ("welcomed", "response", "failed", "notification", "diagnostic"):
            getattr(self.worker, name).connect(getattr(self, name))
        self.worker.finished.connect(self.thread.quit, Qt.ConnectionType.DirectConnection)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    @Slot(object)
    def _state(self, state):
        self.phase = state["phase"]
        self.rtt_ms = state["rtt_ms"]
        self.invalid_packets = state["invalid_packets"]
        self.session = state["session"]
        self.changed.emit()

    @property
    def connected(self):
        return self.phase == "connected"

    def connect_to(self, host, port):
        self.connectRequested.emit(host, port)

    def request(self, op, body=None, context=""):
        self.requestRequested.emit(op, dict(body or {}), context)

    def close(self):
        self.closeRequested.emit(True, "disconnected")

    def drive(self, body):
        self.driveRequested.emit(dict(session=self.session, at=time.monotonic(), body=dict(body)))

    def interrupt(self, op, body, context=""):
        self.interruptRequested.emit(op, dict(body), context)

    def shutdown(self):
        if self.thread.isRunning():
            self.shutdownRequested.emit()
            # Only final application teardown waits; normal GUI actions never wait.
            self.thread.wait()
