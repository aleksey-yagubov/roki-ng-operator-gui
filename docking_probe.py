"""Local KDDockWidgets/QML experiment. No networking or robot commands."""

import argparse
import ctypes
import ctypes.util
import json
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtTest import QTest
import shiboken6

ROOT = Path(__file__).resolve().parent


def set_sink_item(sink, item):
    # PyGObject cannot directly convert a Shiboken QObject to a gpointer.
    # Keep this bridge isolated; all actual GUI/media work stays in Qt/GStreamer.
    class GValue(ctypes.Structure):
        _fields_ = [("g_type", ctypes.c_size_t), ("data", ctypes.c_uint64 * 2)]

    lib = ctypes.CDLL(ctypes.util.find_library("gobject-2.0"))
    lib.g_type_from_name.argtypes = [ctypes.c_char_p]
    lib.g_type_from_name.restype = ctypes.c_size_t
    lib.g_value_init.argtypes = [ctypes.POINTER(GValue), ctypes.c_size_t]
    lib.g_value_init.restype = ctypes.POINTER(GValue)
    lib.g_value_set_pointer.argtypes = [ctypes.POINTER(GValue), ctypes.c_void_p]
    lib.g_value_set_pointer.restype = None
    lib.g_object_set_property.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(GValue)]
    lib.g_object_set_property.restype = None
    lib.g_value_unset.argtypes = [ctypes.POINTER(GValue)]
    lib.g_value_unset.restype = None
    value = GValue()
    lib.g_value_init(ctypes.byref(value), lib.g_type_from_name(b"gpointer"))
    try:
        pointer = shiboken6.getCppPointer(item)[0] if item else 0
        lib.g_value_set_pointer(ctypes.byref(value), pointer)
        lib.g_object_set_property(hash(sink), b"widget", ctypes.byref(value))
    finally:
        lib.g_value_unset(ctypes.byref(value))


