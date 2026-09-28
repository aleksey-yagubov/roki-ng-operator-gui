#!/usr/bin/env python3
"""Start the operator shell. No connection or robot action is automatic."""

import argparse
from pathlib import Path
import signal
import sys

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

from operator_gui.appearance import configure as configure_appearance
from operator_gui.controller import Controller
from operator_gui.video_item import VideoImageProvider
from operator_gui.vision_tuning import TuningImages
from operator_gui.native_docking import configure as configure_docking

ROOT = Path(__file__).resolve().parent


def create_engine(controller):
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    engine = QQmlApplicationEngine()
    engine.addImageProvider("mainVideo", VideoImageProvider(controller.video))
    engine.addImageProvider("tuning",TuningImages(controller.vision_tuning))
    configure_docking(engine,ROOT)
    for name, value in {"backend": controller, "logsModel": controller.log_filter,
                        "controls": controller.control,
                        "fieldEditor": controller.field_editor,
                        "visionTuning":controller.vision_tuning,
                        "video": controller.video,
                        "dataSources": controller.data_sources, "dataFieldsModel": controller.data_sources.rows,
                        "slotsModel": controller.slots, "testsModel": controller.tests,
                        "parametersModel": controller.parameter_filter, "workersModel": controller.workers}.items():
        engine.rootContext().setContextProperty(name, value)
    return engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--robot", default="172.30.0.1", help="Pre-fill IPv4; does not connect")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--config-dir", type=Path, help="Override layout storage for testing")
    args = parser.parse_args()
    app = QGuiApplication([sys.argv[0]])
    configure_appearance(app)
    previous_sigint = signal.getsignal(signal.SIGINT)
    # Do not raise KeyboardInterrupt inside a QML property getter. No polling timer.
    signal.signal(signal.SIGINT, lambda _signum, _frame: app.exit(130))
    app.setOrganizationName("ROKI")
    app.setApplicationName("roki-ng-operator")
    config = args.config_dir or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation))
    config.mkdir(parents=True, exist_ok=True)
    controller = Controller(args.robot, args.port, config)
    controller.control.install_keyboard(app)
    try:
        engine = create_engine(controller)
    except Exception as exc:
        controller.shutdown()
        print(str(exc),file=sys.stderr)
        return 1
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Operator.qml")))
    if not engine.rootObjects():
        controller.shutdown()
        return 1
    app.aboutToQuit.connect(controller.shutdown)
    try:
        return app.exec()
    finally:
        controller.shutdown()
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
