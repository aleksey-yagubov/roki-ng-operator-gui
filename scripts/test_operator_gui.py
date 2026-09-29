#!/usr/bin/env python3
"""Real Qt clicks and window transitions against a loopback-only fake robot."""

import json
from pathlib import Path
import sys
import threading
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QEventLoop, QMetaObject, QObject, QPointF, QTimer, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQuick import QQuickItem
from PySide6.QtQml import QQmlExpression
from PySide6.QtTest import QTest

from operator_gui.controller import Controller
from roki_operator import create_engine
from operator_gui.appearance import configure as configure_appearance
from tests.fake_robot import FakeRobot
from tests.test_operator import wait_until


def settle(milliseconds=200):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main():
    output = ROOT / "artifacts" / "operator-gui"
    output.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication([sys.argv[0]])
    configure_appearance(app)
    app.setOrganizationName("ROKI-test")
    app.setApplicationName("operator-test")
    robot = FakeRobot()
    backend = Controller("127.0.0.1", robot.port, output)
    backend.control.install_keyboard(app)
    engine = create_engine(backend)
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(str(m) for m in messages))
    engine.load(QUrl.fromLocalFile(str(ROOT / "qml" / "Operator.qml")))
    if not engine.rootObjects():
        backend.shutdown()
        robot.close()
        return 1
    window = engine.rootObjects()[0]
    result = {"passed": False, "checks": [], "qml_warnings": warnings}
    inspected_items = []

    def item(name):
        obj = window.findChild(QObject, name)
        if obj is None:
            # Traverse the visual tree in QML, not via Python wrappers for native
            # KDDW internals. Repeater delegates aren't QObject children of the view.
            expression = QQmlExpression(engine.rootContext(), window,
                "(function find(o) { if (o.objectName === " + json.dumps(name) + ") return o;"
                "for (let c of o.children || []) { let r = find(c); if (r) return r; }"
                "return null; })(contentItem)")
            obj, _ = expression.evaluate()
        assert obj is not None, f"Missing {name}"
        inspected_items.append(obj)
        return obj

    def click(name, first_row=False):
        obj = item(name)
        assert isinstance(obj, QQuickItem) and obj.isVisible() and obj.isEnabled(), name
        center = obj.mapToScene(QPointF(obj.width() / 2, 13 if first_row else obj.height() / 2))
        target = obj.window()
        assert 0 <= center.x() < target.width() and 0 <= center.y() < target.height(), f"Clipped {name}: {center}"
        QTest.mouseClick(target, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, center.toPoint())
        settle()

    def show(name):
        dock = item(name)
        assert QMetaObject.invokeMethod(dock, "open")
        assert QMetaObject.invokeMethod(dock, "setAsCurrentTab")
        settle()
        return dock

    def snapshot(name):
        assert not warnings, warnings
        assert window.grabWindow().save(str(output / f"{name}.png"))
        result["checks"].append(name)
        print("PASS", name, flush=True)

    def run():
        try:
            settle(300)
            assert robot.requests == [], "UI startup must not contact robot"
            assert item("robotHost").property("text") == "127.0.0.1"
            item("robotHost").setProperty("text", "192.0.2.7")
            settle(1100)
            assert item("robotHost").property("text") == "192.0.2.7", "Idle updates overwrote user input"
            item("robotHost").setProperty("text", "127.0.0.1")
            snapshot("01-disconnected")
            click("connectButton")
            wait_until(lambda: backend.transport.connected)
            wait_until(lambda: any(m["op"] == "session.heartbeat" for m in robot.requests))
            assert {m["op"] for m in robot.requests} <= {"hello", "session.heartbeat", "log.subscribe"}
            snapshot("02-connected-no-side-effects")
            show("statusDock")
            click("statusButton")
            wait_until(lambda: backend.last_status_at is not None)
            click("capabilitiesButton")
            wait_until(lambda: "simulated" in backend.capabilities_text)
            snapshot("03-status")
            show("catalogDock")
            click("catalogButton")
            wait_until(lambda: backend.slots.rowCount() == 57)
            snapshot("04-slots")
            click("testsTab")
            click("catalogButton")
            wait_until(lambda: backend.tests.rowCount() == 4)
            wait_until(lambda: len(backend.test_schemas) == 4)
            settle()
            assert not item("startTest_run_test").isEnabled()
            snapshot("05-tests")
            show("parametersDock")
            click("parametersButton")
            wait_until(lambda: backend.parameters.rowCount() == 3)
            assert not item("parameterDetailScroll").isVisible()
            group = item("parameterGroup")
            # Activate the ComboBox through its normal keyboard interaction.
            click("parameterGroup")
            QTest.keyClick(window, Qt.Key.Key_End)
            QTest.keyClick(window, Qt.Key.Key_Return)
            settle()
            assert backend.parameter_filter.rowCount() == 1
            snapshot("06-parameter-groups")
            click("parameterGroup")
            QTest.keyClick(window, Qt.Key.Key_Home)
            QTest.keyClick(window, Qt.Key.Key_Return)
            settle()
            click("parametersList", first_row=True)
            wait_until(lambda: "value" in backend.param_parts and "description" in backend.param_parts)
            snapshot("06-parameters")
            assert not item("saveParameterButton").isEnabled()
            assert item("parameterDetailScroll").height() < item("parametersList").parentItem().height() * 0.65
            show("dataDock")
            click("dataListButton")
            wait_until(lambda: len(backend.data_sources.topics) == 4)
            assert not backend.data_sources.wanted
            click("dataSnapshotButton")
            wait_until(lambda: backend.data_sources.view["received"])
            click("dataSubscribeButton")
            wait_until(lambda: backend.data_sources.view["active"])
            robot.send_data("system.workers", 1)
            wait_until(lambda: backend.data_sources.sequences.get("system.workers") == 1)
            snapshot("06-data-sources")
            click("dataUnsubscribeButton")
            wait_until(lambda: not backend.data_sources.wanted)
            assert robot.owner is None and robot.mode == "GAME"
            window.resize(max(800, window.minimumWidth()), max(700, window.minimumHeight()))
            settle()
            for name in ("dataListButton", "dataSnapshotButton", "dataSubscribeButton", "dataUnsubscribeButton", "dataFields", "dataRawDetails"):
                obj = item(name)
                edge = obj.mapToScene(QPointF(obj.width(), obj.height()))
                origin = obj.mapToScene(QPointF(0, 0))
                assert origin.x() >= 0 and origin.y() >= 0 and edge.x() <= window.width() and edge.y() <= item("logsList").mapToScene(QPointF(0, 0)).y(), f"Clipped {name}: {edge}; window={window.width()}x{window.height()}, logs_y={item('logsList').mapToScene(QPointF(0,0)).y()}"
            snapshot("06-data-minimum-window")
            window.resize(1200, 800)
            settle()
            show("parametersDock")
            robot.send_log("GUI test message", "WARNING")
            wait_until(lambda: any(r["message"] == "GUI test message" for r in backend.history))
            click("autoscrollCheck")
            assert not item("autoscrollCheck").property("checked")
            click("pauseLogsCheck")
            before = backend.logs.rowCount()
            robot.send_log("arrived while paused")
            wait_until(lambda: any(r["message"] == "arrived while paused" for r in backend.history))
            assert backend.logs.rowCount() == before
            click("pauseLogsCheck")
            assert not backend.logs_paused
            snapshot("07-logs")
            ticks = []
            ui_timer = QTimer()
            ui_timer.setInterval(20)
            ui_timer.timeout.connect(lambda: ticks.append(time.monotonic()))
            ui_timer.start()

            def flood_logs():
                for index in range(600):
                    robot.send_log(f"GUI burst {index}")

            sender = threading.Thread(target=flood_logs)
            sender.start()
            try:
                wait_until(lambda: not sender.is_alive(), 5000)
            finally:
                sender.join(2)
            settle(1500)
            ui_timer.stop()
            assert len(ticks) >= 30, "GUI timer stalled during log burst"
            max_gap = max(b - a for a, b in zip(ticks, ticks[1:]))
            assert max_gap < 0.5, max_gap
            result["gui_timer_max_gap_ms"] = round(max_gap * 1000, 2)
            assert backend.transport.connected
            result["checks"].append("log-burst-responsive")
            click("saveLayoutButton")
            assert Path(backend.layoutPath).is_file()
            dock = item("parametersDock")
            dock.setProperty("isFloating", True)
            settle(300)
            assert dock.property("isFloating")
            click("parametersButton")
            wait_until(lambda: not backend.pages)
            floating_window = item("parametersButton").window()
            assert floating_window != window
            assert floating_window.grabWindow().save(str(output / "08-floating.png"))
            result["checks"].append("08-floating")
            dock.setProperty("isFloating", False)
            settle()
            assert not dock.property("isFloating")
            assert QMetaObject.invokeMethod(dock, "forceClose")
            settle()
            assert not dock.property("isOpen")
            click("restoreLayoutButton")
            settle(300)
            assert dock.property("isOpen")
            snapshot("09-restored")
            window.resize(max(800, window.minimumWidth()), max(700, window.minimumHeight()))
            settle(300)
            show("connectionDock")
            click("disconnectButton")
            wait_until(lambda: not backend.transport.connected)
            snapshot("10-small")
            assert window.minimumWidth() == 1200 and window.minimumHeight() == 800
            window.resize(window.minimumWidth(), window.minimumHeight())
            settle(300)
            for name in ("robotHost", "parametersList", "logsList"):
                obj = item(name)
                edge = obj.mapToScene(QPointF(obj.width(), obj.height()))
                assert edge.x() <= window.width() and edge.y() <= window.height(), f"Clipped {name}: {edge}; window={window.width()}x{window.height()}, logs_y={item('logsList').mapToScene(QPointF(0,0)).y()}"
            snapshot("11-minimum")
            assert robot.game_running
            assert not any(m["op"] in ("control.acquire", "mode.set", "video.start", "test.start", "motion.pose") for m in robot.requests)
            window.resize(1200, 900)
            show("connectionDock")
            click("connectButton")
            wait_until(lambda: backend.transport.connected)
            show("parametersDock")
            click("acquireButton")
            wait_until(lambda: backend.control.owns)
            assert robot.mode == "GAME", "Acquiring control must not change mode"
            backend.inspectParameter("head.field_tilt")
            wait_until(lambda: "value" in backend.param_parts)
            editor = item("parameterEditor").findChild(QObject, "valueInput")
            editor.setProperty("text", "-1150")
            click("saveParameterButton")
            wait_until(lambda: robot.values.get("head.field_tilt") == -1150)
            assert robot.mode == "GAME", "Editing a parameter must not enter manual mode"
            snapshot("12-global-control")
            show("catalogDock")
            assert item("catalogManualButton").isEnabled()
            assert "ручной режим" in item("catalogBlockedReason").property("text")
            click("catalogManualButton")
            wait_until(lambda: backend.control.view["manual"] and not backend.control.pending)
            show("manualDock")
            click("baseStandButton")
            wait_until(lambda: backend.control.moving)
            assert not item("baseStandButton").isEnabled()
            click("hardStopButton")
            wait_until(lambda: not backend.control.moving and not backend.control.pending)
            snapshot("12-manual-controls")
            click("keyboardCheck")
            assert backend.control.keyboard
            before_tilt = backend.control.tilt
            QTest.keyClick(window, Qt.Key.Key_Up)
            wait_until(lambda: backend.control.tilt == before_tilt + backend.control.head_step and not backend.control.pending)
            QTest.keyClick(window, Qt.Key.Key_Down)
            wait_until(lambda: backend.control.tilt == before_tilt and not backend.control.pending)
            QTest.keyPress(window, Qt.Key.Key_W)
            wait_until(lambda: any(m["op"] == "motion.drive" and m["body"]["x"] == 1 for m in robot.requests))
            QTest.keyRelease(window, Qt.Key.Key_W)
            wait_until(lambda: any(m["op"] == "motion.drive" and m["body"]["x"] == 0 for m in robot.requests))
            show("parametersDock")
            click("parametersButton")
            wait_until(lambda: backend.parameters.rowCount() == 3)
            click("parametersList", first_row=True)
            wait_until(lambda: "value" in backend.param_parts)
            editor = item("parameterEditor").findChild(QObject, "valueInput")
            editor.setProperty("text", "-1200")
            settle(1100)
            assert editor.property("text") == "-1200", "Periodic status reset draft"
            click("saveParameterButton")
            wait_until(lambda: robot.values.get("head.field_tilt") == -1200)
            snapshot("13-parameter-editor")
            show("fieldDock")
            backend.field_editor.values.update({'match.own_goal':0,
                'field.goal.0':{'colour':'yellow','x':-1.675,'y':0,'width':1.},
                'field.goal.1':{'colour':'blue','x':1.675,'y':0,'width':1.}})
            backend.field_editor.changed.emit();settle()
            click("ownBlueGoal")
            wait_until(lambda: backend.field_editor.view['ownColour']=='blue' and not backend.control.pending)
            assert robot.values['match.own_goal']==1
            click("ownYellowGoal")
            wait_until(lambda: backend.field_editor.view['ownColour']=='yellow' and not backend.control.pending)
            assert robot.values['match.own_goal']==0
            snapshot("13e-own-goal-colour")
            show("visionDock")
            tuning=backend.vision_tuning
            tuning.profile='green_field';tuning.profiles=['green_field']
            for axis,low,high in [('l',0,100),('a',-128,127),('b',-128,127)]:
                for suffix,value in [('min',low),('max',high)]:
                    key=f'vision.green_field.{axis}_{suffix}'
                    tuning.metas[key]={'type':'int','min':low,'max':high,'default':value}
                    tuning.values[key]=value
            frame=QImage(800,650,QImage.Format.Format_RGB888);frame.fill(0xff208030)
            backend.video.image=frame;backend.video.last_image_at=time.monotonic();backend.video.image_serial+=1
            tuning.catalogChanged.emit();tuning.changed.emit();settle()
            click('tuningLive')
            wait_until(lambda: tuning.view['live'] and not tuning.source.isNull())
            previous=tuning.serial
            backend.video.image_serial+=1;backend.video.last_image_at=time.monotonic()
            wait_until(lambda: tuning.serial>previous)
            snapshot('13c-live-lab-preview')
            click('tuningSnapshot')
            assert not tuning.view['live']
            previous=tuning.serial
            backend.video.image_serial+=1;settle(300)
            assert tuning.serial==previous
            click('tuningLive')
            backend.video.last_image_at=time.monotonic()-4
            wait_until(lambda: tuning.source.isNull())
            snapshot('13d-live-lab-stale')
            # Existing Qt click harness exercises the actual QML panel and UDP path.
            show("localisationDock")
            click("localisationCheck")
            assert not backend.localisation.available
            assert 'Нужно обновить' in item('localisationStatus').property('text')
            assert 'не поддерживает' in item('localisationNotice').property('text')
            assert not item("localisationStart").isEnabled()
            robot.localisation_enabled=True
            click("localisationCheck")
            wait_until(lambda: backend.localisation.available and not backend.localisation.pending)
            item("localisationPriorX").setProperty("text","-1.2")
            item("localisationPriorY").setProperty("text","-0.8")
            item("localisationPriorYaw").setProperty("text","90")
            click("localisationStart")
            wait_until(lambda: backend.localisation.view['running'] and not backend.control.pending)
            assert len(backend.localisation.view['pose'])==3
            command=next(m for m in reversed(robot.requests) if m['op']=='localisation.start')
            assert abs(command['body']['prior'][2]-1.57079632679)<1e-8
            assert not item("localisationStart").isEnabled()
            snapshot("13a-localisation-candidate")
            robot.localisation_age=1800
            click("localisationRefresh")
            wait_until(lambda: not backend.localisation.pending)
            assert backend.localisation.view['pose']==[]
            assert 'свежей' in item("localisationStatus").property('text')
            snapshot("13b-localisation-stale")
            click("localisationStop")
            wait_until(lambda: not backend.localisation.view['running'] and not backend.control.pending)
            assert backend.localisation.view['pose']==[]

            show("catalogDock")
            click("catalogButton")
            wait_until(lambda: len(backend.test_schemas) == 4)
            click("startTest_run_test")
            wait_until(lambda: backend.control.moving)
            snapshot("14-test-running")
            click("hardStopButton")
            wait_until(lambda: not backend.control.pending)
            show("manualDock")
            click("releaseButton")
            wait_until(lambda: not backend.control.owns)
            assert not robot.errors, robot.errors
            result["passed"] = True
        except Exception:
            result["error"] = traceback.format_exc()
            print(result["error"], flush=True)
            window.grabWindow().save(str(output / "failure.png"))
        finally:
            result["operations"] = sorted({m["op"] for m in robot.requests})
            (output / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
            backend.shutdown()
            robot.close()
            app.exit(0 if result["passed"] else 1)

    QTimer.singleShot(500, run)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
