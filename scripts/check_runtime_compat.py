#!/usr/bin/env python3
"""Integration against a LOCAL roki-ng --simulate subprocess, never hardware."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication

from operator_gui.controller import Controller
from tests.test_operator import wait_until


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-dir", type=Path, default=ROOT.parent / "roki-ng")
    parser.add_argument("--exercise-controls", action="store_true", help="Exercise motions on SimHardware only")
    args = parser.parse_args()
    app = QCoreApplication([])
    output = ROOT / "artifacts" / "runtime-compat"
    output.mkdir(parents=True, exist_ok=True)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="operator-runtime-") as state, (output / "runtime.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "roki_ng", "--simulate", "--skip-bootstrap",
                                    *([] if args.exercise_controls else ["--body-disabled"]),
                                    "--host", "127.0.0.1", "--port", str(port),
                                    "--state-dir", state], cwd=args.runtime_dir, stdout=log, stderr=subprocess.STDOUT)
        controller = Controller("127.0.0.1", port, output)
        result = {"passed": False}
        try:
            # Session retries handle the supervisor's socket becoming ready.
            controller.connectRobot("127.0.0.1", port)
            wait_until(lambda: controller.transport.connected, 5000)
            controller.requestStatus()
            wait_until(lambda: controller.last_status_at is not None)
            if controller.mode == "BOOTSTRAP":
                controller.requestStatus()
                wait_until(lambda: controller.mode != "BOOTSTRAP", 5000)
            assert controller.mode == "IDLE", controller.status_text
            assert controller.owner == "Нет владельца", controller.owner
            for kind in ("slots", "tests", "parameters"):
                controller.requestCatalog(kind)
                wait_until(lambda: kind not in controller.pages)
                assert getattr(controller, kind).rowCount() > 0, kind
            key = controller.parameters.items[0]["name"]
            controller.inspectParameter(key)
            wait_until(lambda: "value" in controller.param_parts and "description" in controller.param_parts)
            controller.describeTest("run_test")
            wait_until(lambda: "run_test" in controller.test_text)
            data = controller.data_sources
            data.requestList()
            wait_until(lambda: len(data.topics) >= 4)
            for topic in data.topics:
                data.select(topic["name"])
                data.snapshot()
                wait_until(lambda: data.view["received"] and not data.view["busy"])
                data.subscribe(2)
                wait_until(lambda: data.view["active"] and data.sequences.get(data.selected, 0) > 0)
                data.unsubscribe()
                wait_until(lambda: not data.view["watching"])
                assert not data.error, data.error
            assert not controller.control.owns
            result["data_sources"] = [t["name"] for t in data.topics]
            if args.exercise_controls:
                c = controller.control
                c.acquire()
                wait_until(lambda: c.owns)
                c.enterManual()
                wait_until(lambda: c.view["manual"] and not c.pending)
                c.pose("base_stand")
                wait_until(lambda: c.job.get("status") == "completed", 12000)
                assert not c.error, c.error
                c.head(100, -500)
                wait_until(lambda: c.pan == 100 and c.tilt == -500)
                c.hold("forward", True)
                # Let the GUI and transport run normally while the simulated gait advances.
                from PySide6.QtCore import QEventLoop, QTimer
                loop = QEventLoop()
                QTimer.singleShot(700, loop.quit)
                loop.exec()
                c.hold("forward", False)
                c.stop(True)
                wait_until(lambda: not c.pending)
                c.pose("base_stand")
                wait_until(lambda: c.job.get("status") == "completed", 12000)
                controller.startTest("jump_test", {"direction": "forward", "count": 1})
                wait_until(lambda: c.job.get("operation") == "test.start")
                wait_until(lambda: c.job.get("status") == "completed", 12000)
                result["test_job"] = c.job
                controller.inspectParameter("head.field_tilt")
                wait_until(lambda: controller.param_parts.get("key") == "head.field_tilt" and "value" in controller.param_parts)
                controller.saveParameter("head.field_tilt", "-1200")
                wait_until(lambda: controller.param_parts.get("value") == -1200)
                c.release()
                wait_until(lambda: not c.owns and not c.pending)
                assert not c.error, c.error
                result["controls_exercised"] = True
            assert process.poll() is None, "Supervisor exited"
            result.update(passed=True, state=controller.mode, slots=controller.slots.rowCount(),
                          tests=controller.tests.rowCount(), parameters=controller.parameters.rowCount(),
                          workers=controller.workers.items)
        finally:
            controller.shutdown()
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
