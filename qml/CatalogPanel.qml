import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property var kddockwidgets_min_size: Qt.size(320, 260)
    Connections {
        target: slotsModel
        function onModelReset() { selectedSlot.text = ""; catalog.currentIndex = -1 }
    }
    TabBar {
        id: tabs
        Layout.fillWidth: true
        TabButton { text: "Слоты" }
        TabButton { objectName: "testsTab"; text: "Тесты" }
    }
    Label { objectName: "catalogBlockedReason"; text: controls.view.blockedReason; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Button { objectName: "catalogManualButton"; text: "Включить ручной режим"; visible: controls.view.owns && !controls.view.manual; enabled: controls.view.canEnterManual; onClicked: controls.enterManual() }
    Button {
        objectName: "catalogButton"
        text: tabs.currentIndex === 0 ? "Запросить список слотов" : "Запросить тесты и формы"
        enabled: backend.view.connected && !backend.view.catalogsBusy
        onClicked: backend.requestCatalog(tabs.currentIndex === 0 ? "slots" : "tests")
    }
    ListView {
        id: catalog
        objectName: "catalogList"
        visible: tabs.currentIndex === 0
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 80
        clip: true
        model: slotsModel
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var entry
            required property int index
            width: ListView.view.width
            text: entry.name
            highlighted: ListView.isCurrentItem
            onClicked: { catalog.currentIndex = index; selectedSlot.text = entry.name }
        }
    }
    RowLayout {
        visible: tabs.currentIndex === 0
        Layout.fillWidth: true
        Label { id: selectedSlot; Layout.fillWidth: true; elide: Text.ElideRight; text: "" }
        Button { objectName: "startSlotButton"; text: "Запустить слот"; enabled: controls.view.ready && selectedSlot.text !== ""; onClicked: controls.slot(selectedSlot.text, 1.0) }
    }
    Label { visible: tabs.currentIndex === 0 && selectedSlot.text === ""; text: "Выберите слот в списке."; Layout.fillWidth: true; wrapMode: Text.Wrap }
    ScrollView {
        id: testScroll
        visible: tabs.currentIndex === 1
        Layout.fillWidth: true
        Layout.fillHeight: true
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            width: testScroll.availableWidth
            Repeater {
                objectName: "testCards"
                model: testsModel
                delegate: TestCard { required property var entry; schema: entry.schema || ({}); testName: entry.name; raw: entry.raw || ""; Layout.fillWidth: true }
            }
        }
    }
    Flow {
        Layout.fillWidth: true
        spacing: 4
        Button { text: "Завершить цикл"; enabled: controls.view.owns; onClicked: controls.stop(false) }
        Button { text: "Сброс очереди"; enabled: controls.view.owns; onClicked: controls.stop(true) }
    }
    Label { text: controls.view.jobOperation + " · " + controls.view.jobStatus + " " + controls.view.jobProgress; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: controls.view.error || controls.view.jobReason; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
