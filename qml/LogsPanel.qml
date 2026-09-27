import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property var kddockwidgets_min_size: Qt.size(340, 180)
    function applyFilter() { logsModel.configure(level.currentText, search.text, source.text) }
    function scrollToEnd() { logs.positionViewAtEnd() }
    function follow() { if (autoscroll.checked) Qt.callLater(scrollToEnd) }
    Flow {
        Layout.fillWidth: true
        spacing: 6
        ComboBox { id: level; objectName: "logLevel"; model: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]; onActivated: applyFilter() }
        TextField { id: search; objectName: "logSearch"; width: 170; placeholderText: "Поиск в журнале"; onTextChanged: applyFilter() }
        TextField { id: source; width: 140; placeholderText: "Источник"; onTextChanged: applyFilter() }
        CheckBox { id: autoscroll; objectName: "autoscrollCheck"; text: "Автопрокрутка"; checked: true; onToggled: follow() }
        CheckBox { objectName: "pauseLogsCheck"; text: "Пауза просмотра"; checked: backend.view.logPaused; onToggled: backend.pauseLogs(checked) }
        Button { objectName: "clearLogsButton"; text: "Очистить"; onClicked: backend.clearLogs() }
    }
    ListView {
        id: logs
        objectName: "logsList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 70
        clip: true
        model: logsModel
        ScrollBar.vertical: ScrollBar {}
        onCountChanged: follow()
        delegate: Label {
            required property var entry
            width: ListView.view.width
            padding: 3
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            text: entry.time + " [" + entry.level + "] " + entry.source + ": " + entry.message
        }
    }
    Connections {
        target: logsModel
        function onRowsInserted() { follow() }
        function onModelReset() { follow() }
    }
    Label { text: "В памяти: " + backend.view.logCount + " / 2000. Время слева: получение на ПК."; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
