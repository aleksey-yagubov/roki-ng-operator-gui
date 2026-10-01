import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "manualScroll"
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
            Button {
                objectName: "manualModeButton"
                text: "Ручной режим"
                checkable: true
                checked: controls.view.manual
                enabled: controls.view.manual ? controls.view.pending !== "mode.set" : controls.view.canEnterManual
                onClicked: {
                    checked = Qt.binding(function() { return controls.view.manual })
                    if (controls.view.manual) controls.leaveManual()
                    else controls.enterManual()
                }
                ToolTip.visible: hovered
                ToolTip.text: "Выключение переводит робота в IDLE и останавливает очередь тела. Управление остаётся у оператора."
            }
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
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: "Присед:" }
                    ComboBox {
                        objectName: "crouchMode"
                        Layout.fillWidth: true
                        textRole: "text"
                        model: [
                            {text: "Не оставаться", mode: "off"},
                            {text: "Обычный присед", mode: "on"},
                            {text: "Центрированный присед", mode: "centered"}
                        ]
                        currentIndex: ["off", "on", "centered"].indexOf(controls.driveUi.crouch)
                        onActivated: function(index) { controls.driveSettings(controls.driveUi.speed, model[index].mode, controls.driveUi.headingHold) }
                    }
                }
                CheckBox {
                    objectName: "headingHoldCheck"
                    text: "Удерживать курс по IMU тела"
                    checked: controls.driveUi.headingHold
                    onToggled: controls.driveSettings(controls.driveUi.speed, controls.driveUi.crouch, checked)
                    ToolTip.visible: hovered
                    ToolTip.text: "Удержание направления ходьбы, не стабилизация равновесия и не IMU головы."
                }
                RowLayout {
                    Button { objectName: "crouchButton"; text: "Crouch"; enabled: controls.view.ready; onClicked: controls.pose("crouch") }
                    Button { text: "Stand"; enabled: controls.view.ready; onClicked: controls.pose("stand") }
                }
                Label { text: "Speed: " + Math.round(speed.value * 100) + "%" }
                Slider {
                    id: speed
                    Layout.fillWidth: true
                    from: 0.1
                    to: 1.0
                    value: controls.driveUi.speed
                    onMoved: controls.driveSettings(value, controls.driveUi.crouch, controls.driveUi.headingHold)
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
                Flow {
                    Layout.fillWidth: true
                    spacing: 4
                    Button { objectName: "getUpButton"; text: "Встать после падения"; enabled: controls.view.ready; onClicked: controls.getUp() }
                    Button { objectName: "splitsSmallButton"; text: "Splits"; enabled: controls.view.ready; onClicked: controls.splits("small") }
                    Button { objectName: "splitsBigButton"; text: "Шпагат"; enabled: controls.view.ready; onClicked: controls.splits("big") }
                }
                Label { text: "После Splits / шпагата выход через Crouch, Stand или Base."; Layout.fillWidth: true; wrapMode: Text.Wrap }
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
                    Label { text: controls.headUi.known ? "Цель: " + controls.headUi.targetPan + " / " + controls.headUi.targetTilt + " ticks" : "Цель головы неизвестна" }
                    Label { text: controls.headUi.dirty ? "Черновик: нажмите Apply" : "Заданные ticks, не измеренная позиция" }
                    Label { text: "Pan: " + controls.headUi.pan }
                    Slider { objectName: "headPan"; Layout.fillWidth: true; from: -2666; to: 2666; stepSize: 1; value: controls.headUi.pan; onMoved: controls.setHeadUi(Math.round(value), controls.headUi.tilt) }
                    Label { text: "Tilt: " + controls.headUi.tilt }
                    Slider { objectName: "headTilt"; Layout.fillWidth: true; from: -2600; to: 950; stepSize: 1; value: controls.headUi.tilt; onMoved: controls.setHeadUi(controls.headUi.pan, Math.round(value)) }
                    RowLayout {
                        Button { objectName: "headApply"; text: "Apply"; enabled: controls.headUi.canSend; onClicked: controls.head(controls.headUi.pan, controls.headUi.tilt) }
                        Button { text: "Field"; enabled: controls.view.ready; onClicked: controls.pose("head_field") }
                        Button { text: "Zero"; enabled: controls.headUi.canSend; onClicked: controls.head(0, 0) }
                    }
                }
                ColumnLayout {
                    Layout.preferredWidth: 120
                    Label { text: "Turn steps: " + controls.headUi.step }
                    Slider { Layout.fillWidth: true; from: 10; to: 1000; stepSize: 10; value: controls.headUi.step; onMoved: controls.setHeadStep(Math.round(value)) }
                    GridLayout {
                        columns: 3
                        Item { width: 1; height: 1 }
                        Button { objectName: "headUpButton"; text: "Up"; Layout.preferredWidth: 48; enabled: controls.headUi.canNudge; onClicked: controls.nudgeHead("up") }
                        Item { width: 1; height: 1 }
                        Button { text: "Left"; Layout.preferredWidth: 48; enabled: controls.headUi.canNudge; onClicked: controls.nudgeHead("left") }
                        Button { objectName: "headDownButton"; text: "Down"; Layout.preferredWidth: 48; enabled: controls.headUi.canNudge; onClicked: controls.nudgeHead("down") }
                        Button { text: "Right"; Layout.preferredWidth: 48; enabled: controls.headUi.canNudge; onClicked: controls.nudgeHead("right") }
                    }
                    RowLayout {
                        Button { objectName: "headPanZero"; text: "Pan 0"; enabled: controls.headUi.canSend; onClicked: controls.resetHeadAxis("pan") }
                        Button { objectName: "headTiltZero"; text: "Tilt 0"; enabled: controls.headUi.canSend; onClicked: controls.resetHeadAxis("tilt") }
                    }
                }
            }
        }
        Label { text: controls.view.jobOperation + " · " + controls.view.jobStatus + " " + controls.view.jobProgress; Layout.fillWidth: true; wrapMode: Text.Wrap }
        SelectableLabel { text: controls.view.jobReason || controls.view.error; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
    }
}
