import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var kddockwidgets_min_size: Qt.size(340, 180)
    property bool dirty: true
    property string renderedText: ""
    function applyFilter() {
        logText.deselect()
        logsModel.configure(level.currentText, search.text, source.text)
        schedule()
    }
    function scrollToEnd() {
        if (autoscroll.checked && !logText.selectedText.length)
            logs.contentItem.contentY = Math.max(0, logs.contentItem.contentHeight - logs.contentItem.height)
    }
    function follow() { if (autoscroll.checked) Qt.callLater(scrollToEnd) }
    function schedule() { dirty = true; if (!refresh.running) refresh.start() }
    function updateText() {
        if (!dirty || logText.selectedText.length) return
        dirty = false
        let next = logsModel.text()
        if (next === renderedText) return
        let previousY = logs.contentItem.contentY
        if (renderedText.length && next.startsWith(renderedText))
            logText.insert(logText.length, next.substring(renderedText.length))
        else
            logText.text = next
        renderedText = next
        Qt.callLater(function() {
            if (autoscroll.checked) scrollToEnd()
            else logs.contentItem.contentY = Math.max(0, Math.min(previousY, logs.contentItem.contentHeight - logs.contentItem.height))
        })
    }
    Timer { id: refresh; interval: 100; onTriggered: root.updateText() }
    Component.onCompleted: schedule()
    Flow {
        Layout.fillWidth: true
        spacing: 6
        ComboBox { id: level; objectName: "logLevel"; model: ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]; onActivated: applyFilter() }
        TextField { id: search; objectName: "logSearch"; width: 170; placeholderText: "Поиск в журнале"; onTextChanged: applyFilter() }
        TextField { id: source; width: 140; placeholderText: "Источник"; onTextChanged: applyFilter() }
        CheckBox { id: autoscroll; objectName: "autoscrollCheck"; text: "Автопрокрутка"; checked: true; onToggled: follow() }
        CheckBox { objectName: "pauseLogsCheck"; text: "Пауза просмотра"; checked: backend.view.logPaused; onToggled: backend.pauseLogs(checked) }
        Button { objectName: "clearLogsButton"; text: "Очистить"; onClicked: { logText.deselect(); backend.clearLogs() } }
        Button { objectName: "copyLogsButton"; text: "Копировать журнал"; onClicked: logsModel.copyAll() }
    }
    ScrollView {
        id: logs
        objectName: "logsList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 70
        clip: true
        contentWidth: availableWidth
        TextArea {
            id: logText
            objectName: "logText"
            width: logs.availableWidth
            padding: 3
            readOnly: true
            selectByMouse: true
            persistentSelection: true
            background: null
            textFormat: Text.PlainText
            wrapMode: Text.WrapAnywhere
            onSelectedTextChanged: { if (!selectedText.length && root.dirty) root.schedule() }
            TapHandler {
                acceptedButtons: Qt.RightButton
                onTapped: copyMenu.popup()
            }
            Menu {
                id: copyMenu
                MenuItem { text: "Копировать выделенное"; enabled: logText.selectedText.length > 0; onTriggered: logText.copy() }
                MenuItem { text: "Выделить всё"; onTriggered: logText.selectAll() }
            }
        }
    }
    Connections {
        target: logsModel
        function onRowsInserted() { root.schedule() }
        function onRowsRemoved() { root.schedule() }
        function onModelReset() { root.schedule() }
        function onLayoutChanged() { root.schedule() }
        function onDataChanged() { root.schedule() }
    }
    Label { text: "В памяти: " + backend.view.logCount + " / 2000. Время слева: получение на ПК."; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { visible: logText.selectedText.length > 0; text: "Выделение: показан снимок журнала. Новые записи продолжают приниматься."; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
