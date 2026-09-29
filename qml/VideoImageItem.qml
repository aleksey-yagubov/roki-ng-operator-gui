import QtQuick
Image {
    objectName: "mainVideoItem"
    source: video.hasImage ? "image://mainVideo/" + video.imageSerial : ""
    cache: false
    asynchronous: false
    fillMode: Image.PreserveAspectFit
}
