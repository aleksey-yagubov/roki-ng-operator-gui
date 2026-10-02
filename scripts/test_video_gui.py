#!/usr/bin/env python3
"""Real RTP + hardware decode + Qt rendering; local simulated robot only."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import traceback
import faulthandler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication, QEvent, QTimer, QUrl, QObject, QMetaObject
from PySide6.QtGui import QGuiApplication
from roki_operator import create_engine
from operator_gui.controller import Controller
from tests.test_operator import wait_until
from tests.fake_robot import FakeRobot


class MediaRobot(FakeRobot):
    def __init__(self):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst
        Gst.init(None)
        self.Gst, self.pipeline = Gst, None
        super().__init__()

    def _result(self, op, body):
        result = super()._result(op, body)
        if op == "videostream.subscribe":
            encode = "openh264enc bitrate=2000000 gop-size=30 ! h264parse ! rtph264pay pt=96 config-interval=1"
            launch = ("videotestsrc is-live=true pattern=smpte ! video/x-raw,format=I420,width=800,height=650,framerate=30/1 "
                      f"! {encode} ssrc={result['ssrc']} ! udpsink host=127.0.0.1 port={body['rtp_port']} sync=false")
            self.pipeline = self.Gst.parse_launch(launch)
            self.pipeline.set_state(self.Gst.State.PLAYING)
        elif op in ("videostream.stop", "videostream.unsubscribe") and self.pipeline:
            self.pipeline.set_state(self.Gst.State.NULL)
            self.pipeline = None
        return result

    def close(self):
        super().close()
        if self.pipeline:
            self.pipeline.set_state(self.Gst.State.NULL)


def port():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    faulthandler.enable()
    faulthandler.dump_traceback_later(25, repeat=True)
    app = QGuiApplication([sys.argv[0]])
    output = ROOT / "artifacts" / "video-gui"
    output.mkdir(parents=True, exist_ok=True)
    report = {"passed": False, "cycles": []}
    with tempfile.TemporaryDirectory() as state, (output / "robot.log").open("w") as log:
        robot = MediaRobot()
        control_port, video_port = robot.port, port()
        controller = Controller("127.0.0.1", control_port, Path(state))
        engine = create_engine(controller)
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(str(i) for i in items))
        engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Operator.qml")))
        window = engine.rootObjects()[0]


        def run():
            try:
                controller.connectRobot("127.0.0.1", control_port)
                wait_until(lambda: controller.transport.connected, 6000)
                controller.control.acquire()
                wait_until(lambda: controller.control.owns)
                controller.control.enterManual()
                wait_until(lambda: controller.control.view["manual"] and not controller.control.pending)
                manager = controller.streams
                manager.refresh()
                wait_until(lambda: len(manager.names)==3 and bool(manager.capabilities) and not manager.pending)
                first = controller.video_views.add("")
                second = controller.video_views.add("")
                image_dock = window.findChild(QObject, "viewDock-" + first)
                item = window.findChild(QObject, "viewImage-" + first)
                other = window.findChild(QObject, "viewImage-" + second)
                assert item and other and image_dock
                QMetaObject.invokeMethod(image_dock,"setAsCurrentTab")
                choices = (("h264", "avdec_h264"),)
                if sys.platform == "linux": choices = (("h264", "vah264dec"),) + choices
                for codec, decoder in choices:
                    QMetaObject.invokeMethod(image_dock, "open")
                    QMetaObject.invokeMethod(image_dock, "setAsCurrentTab")
                    ident = "stream"
                    controller.video_views.select(first,ident)
                    controller.video_views.select(second,ident)
                    manager.watch(ident,0,decoder)
                    wait_until(lambda: ident in manager.players)
                    video = manager.players[ident]
                    controller.video_views.select(first,ident)
                    controller.video_views.select(second,ident)
                    wait_until(lambda: video.view["frames"] >= 30 or bool(video.error), 15000)
                    assert not video.error, video.error
                    assert video.view["size"] == "800x650", video.view
                    wait_until(lambda: video.view["fps"] is not None and 25 < video.view["fps"] < 35, 5000)
                    assert not warnings, warnings
                    assert item.window() == window
                    run_id = video.info["run_id"]
                    before = video.image_serial
                    image_dock.setProperty("isFloating", True)
                    wait_until(lambda: item.window() != window and video.image_serial > before + 5)
                    assert video.info["run_id"] == run_id
                    assert item.window().grabWindow().save(str(output / f"{len(report['cycles'])}-floating.png"))
                    before = video.image_serial
                    image_dock.setProperty("isFloating", False)
                    wait_until(lambda: item.window() == window and video.image_serial > before + 5)
                    QMetaObject.invokeMethod(image_dock, "forceClose")
                    before = video.image_serial
                    wait_until(lambda: video.image_serial > before + 5)
                    QMetaObject.invokeMethod(image_dock, "open")
                    QMetaObject.invokeMethod(image_dock, "setAsCurrentTab")
                    assert video.info["run_id"] == run_id
                    frame = item.window().grabWindow()
                    assert frame.save(str(output / f"{len(report['cycles'])}-{codec}.png"))
                    report["cycles"].append(dict(codec=codec, decoder=decoder, fps=video.view["fps"], frames=video.view["frames"], size=video.view["size"]))
                    print("PASS", report["cycles"][-1], flush=True)
                    QMetaObject.invokeMethod(image_dock, 'forceClose')
                    before = video.image_serial
                    wait_until(lambda: video.image_serial > before + 5)
                    assert video.info["run_id"] == run_id
                    assert other.property("source") == item.property("source")
                    assert len([p for p in manager.players.values() if p.phase == "receiving"]) == 1
                    manager.unsubscribe(ident)
                    wait_until(lambda: video.phase=="stopped" and not manager.busy(ident), 5000)
                    wait_until(lambda: not str(item.property("source").toString()))
                    assert not image_dock.property("isOpen")
                QMetaObject.invokeMethod(window, "saveLayout")
                before=len([m for m in robot.requests if m['op'].startswith('videostream.') and m['op'] not in ('videostream.status','videostream.list')])
                controller.video_views.remove(first)
                controller.video_views.remove(second)
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                wait_until(lambda:window.findChild(QObject,"viewDock-"+first) is None)
                QMetaObject.invokeMethod(window, "restoreLayout")
                assert {e["id"] for e in controller.video_views.entries}=={first,second}
                assert all(e["stream"]=="" for e in controller.video_views.entries)
                assert window.findChild(QObject,"viewDock-"+first) is not None
                assert before==len([m for m in robot.requests if m['op'].startswith('videostream.') and m['op'] not in ('videostream.status','videostream.list')])
                assert not warnings,warnings
                assert not robot.errors, robot.errors
                report["passed"] = True
            except Exception:
                report["error"] = traceback.format_exc()
                report["robot_errors"] = robot.errors
                report["model"] = controller.streams.view
                report["requests"] = [m['op'] for m in robot.requests[-30:]]
                report["log"] = list(controller.history)[-20:]
                print(report["error"], flush=True)
            finally:
                report["warnings"] = warnings
                (output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
                controller.shutdown()
                app.exit(0 if report["passed"] else 1)

        QTimer.singleShot(400, run)
        try:
            return app.exec()
        finally:
            controller.shutdown()
            robot.close()
            engine.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    raise SystemExit(main())