class Probe(QObject):
    logChanged = Signal()
    clicksChanged = Signal()

    def __init__(self, app, args):
        super().__init__()
        self.app = app
        self.args = args
        self.lines = []
        self.clicks = 0
        self.pipeline = None
        self.sink = None
        self.video_item = None
        self.Gst = None
        self.errors = []
        self.snapshots = []
        self.window_changes = 0
        self.artifacts = ROOT / "artifacts" / (
            "docking" if not args.video else "video-static" if args.stationary else "video-move"
        )
        self.artifacts.mkdir(parents=True, exist_ok=True)
        if args.self_test:
            self.write_result(None)
        self.bus_timer = QTimer(self)
        self.bus_timer.timeout.connect(self.poll_bus)
        if args.video:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst
            self.Gst = Gst
            Gst.init(None)
            # Load the plugin before the QML engine resolves its video-item import.
            self.sink = Gst.ElementFactory.make("qml6glsink", "video_sink")
            if self.sink is None:
                raise RuntimeError("qml6glsink is not installed")

    @Property(bool, constant=True)
    def videoEnabled(self):
        return self.args.video

    @Property(str, constant=True)
    def layoutPath(self):
        return str(self.artifacts / "layout.json")

    @Property(str, notify=logChanged)
    def logText(self):
        return "\n".join(self.lines)

    @Property(int, notify=clicksChanged)
    def clickCount(self):
        return self.clicks

    @Slot(str)
    def note(self, text):
        print(text, flush=True)
        self.lines = (self.lines + [text])[-100:]
        self.logChanged.emit()

    @Slot()
    def increment(self):
        self.clicks += 1
        self.clicksChanged.emit()
        self.note(f"Python callback #{self.clicks}")

    def qml_warnings(self, warnings):
        for warning in warnings:
            self.errors.append(str(warning))
            self.note(str(warning))

    @Slot(QObject)
    def attachVideo(self, item):
        self.video_item = item
        item.windowChanged.connect(self.window_changed)
        QTimer.singleShot(300, self.start_video)

    def window_changed(self, window):
        self.window_changes += 1
        pointer = shiboken6.getCppPointer(window)[0] if window else 0
        self.note(f"video QQuickWindow changed: {pointer:#x}")

    def start_video(self):
        try:
            Gst = self.Gst
            self.pipeline = Gst.parse_launch(
                "videotestsrc is-live=true pattern=ball ! "
                "video/x-raw,width=800,height=650,framerate=60/1 ! "
                "glupload ! glcolorconvert ! queue name=output"
            )
            self.pipeline.add(self.sink)
            if not self.pipeline.get_by_name("output").link(self.sink):
                raise RuntimeError("Cannot link qml6glsink")
            set_sink_item(self.sink, self.video_item)
            if self.sink.set_state(Gst.State.READY) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("qml6glsink READY failed")
            self.bus_timer.start(100)
            result = self.pipeline.set_state(Gst.State.PLAYING)
            self.note(f"pipeline PLAYING: {result.value_nick}")
            if result == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Pipeline failed to start")
        except Exception as exc:
            self.errors.append(str(exc))
            self.note(f"ERROR: {exc}")

    def poll_bus(self):
        if not self.pipeline:
            return
        Gst = self.Gst
        bus = self.pipeline.get_bus()
        while (message := bus.pop()) is not None:
            if message.type == Gst.MessageType.ERROR:
                error, debug = message.parse_error()
                self.errors.append(str(error))
                self.note(f"GST ERROR: {error}: {debug}")
            elif message.type == Gst.MessageType.WARNING:
                error, debug = message.parse_warning()
                self.note(f"GST WARNING: {error}: {debug}")

    def shutdown(self):
        self.bus_timer.stop()
        if self.pipeline:
            self.pipeline.set_state(self.Gst.State.NULL)
            set_sink_item(self.sink, None)
            self.pipeline = None

    def click(self, name):
        item = self.window.findChild(QObject, name)
        assert item is not None, name
        assert item.isVisible() and item.isEnabled(), name
        position = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(item.window(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, position)
        QTest.qWait(600)

    def snapshot(self, name, expect_video=True):
        self.poll_bus()
        assert not self.errors, self.errors
        record = {"name": name, "window_changes": self.window_changes}
        if self.sink and expect_video:
            stats = self.sink.get_property("stats")
            rendered = stats.get_value("rendered")
            assert rendered > 0, "No frames rendered"
            record["rendered"] = rendered
            record["dropped"] = stats.get_value("dropped")
            QTest.qWait(250)
            assert self.sink.get_property("stats").get_value("rendered") > rendered
            window = self.video_item.window()
            assert window and self.video_item.width() > 0 and self.video_item.height() > 0
        else:
            window = self.window
        image = window.grabWindow()
        assert not image.isNull(), "Empty window screenshot"
        assert image.save(str(self.artifacts / f"{name}.png"))
        self.snapshots.append(record)
        self.note(f"PASS {name}: {record}")

    def write_result(self, passed):
        (self.artifacts / "result.json").write_text(json.dumps({
            "passed": passed, "snapshots": self.snapshots, "errors": self.errors,
        }, indent=2) + "\n")

    def self_test(self):
        try:
            QTest.qWait(1200)
            self.click("pythonButton")
            assert self.clicks == 1
            self.snapshot("01-docked")
            if self.args.stationary:
                QTest.qWait(2000)
                self.snapshot("02-still-playing")
                self.note("STATIONARY SELF-TEST PASSED (no window transitions)")
                self.write_result(True)
                self.app.exit(0)
                return
            self.click("saveButton")
            assert Path(self.layoutPath).is_file()
            self.click("floatButton")
            dock = self.window.findChild(QObject, "videoDock")
            assert dock.property("isFloating")
            self.snapshot("02-floating")
            self.click("floatButton")
            assert not dock.property("isFloating")
            self.snapshot("03-redocked")
            self.click("hideButton")
            assert not dock.property("isOpen")
            self.snapshot("04-hidden", expect_video=False)
            self.click("hideButton")
            assert dock.property("isOpen")
            self.snapshot("05-shown")
            self.click("tabButton")
            self.snapshot("06-tabbed")
            self.click("restoreButton")
            self.snapshot("07-restored")
            self.window.resize(800, 600)
            QTest.qWait(500)
            self.snapshot("08-small")
            self.note("SELF-TEST PASSED")
            result = 0
        except Exception:
            self.errors.append(traceback.format_exc())
            self.note(self.errors[-1])
            result = 1
        self.write_result(result == 0)
        self.app.exit(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", action="store_true", help="Enable experimental qml6glsink; floating may abort GStreamer")
    parser.add_argument("--stationary", action="store_true", help="Self-test without window transitions")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.video and not args.stationary:
        print("WARNING: moving live video can crash GStreamer 1.28.7. This is a reproducer, not production UI.", flush=True)
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    QGuiApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QGuiApplication([sys.argv[0]])
    probe = Probe(app, args)
    engine = QQmlApplicationEngine()
    module_root = ROOT / "native" / "qml"
    if not module_root.is_dir():
        module_root = ROOT / ".deps" / "build" / "KDDockWidgets"
    engine.addImportPath(str(module_root))
    engine.rootContext().setContextProperty("probe", probe)
    engine.warnings.connect(probe.qml_warnings)
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "DockingProbe.qml")))
    if not engine.rootObjects():
        return 1
    probe.window = engine.rootObjects()[0]
    app.aboutToQuit.connect(probe.shutdown)
    if args.self_test:
        QTimer.singleShot(800, probe.self_test)
    try:
        return app.exec()
    finally:
        probe.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
