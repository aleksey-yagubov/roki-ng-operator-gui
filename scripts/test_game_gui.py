"""Headless QML contract check; no mouse interaction or robot hardware."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shiboken6 import delete
from PySide6.QtCore import QObject, QUrl, QMetaObject
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from operator_gui.controller import Controller
from tests.fake_robot import FakeRobot
from tests.test_operator import wait_until


def main():
    app = QGuiApplication([])
    robot = FakeRobot()
    with tempfile.TemporaryDirectory() as directory:
        backend = Controller('127.0.0.1', robot.port, Path(directory))
        engine = QQmlApplicationEngine()
        engine.rootContext().setContextProperty('game', backend.game)
        engine.rootContext().setContextProperty('streams', backend.streams)
        engine.rootContext().setContextProperty('localisation', backend.localisation)
        warnings = []
        engine.warnings.connect(lambda messages: warnings.extend(str(m) for m in messages))
        engine.load(QUrl.fromLocalFile(str(ROOT/'qml/GamePanel.qml')))
        try:
            assert engine.rootObjects(), warnings
            panel = engine.rootObjects()[0]
            item = lambda name: panel.findChild(QObject, name)
            status = item('gameState')
            assert status.property('readOnly') and status.property('selectByMouse')
            QMetaObject.invokeMethod(status, 'selectAll')
            QMetaObject.invokeMethod(status, 'copy')
            assert app.clipboard().text() == status.property('text')
            assert not item('gameObserve').property('enabled')
            assert not item('gamePhysicalStart').property('enabled')
            assert not item('gameStop').property('enabled')
            backend.connectRobot('127.0.0.1', robot.port)
            wait_until(lambda: backend.transport.connected)
            backend.control.acquire()
            wait_until(lambda: backend.control.owns)
            backend.control.enterManual()
            wait_until(lambda: backend.control.mode == 'MANUAL' and not backend.control.pending)
            robot.game_running = False
            assert item('gameObserve').property('enabled')
            assert 'физическими' in item('gamePhysicalStart').property('text')
            backend.game.start(True, 0)
            wait_until(lambda: backend.game.view['running'])
            assert item('gameStop').property('enabled')
            assert not item('gameObserve').property('enabled')
            backend.game.stop()
            wait_until(lambda: not backend.game.view['running'] and backend.control.mode == 'MANUAL')
            assert item('gameObserve').property('enabled')
            assert not warnings, warnings
            print('Game QML controls passed; no QML warnings')
        finally:
            backend.shutdown()
            robot.close()
            delete(engine)
            app.processEvents()
    assert robot.errors == [], robot.errors


if __name__ == '__main__':
    main()
