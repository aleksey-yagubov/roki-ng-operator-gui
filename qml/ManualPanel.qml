import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    property var kddockwidgets_min_size: Qt.size(330, 290)
    contentWidth: Math.max(availableWidth, 520)
    clip: true
    onVisibleChanged: { if (!visible) controls.stopInput() }
    ColumnLayout {
        width: root.contentWidth
        spacing: 8
        Flow {
            Layout.fillWidth: true
            spacing: 4
            Button { objectName: "manualModeButton"; text: "Ручной режим"; enabled: controls.view.owns && !controls.view.manual && !controls.view.pending; onClicked: controls.enterManual() }
        }
        Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: controls.view.manual ? "Ручное управление активно" : controls.view.owns ? "Управление получено. Выберите ручной режим." : "Наблюдение: движения запрещены"
        }
        CheckBox {
            objectName: "keyboardCheck"
            text: "Клавиатура: WASD / QE / Shift+WASD / стрелки"
            checked: controls.view.keyboard
            enabled: controls.view.manual
            onToggled: controls.setKeyboard(checked)
        }
        GroupBox {
            title: "Walk"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                CheckBox {
                    id: holdCrouch
                    text: "Hold crouch after stop"
                    checked: true
                    onToggled: controls.driveSettings(speed.value, checked)
                }
                RowLayout {
                    Button { text: "Crouch"; enabled: controls.view.ready; onClicked: controls.pose("crouch") }
                    Button { text: "Stand"; enabled: controls.view.ready; onClicked: controls.pose("stand") }
                }
                Label { text: "Speed: " + Math.round(speed.value * 100) + "%" }
                Slider {
                    id: speed
                    Layout.fillWidth: true
                    from: 0.1
                    to: 1.0
                    value: 0.5
                    onMoved: controls.driveSettings(value, holdCrouch.checked)
                }
                RowLayout {
                    GridLayout {
                        columns: 3
                        Button { text: "Q"; enabled: controls.view.ready; onClicked: controls.jump("turn_left") }
                        Button { objectName: "walkForward"; text: "W"; enabled: controls.view.manual && !controls.view.pending; onPressed: controls.hold("forward", true); onReleased: controls.hold("forward", false); onCanceled: controls.hold("forward", false) }
                        Button { text: "E"; enabled: controls.view.ready; onClicked: controls.jump("turn_right") }
                        Button { text: "A"; enabled: controls.view.manual && !controls.view.pending; onPressed: controls.hold("left", true); onReleased: controls.hold("left", false); onCanceled: controls.hold("left", false) }
                        Button { text: "S"; enabled: controls.view.manual && !controls.view.pending; onPressed: controls.hold("backward", true); onReleased: controls.hold("backward", false); onCanceled: controls.hold("backward", false) }
                        Button { text: "D"; enabled: controls.view.manual && !controls.view.pending; onPressed: controls.hold("right", true); onReleased: controls.hold("right", false); onCanceled: controls.hold("right", false) }
                    }
                    GridLayout {
                        columns: 3
                        Item { width: 1; height: 1 }
                        Button { text: "Jump F"; enabled: controls.view.ready; onClicked: controls.jump("forward") }
                        Item { width: 1; height: 1 }
                        Button { text: "Jump L"; enabled: controls.view.ready; onClicked: controls.jump("left") }
                        Button { text: "Jump B"; enabled: controls.view.ready; onClicked: controls.jump("backward") }
                        Button { text: "Jump R"; enabled: controls.view.ready; onClicked: controls.jump("right") }
                    }
                }
            }
        }
        GroupBox {
            title: "Actions"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Layout.fillWidth: true
                    GridLayout {
                        columns: 2
                        Button { text: "Kick L"; enabled: controls.view.ready; onClicked: controls.kick("left", 80) }
                        Button { text: "Kick R"; enabled: controls.view.ready; onClicked: controls.kick("right", 80) }
                        Button { text: "Hard L"; enabled: false }
                        Button { text: "Hard R"; enabled: false }
                    }
                    Button { objectName: "baseStandButton"; text: "Base"; Layout.preferredWidth: 72; Layout.preferredHeight: 72; enabled: controls.view.ready; onClicked: controls.pose("base_stand") }
                    Button { text: "Reset\nQueue"; Layout.preferredWidth: 72; Layout.preferredHeight: 72; enabled: controls.view.owns; onClicked: controls.stop(true) }
                }
                Label { text: "Hard L/R: аппаратный удар ещё не поддерживается протоколом."; Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }
        GroupBox {
            title: "Head"
            Layout.fillWidth: true
            RowLayout {
                anchors.fill: parent
                ColumnLayout {
                    Layout.preferredWidth: 170
                    Layout.fillWidth: true
                    Label { text: "Pan: " + controls.headUi.pan }
                    Slider { objectName: "headPan"; Layout.fillWidth: true; from: -2666; to: 2666; stepSize: 1; value: controls.headUi.pan; onMoved: controls.setHeadUi(Math.round(value), controls.headUi.tilt) }
                    Label { text: "Tilt: " + controls.headUi.tilt }
                    Slider { objectName: "headTilt"; Layout.fillWidth: true; from: -2600; to: 950; stepSize: 1; value: controls.headUi.tilt; onMoved: controls.setHeadUi(controls.headUi.pan, Math.round(value)) }
                    RowLayout {
                        Button { text: "Apply"; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.head(controls.headUi.pan, controls.headUi.tilt) }
                        Button { text: "Field"; enabled: controls.view.ready; onClicked: controls.pose("head_field") }
                        Button { text: "Zero"; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.head(0, 0) }
                    }
                }
                ColumnLayout {
                    Layout.preferredWidth: 120
                    Label { text: "Turn speed: " + controls.headUi.step }
                    Slider { Layout.fillWidth: true; from: 10; to: 1000; stepSize: 10; value: controls.headUi.step; onMoved: controls.setHeadStep(Math.round(value)) }
                    GridLayout {
                        columns: 3
                        Item { width: 1; height: 1 }
                        Button { objectName: "headUpButton"; text: "Up"; Layout.preferredWidth: 48; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.nudgeHead("up") }
                        Item { width: 1; height: 1 }
                        Button { text: "Left"; Layout.preferredWidth: 48; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.nudgeHead("left") }
                        Button { objectName: "headDownButton"; text: "Down"; Layout.preferredWidth: 48; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.nudgeHead("down") }
                        Button { text: "Right"; Layout.preferredWidth: 48; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.nudgeHead("right") }
                    }
                    RowLayout {
                        Button { text: "Pan 0"; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.head(0, controls.headUi.tilt) }
                        Button { text: "Tilt 0"; enabled: controls.view.manual && !controls.view.pending; onClicked: controls.head(controls.headUi.pan, 0) }
                    }
                }
            }
        }
        Label { text: controls.view.jobOperation + " · " + controls.view.jobStatus + " " + controls.view.jobProgress; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: controls.view.jobReason || controls.view.error; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
