"""Headless QML contract check; no mouse interaction or robot hardware."""
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shiboken6 import delete
from PySide6.QtCore import QObject, QUrl, QMetaObject, Q_ARG
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from operator_gui.controller import Controller
from operator_gui.video_item import VideoImageProvider
from tests.fake_robot import FakeRobot
from tests.test_operator import wait_until
from tests.test_video import ReceiverStub


def main():
    app = QGuiApplication([])
    robot = FakeRobot()
    with tempfile.TemporaryDirectory() as directory:
        backend = Controller('127.0.0.1', robot.port, Path(directory))
        engine = QQmlApplicationEngine()
        engine.addImageProvider('streams', VideoImageProvider(backend.streams))
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
            assert not item('gameStart').property('enabled')
            assert not item('gamePickup').property('enabled')
            assert not item('gameStop').property('enabled')
            backend.connectRobot('127.0.0.1', robot.port)
            wait_until(lambda: backend.transport.connected)
            QMetaObject.invokeMethod(item('gameSubscribe'), 'clicked')
            wait_until(lambda: 'game.state' in backend.data_sources.active)
            robot.send_data('game.state', 1)
            wait_until(lambda: backend.game.view['fresh'])
            assert robot.owner is None
            robot.localisation_enabled = robot.localisation_running = True
            robot.localisation_fit = 'matched'
            QMetaObject.invokeMethod(item('gameWatchPosition'), 'clicked')
            wait_until(lambda: backend.localisation.view['subscribed'])
            robot.send_data('localisation.state', 1)
            wait_until(lambda: len(backend.localisation.view['pose']) == 3)
            panel.setProperty('visible', False)
            panel.setProperty('visible', True)
            assert backend.localisation.view['watching']
            assert not any(m['op'].startswith(('game.', 'localisation.')) for m in robot.requests)
            QMetaObject.invokeMethod(item('gameWatchPosition'), 'clicked')
            wait_until(lambda: not backend.localisation.view['watching'])
            QMetaObject.invokeMethod(item('gameSubscribe'), 'clicked')
            wait_until(lambda: not backend.game.view['watching'])
            backend.game.refresh()
            robot.game_running = False
            wait_until(lambda: not backend.game.pending)
            backend.game.refresh()
            wait_until(lambda: not backend.game.view['running'])
            backend.control.acquire()
            wait_until(lambda: backend.control.owns)
            backend.control.enterManual()
            wait_until(lambda: backend.control.mode == 'MANUAL' and not backend.control.pending)
            robot.game_running = False
            assert item('gameStart').property('enabled')
            QMetaObject.invokeMethod(item('gameStart'), 'clicked')
            wait_until(lambda: backend.game.view['running'])
            assert item('gameStop').property('enabled')
            assert not item('gameStart').property('enabled')
            QMetaObject.invokeMethod(item('gamePickup'), 'clicked')
            wait_until(lambda: backend.game.view['pickupReady'])
            assert item('gameStart').property('enabled')
            assert item('gameStart').property('text') == 'Повторный ввод'
            backend.game.stop()
            wait_until(lambda: not backend.game.view['running'] and backend.control.mode == 'MANUAL')
            assert item('gameStart').property('enabled')
            opened = []
            panel.requestStreams.connect(lambda: opened.append(True))
            QMetaObject.invokeMethod(item('gameOpenStreams'), 'clicked')
            assert opened and not any(m['op'].startswith('videostream.') for m in robot.requests)
            with patch('operator_gui.video.Receiver', ReceiverStub):
                backend.streams.refresh()
                wait_until(lambda: bool(backend.streams.names) and not backend.streams.pending)
                backend.streams.watch('stream', 0, 'avdec_h264')
                wait_until(lambda: 'stream' in backend.streams.players and backend.streams.players['stream'].phase == 'receiving')
                image = QImage(800, 650, QImage.Format.Format_RGB32)
                image.fill(0xff336699)
                backend.streams.players['stream'].receiver.imageReady.emit(image)
                item('gameVideoSelector').setProperty('currentIndex', 0)
                QMetaObject.invokeMethod(item('gameVideoSelector'), 'activated', Q_ARG(int, 0))
                loaded = QQmlExpression(engine.rootContext(), item('gameVideoImage'), 'status === 1')
                wait_until(lambda: loaded.evaluate()[0])
                assert item('gameVideoImage').property('sourceSize').width() == 800
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
