import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import com.kdab.dockwidgets 2.0 as KDDW

ApplicationWindow {
    id: window
    objectName: "probeWindow"
    visible: true
    width: 1100
    height: 720
    title: "ROKI operator: docking probe (no robot connection)"
    property alias videoDock: videoDock
    property alias controlsDock: controlsDock
    property alias logsDock: logsDock

    header: ToolBar {
        Flow {
            width: parent.width
            Button {
                objectName: "floatButton"
                text: videoDock.isFloating ? "Dock video" : "Float video"
                onClicked: videoDock.isFloating = !videoDock.isFloating
            }
            Button {
                objectName: "hideButton"
                text: videoDock.isOpen ? "Hide video" : "Show video"
                onClicked: videoDock.isOpen ? videoDock.close() : videoDock.open()
            }
            Button {
                objectName: "tabButton"
                text: "Tab video with controls"
                onClicked: {
                    controlsDock.addDockWidgetAsTab(videoDock)
                    videoDock.setAsCurrentTab()
                }
            }
            Button {
                objectName: "saveButton"
                text: "Save layout"
                onClicked: probe.note("save layout: " + saver.saveToFile(probe.layoutPath))
            }
            Button {
                objectName: "restoreButton"
                text: "Restore layout"
                onClicked: probe.note("restore layout: " + saver.restoreFromFile(probe.layoutPath))
            }
        }
    }

    KDDW.DockingArea {
        id: area
        uniqueName: "operator-probe"
        anchors.fill: parent

        KDDW.DockWidget {
            id: videoDock
            objectName: "videoDock"
            uniqueName: "video"
            title: "Video (test source)"
            Item {
                property var kddockwidgets_min_size: Qt.size(300, 240)
                anchors.fill: parent
                Loader {
                    id: videoLoader
                    anchors.fill: parent
                    source: probe.videoEnabled ? "VideoSurface.qml" : ""
                    onLoaded: probe.attachVideo(item.videoItem)
                }
                Label {
                    visible: !probe.videoEnabled
                    anchors.centerIn: parent
                    text: "Docking-only test"
                }
            }
        }

        KDDW.DockWidget {
            id: controlsDock
            objectName: "controlsDock"
            uniqueName: "controls"
            title: "Python / QML controls"
            Pane {
                property var kddockwidgets_min_size: Qt.size(260, 200)
                anchors.fill: parent
                ColumnLayout {
                    anchors.fill: parent
                    Label { text: "This prototype cannot command a robot."; wrapMode: Text.Wrap; Layout.fillWidth: true }
                    Button {
                        objectName: "pythonButton"
                        text: "Call Python"
                        onClicked: probe.increment()
                    }
                    Label { text: "Python callbacks: " + probe.clickCount }
                    Slider { Layout.fillWidth: true; from: 0; to: 100; value: 50 }
                    Item { Layout.fillHeight: true }
                }
            }
        }

        KDDW.DockWidget {
            id: logsDock
            uniqueName: "logs"
            title: "Probe log"
            ScrollView {
                property var kddockwidgets_min_size: Qt.size(300, 140)
                anchors.fill: parent
                TextArea { text: probe.logText; readOnly: true; wrapMode: TextEdit.Wrap }
            }
        }

        Component.onCompleted: {
            addDockWidget(videoDock, KDDW.KDDockWidgets.Location_OnLeft)
            addDockWidget(controlsDock, KDDW.KDDockWidgets.Location_OnRight, videoDock)
            addDockWidget(logsDock, KDDW.KDDockWidgets.Location_OnBottom, null, Qt.size(1000, 180))
        }
    }

    KDDW.LayoutSaver { id: saver }
}
