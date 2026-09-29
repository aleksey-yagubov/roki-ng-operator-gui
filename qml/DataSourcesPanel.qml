import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property var kddockwidgets_min_size: Qt.size(320, 250)
    Button { objectName: "dataListButton"; text: "Запросить источники"; enabled: dataSources.view.connected && !dataSources.view.listing; onClicked: dataSources.requestList() }
    ComboBox {
        id: topics
        objectName: "dataTopic"
        Layout.fillWidth: true
        model: dataSources.catalog
        textRole: "name"
        onActivated: dataSources.select(currentText)
    }
    Connections {
        target: dataSources
        function onTopicsChanged() { topics.currentIndex = dataSources.catalog.findIndex(x => x.name === dataSources.view.selected) }
        function onChanged() {
            let index = dataSources.catalog.findIndex(x => x.name === dataSources.view.selected)
            if (topics.currentIndex !== index) topics.currentIndex = index
        }
    }
    Flow {
        Layout.minimumWidth: 0
        Layout.preferredWidth: 1
        Layout.fillWidth: true
        spacing: 4
        Button { objectName: "dataSnapshotButton"; text: "Снимок"; enabled: dataSources.view.connected && !!dataSources.view.selected && !dataSources.view.busy; onClicked: dataSources.snapshot() }
        SpinBox { id: rate; from: 1; to: Math.max(1, Math.floor(dataSources.view.maxRate)); value: 2; editable: true; ToolTip.text: "Частота обновлений, Гц"; ToolTip.visible: hovered }
        Button { objectName: "dataSubscribeButton"; text: dataSources.view.watching ? "Изменить частоту" : "Подписаться"; enabled: dataSources.view.connected && !!dataSources.view.selected && !dataSources.view.busy; onClicked: dataSources.subscribe(rate.value) }
        Button { objectName: "dataUnsubscribeButton"; text: "Отписаться"; enabled: dataSources.view.connected && dataSources.view.watching && !dataSources.view.busy; onClicked: dataSources.unsubscribe() }
    }
    Label {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        text: !dataSources.view.connected ? "Нет связи. Показан последний сохранённый снимок."
            : dataSources.view.active ? "Подписка: " + dataSources.view.rate + " Гц"
            : dataSources.view.watching ? "Подписка запрошена, подтверждение не получено."
            : "Автообновление выключено. Выбор источника ничего не запускает."
    }
    Label {
        Layout.fillWidth: true
        wrapMode: Text.Wrap
        text: dataSources.view.received ? "Получено " + dataSources.view.localAge + " с назад · возраст на роботе: "
            + dataSources.view.sourceAge + " мс · источник " + (dataSources.view.valid ? "доступен" : "недоступен")
            + " · пропущено: " + dataSources.view.gaps : "Данные ещё не запрошены."
    }
    ListView {
        objectName: "dataFields"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 60
        clip: true
        model: dataFieldsModel
        ScrollBar.vertical: ScrollBar {}
        delegate: RowLayout {
            required property var entry
            width: ListView.view.width
            Label { text: entry.name; Layout.preferredWidth: parent.width * 0.46; wrapMode: Text.WrapAnywhere }
            Label { text: entry.value; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere; textFormat: Text.PlainText }
        }
    }
    Label { text: dataSources.view.error; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: "Запрошено подписок: " + dataSources.view.subscriptions; Layout.fillWidth: true }
    ScrollView {
        id: rawScroll
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(raw.implicitHeight, 150)
        contentWidth: availableWidth
        clip: true
        RawDetails { id: raw; objectName: "dataRawDetails"; width: rawScroll.availableWidth; text: dataSources.view.raw }
    }
}
