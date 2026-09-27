import QtQuick
import org.freedesktop.gstreamer.Qt6GLVideoItem 1.0

Item {
    property alias videoItem: video
    GstGLQt6VideoItem {
        id: video
        objectName: "videoItem"
        anchors.fill: parent
    }
    Rectangle {
        x: parent.width * 0.3
        y: parent.height * 0.3
        width: parent.width * 0.4
        height: parent.height * 0.4
        color: "transparent"
        border.color: "orange"
        border.width: 2
        Text { text: "Qt Quick OSD"; color: "white" }
    }
}
