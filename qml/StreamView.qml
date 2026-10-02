import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    required property string viewId
    property var kddockwidgets_min_size: Qt.size(300, 230)
    property string selected: { videoViews.entries; return videoViews.selected(viewId) }
    property var reception: { streams.view; return streams.reception(selected) }
    property string frameUrl: ""
    function updateFrame() { frameUrl = streams.imageUrl(selected) }
    onSelectedChanged: updateFrame()
    onReceptionChanged: updateFrame()
    Component.onCompleted: updateFrame()
    Connections { target: streams; function onFramesChanged() { root.updateFrame() } }
    RowLayout {
        Layout.fillWidth: true
        ComboBox {
            objectName: "viewSelector-" + root.viewId
            Layout.fillWidth: true
            model: streams.receivers
            textRole: "label"
            currentIndex: model.findIndex(s => s.id === root.selected)
            enabled: count > 0
            displayText: currentIndex < 0 ? (root.selected ? "Поток недоступен: " + root.selected : count ? "Выберите принимаемый стрим" : "Нет принимаемых стримов") : currentText
            onActivated: videoViews.select(root.viewId, model[currentIndex].id)
        }
        Button { text: "Удалить просмотр"; onClicked: videoViews.remove(root.viewId) }
    }
    Label {
        text: root.reception.active ? (root.reception.size || "Ожидание кадра") + " · " + (root.reception.fps === undefined || root.reception.fps === null ? "—" : root.reception.fps.toFixed(1)) + " FPS"
             : root.reception.error || "В панели «Стримы» выберите видеовыход и нажмите «Смотреть», затем выберите его здесь."
        Layout.fillWidth: true; wrapMode: Text.Wrap
    }
    Label { visible: root.reception.stalled || false; text: "Нет новых кадров. Проверьте передачу и UDP."; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Image {
        objectName: "viewImage-" + root.viewId
        Layout.fillWidth: true; Layout.fillHeight: true
        fillMode: Image.PreserveAspectFit
        source: root.frameUrl
        cache: false
    }
}
