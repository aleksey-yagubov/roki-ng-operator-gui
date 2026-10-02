"""Render localisation markers and click display options without robot hardware."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickView
from PySide6.QtTest import QTest
from shiboken6 import delete

from operator_gui.controller import Controller
from tests.fake_robot import FakeRobot
from tests.test_operator import wait_until


def main():
    app = QGuiApplication([])
    robot = FakeRobot()
    robot.localisation_enabled = robot.localisation_running = True
    robot.localisation_fit = 'matched'
    with tempfile.TemporaryDirectory() as directory:
        backend = Controller('127.0.0.1', robot.port, Path(directory))
        window = QQuickView()
        window.setResizeMode(QQuickView.SizeRootObjectToView)
        window.resize(900, 1200)
        context = window.rootContext()
        for name, obj in (('backend', backend), ('controls', backend.control), ('localisation', backend.localisation)):
            context.setContextProperty(name, obj)
        warnings = []
        window.engine().warnings.connect(lambda messages: warnings.extend(str(m) for m in messages))
        window.setSource(QUrl.fromLocalFile(str(ROOT / 'qml/LocalisationPanel.qml')))
        window.show()
        try:
            assert window.rootObject() is not None, warnings
            item = lambda name: window.rootObject().findChild(QObject, name)
            backend.connectRobot('127.0.0.1', robot.port)
            wait_until(lambda: backend.transport.connected)
            backend.localisation.check()
            wait_until(lambda: backend.localisation.available and not backend.localisation.pending)
            state = robot._result('localisation.status', {})

            def update(result, age=10):
                backend.localisation.response('localisation.status', dict(state, result=result, age_ms=age), 'localisation:status')
                QTest.qWait(80)

            def click(name):
                button = item(name)
                centre = button.mapToScene(QPointF(button.width()/2, button.height()/2)).toPoint()
                QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, centre)
                QTest.qWait(80)

            def has_colour(pose, colour):
                canvas = item('localisationMap')
                g = state['geometry']
                ppm = min((canvas.width()-50)/g['carpet_width'], (canvas.height()-50)/g['carpet_length'])
                centre = canvas.mapToScene(QPointF(canvas.width()/2-pose[1]*ppm,
                                                  canvas.height()/2-pose[0]*ppm)).toPoint()
                image = window.grabWindow()
                assert not image.isNull()
                scale = image.devicePixelRatio()
                x, y = round(centre.x()*scale), round(centre.y()*scale)
                radius = round(10*scale)
                return any(image.pixelColor(i, j).name() == colour
                           for i in range(max(0, x-radius), min(image.width(), x+radius+1))
                           for j in range(max(0, y-radius), min(image.height(), y+radius+1)))

            good = dict(state['result'])
            update(good)
            assert has_colour(good['candidate'], '#ffad42')
            update(good, 2000)
            assert has_colour(good['candidate'], '#a9adb3')
            assert item('localisationLastPoseAge').isVisible()
            before = len(robot.requests)
            click('localisationShowLast')
            assert not has_colour(good['candidate'], '#a9adb3')
            click('localisationShowLast')
            bad = dict(good, candidate=[.5, .5, 0.], fit_state='weak')
            update(bad)
            assert not has_colour(bad['candidate'], '#ff7070')
            click('localisationShowQuestionable')
            assert has_colour(bad['candidate'], '#ff7070')
            assert has_colour(good['candidate'], '#a9adb3')
            update(dict(candidate=None, reason='insufficient_observations', lines=2))
            assert 'insufficient_observations' in item('localisationResultSummary').property('text')
            assert not has_colour(bad['candidate'], '#ff7070')
            assert has_colour(good['candidate'], '#a9adb3')
            assert not any(m['op'] != 'session.heartbeat' for m in robot.requests[before:]), robot.requests[before:]
            assert not warnings, warnings
            print('PASS localisation QML: current/stale/questionable markers, toggles, missing observations')
        finally:
            backend.shutdown()
            robot.close()
            delete(window)
            app.processEvents()


if __name__ == '__main__':
    main()
