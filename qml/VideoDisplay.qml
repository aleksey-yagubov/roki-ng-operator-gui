import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// One persistent QQuickWindow: a live GL sink is never reparented by docking.
Window {
    id: display
    property alias videoItem: surface.item
    objectName: "videoWindow"
    visible: true
    width: 840
    height: 720
    title: "ROKI · основной видеопоток"
    onClosing: function(close) { close.accepted = false; video.closeWindow() }
    Connections { target: video; function onHideWindow() { display.hide() } }
    ColumnLayout {
        anchors.fill: parent
        RowLayout {
            Layout.fillWidth: true
            Button { text: "Остановить видео"; enabled: video.view.canStop; onClicked: video.stop() }
            VideoStats { Layout.fillWidth: true }
        }
        Label { text: video.view.error || (video.view.stalled ? "Нет новых кадров" : ""); visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Loader {
            id: surface
            Layout.fillWidth: true
            Layout.fillHeight: true
            source: "VideoGLItem.qml"
            onLoaded: video.attach(item)
        }
    }
}
