import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: scroll
    property var kddockwidgets_min_size: Qt.size(280, 200)
    contentWidth: availableWidth
    clip: true
    ColumnLayout {
        width: scroll.availableWidth
        spacing: 10
        Label { text: "Подключение к роботу"; font.bold: true }
        Label { text: "IPv4 / UDP. Поиска устройств в сети нет."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        TextField {
            id: host
            objectName: "robotHost"
            Layout.fillWidth: true
            Component.onCompleted: text = backend.view.host
            placeholderText: "172.30.0.1"
            enabled: backend.view.phase !== "connected" && backend.view.phase !== "connecting"
            selectByMouse: true
        }
        RowLayout {
            Label { text: "Порт" }
            SpinBox { id: port; objectName: "robotPort"; from: 1; to: 65535; Component.onCompleted: value = backend.view.port; editable: true; enabled: host.enabled }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Button {
                objectName: "connectButton"
                text: "Подключить"
                enabled: host.enabled
                onClicked: backend.connectRobot(host.text, port.value)
            }
            Button {
                objectName: "disconnectButton"
                text: "Отключить"
                enabled: !host.enabled
                onClicked: backend.disconnectRobot()
            }
        }
        Label { text: backend.view.connection; font.bold: true }
        Label {
            text: "После подключения: сессия, heartbeat, журнал и напряжение аккумулятора (1 Гц). Управление не захватывается, камера и IMU не запускаются, каталоги не запрашиваются."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
        Label {
            text: "Автономная игра не должна зависеть от наличия оператора. Ручное управление требует отдельного контроля потери связи."
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
}
