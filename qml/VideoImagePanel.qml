import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    property var kddockwidgets_min_size: Qt.size(300, 220)
    property alias videoItem: image
    Button { text: "Остановить видео"; enabled: video.view.canStop; onClicked: video.stop() }
    VideoStats { Layout.fillWidth: true }
    Label { text: video.view.error || (video.view.stalled ? "Нет новых кадров" : ""); visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
    VideoImageItem { id: image; Layout.fillWidth: true; Layout.fillHeight: true }
}
