import QtQuick
Image {
    objectName: "mainVideoItem"
    source: video.imageSerial ? "image://mainVideo/" + video.imageSerial : ""
    cache: false
    asynchronous: false
    fillMode: Image.PreserveAspectFit
}
