import QtQuick
import QtQuick.Controls

Label {
    objectName: "videoStats"
    text: video.view.phase + " | " + video.view.size + " | FPS: "
          + (video.view.fps === null || video.view.fps === undefined ? "-" : Number(video.view.fps).toFixed(1))
          + " | " + video.view.frames + " кадров"
    wrapMode: Text.Wrap
    ToolTip.text: "FPS по приросту GStreamer sink stats.rendered за 0,5 с. Это приём кадров sink, не частота перерисовки Qt."
    ToolTip.visible: hover.hovered
    HoverHandler { id: hover }
}
