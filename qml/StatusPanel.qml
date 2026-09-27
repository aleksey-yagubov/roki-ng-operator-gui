import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: scroll
    property var kddockwidgets_min_size: Qt.size(300, 220)
    contentWidth: availableWidth
    clip: true
    ColumnLayout {
        width: scroll.availableWidth
        spacing: 8
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Button { objectName: "statusButton"; text: "Запросить статус"; enabled: backend.view.connected; onClicked: backend.requestStatus() }
            Button { objectName: "capabilitiesButton"; text: "Возможности"; enabled: backend.view.connected; onClicked: backend.requestCapabilities() }
        }
        Label { text: "Робот: " + backend.view.robot; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Режим: " + backend.view.mode + (backend.view.connected ? "" : " (неактуально)"); Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Владелец управления: " + backend.view.owner; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Аккумулятор: нет измеренных данных"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Возраст снимка: " + backend.view.statusAge + " с" }
        Repeater {
            model: workersModel
            delegate: Label {
                required property var entry
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: entry.name + ": " + entry.state + (entry.alive ? "" : " / процесс недоступен")
            }
        }
        RawDetails {
            objectName: "statusDetails"
            Layout.fillWidth: true
            text: backend.view.statusText
        }
        Label { text: "Заявленные возможности"; font.bold: true }
        Label { text: "Режимы: " + (backend.view.capabilities.modes || []).join(", "); Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Движения: " + (backend.view.capabilities.body || []).join(", "); Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Источники данных: " + (backend.view.capabilities.data_topics || []).join(", "); Layout.fillWidth: true; wrapMode: Text.Wrap }
        RawDetails { text: backend.view.capabilitiesText }
    }
}
