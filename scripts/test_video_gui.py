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
        if op == "videostream.start":
            spec = result["spec"]
            jpeg = spec["codec"]["name"] == "jpeg"
            encode = ("jpegenc ! rtpjpegpay pt=26" if jpeg else
                      "x264enc tune=zerolatency speed-preset=ultrafast bitrate=2000 key-int-max=30 ! rtph264pay pt=96 config-interval=1")
            launch = ("videotestsrc is-live=true pattern=smpte ! video/x-raw,format=I420,width=800,height=648,framerate=30/1 "
                      f"! {encode} ssrc=1234 ! udpsink host=127.0.0.1 port={body['rtp_port']} sync=false")
            self.pipeline = self.Gst.parse_launch(launch)
            self.pipeline.set_state(self.Gst.State.PLAYING)
        elif op in ("videostream.destroy", "videostream.detach") and self.pipeline:
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
        controller = Controller("127.0.0.1", control_port, output)
        engine = create_engine(controller)
        warnings = []
        engine.warnings.connect(lambda items: warnings.extend(str(i) for i in items))
        engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Operator.qml")))
        window = engine.rootObjects()[0]
        image_dock = window.findChild(QObject, "imageDock")

        def run():
            try:
                controller.connectRobot("127.0.0.1", control_port)
                wait_until(lambda: controller.transport.connected, 6000)
                controller.control.acquire()
                wait_until(lambda: controller.control.owns)
                controller.control.enterManual()
                wait_until(lambda: controller.control.view["manual"] and not controller.control.pending)
                video = controller.video
                video.getCapabilities()
                wait_until(lambda: bool(video.capabilities))
                choices = (("jpeg", "jpegdec"), ("h264", "avdec_h264"))
                if sys.platform != "darwin": choices = (("h264", "vah264dec"), ("jpeg", "vajpegdec")) + choices
                for codec, decoder in choices:
                    video.start(dict(sensorWidth=1600, sensorHeight=1300, depth=10, width=800,
                                     height=648, fps=30, codec=codec, bitrate=2000000,
                                     port=video_port, decoder=decoder))
                    wait_until(lambda: video.view["frames"] >= 30 or bool(video.error), 15000)
                    assert not video.error, video.error
                    assert video.view["size"] == "800x648", video.view
                    wait_until(lambda: video.view["fps"] is not None and 25 < video.view["fps"] < 35, 5000)
                    assert not warnings, warnings
                    assert video.item.window() == window
                    stream_id = video.info["stream_id"]
                    before = video.imageSerial
                    image_dock.setProperty("isFloating", True)
                    wait_until(lambda: video.item.window() != window and video.imageSerial > before + 5)
                    assert video.info["stream_id"] == stream_id
                    assert video.item.window().grabWindow().save(str(output / f"{len(report['cycles'])}-floating.png"))
                    before = video.imageSerial
                    image_dock.setProperty("isFloating", False)
                    wait_until(lambda: video.item.window() == window and video.imageSerial > before + 5)
                    QMetaObject.invokeMethod(image_dock, "forceClose")
                    before = video.imageSerial
                    wait_until(lambda: video.imageSerial > before + 5)
                    QMetaObject.invokeMethod(image_dock, "open")
                    QMetaObject.invokeMethod(image_dock, "setAsCurrentTab")
                    assert video.info["stream_id"] == stream_id
                    frame = video.item.window().grabWindow()
                    assert frame.save(str(output / f"{len(report['cycles'])}-{codec}.png"))
                    report["cycles"].append(dict(codec=codec, decoder=decoder, fps=video.view["fps"], frames=video.view["frames"], size=video.view["size"]))
                    print("PASS", report["cycles"][-1], flush=True)
                    video.closeWindow()
                    before = video.imageSerial
                    wait_until(lambda: video.imageSerial > before + 5)
                    assert video.info["stream_id"] == stream_id
                    video.stop()
                    wait_until(lambda: not video.info and not video.pending and not video.local_busy, 5000)
                    assert not image_dock.property("isOpen")
                assert not robot.errors, robot.errors
                report["passed"] = True
            except Exception:
                report["error"] = traceback.format_exc()
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
