import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import com.kdab.dockwidgets 2.0 as KDDW

ApplicationWindow {
    id: window
    objectName: "operatorWindow"
    visible: true
    width: 1200
    height: 800
    minimumWidth: 800
    minimumHeight: 700
    title: "ROKI NG Operator"
    onClosing: Qt.quit()
    property var docks: [connectionDock, manualDock, videoDock, imageDock, statusDock, slotsDock, testsDock, parametersDock, dataDock, logsDock, diagnosticsDock]
    Loader {
        id: videoWindowLoader
        onStatusChanged: if (status === Loader.Error) video.media_error("Не удалось загрузить окно видео QML")
    }
    Connections {
        target: video
        function onShowWindow() {
            if (video.view.sink === "image") {
                if (videoWindowLoader.item) videoWindowLoader.item.hide()
                showDock(imageDock)
                video.attach(imagePanel.videoItem)
            } else {
                imageDock.forceClose()
                if (!videoWindowLoader.source.toString()) videoWindowLoader.source = "VideoDisplay.qml"
                else {
                    videoWindowLoader.item.show()
                    video.attach(videoWindowLoader.item.videoItem)
                }
            }
        }
        function onHideWindow() { if (video.view.sink === "image") imageDock.forceClose() }
    }

    function showDock(dock) { dock.open(); dock.setAsCurrentTab() }
    function saveLayout() { backend.layoutResult("Сохранение раскладки: " + saver.saveToFile(backend.layoutPath)) }
    function restoreLayout() { backend.layoutResult("Восстановление раскладки: " + saver.restoreFromFile(backend.layoutPath)) }

    header: ToolBar {
        RowLayout {
            width: parent.width
            spacing: 4
            RowLayout {
                id: layoutButtons
                ToolButton {
                    objectName: "panelsButton"
                    text: "Панели"
                    onClicked: panels.open()
                    Menu {
                        id: panels
                        MenuItem { text: "Подключение"; onTriggered: showDock(connectionDock) }
                        MenuItem { text: "Ручное управление"; onTriggered: showDock(manualDock) }
                        MenuItem { text: "Видео"; onTriggered: showDock(videoDock) }
                        MenuItem { text: "Изображение (QImage)"; onTriggered: showDock(imageDock) }
                        MenuItem { text: "Состояние"; onTriggered: showDock(statusDock) }
                        MenuItem { text: "Слоты"; onTriggered: showDock(slotsDock) }
                        MenuItem { text: "Тесты"; onTriggered: showDock(testsDock) }
                        MenuItem { text: "Параметры"; onTriggered: showDock(parametersDock) }
                        MenuItem { text: "Источники данных"; onTriggered: showDock(dataDock) }
                        MenuItem { text: "Журнал"; onTriggered: showDock(logsDock) }
                        MenuItem { text: "Диагностика"; onTriggered: showDock(diagnosticsDock) }
                    }
                }
                ToolButton { objectName: "saveLayoutButton"; text: window.width >= 1100 ? "Сохранить раскладку" : "Сохранить"; onClicked: saveLayout() }
                ToolButton { objectName: "restoreLayoutButton"; text: "Восстановить"; onClicked: restoreLayout() }
                ToolButton { text: "Управление"; visible: window.width >= 1100; onClicked: showDock(manualDock) }
            }
            Label {
                objectName: "connectionSummary"
                Layout.fillWidth: true
                Layout.minimumWidth: 40
                text: backend.view.connection + " | " + backend.view.robot + " | " + backend.view.mode
                elide: Text.ElideRight
                ToolTip.visible: summaryHover.hovered
                ToolTip.text: text
                HoverHandler { id: summaryHover }
            }
            Frame {
                id: robotControls
                objectName: "robotControlsGroup"
                Layout.rightMargin: 4
                padding: 2
                RowLayout {
                    Button {
                        objectName: "acquireButton"
                        text: "Получить управление"
                        font.bold: true
                        visible: !controls.view.owns
                        enabled: backend.view.connected && !controls.view.pending
                        onClicked: controls.acquire()
                    }
                    Button {
                        objectName: "releaseButton"
                        text: "Отдать управление"
                        font.bold: true
                        visible: controls.view.owns
                        enabled: controls.view.pending !== "control.release"
                        onClicked: controls.release()
                    }
                    Button { text: "Завершить цикл"; enabled: controls.view.owns; onClicked: controls.stop(false) }
                    Button { objectName: "hardStopButton"; text: "СБРОС ОЧЕРЕДИ"; font.bold: true; enabled: controls.view.owns; onClicked: controls.stop(true) }
                }
            }
        }
    }
    footer: ToolBar {
        Label {
            width: parent.width
            padding: 5
            text: backend.view.connected ? (controls.view.owns ? "Управление получено. " : "Наблюдение. ") + "Аккумулятор: нет данных. RTT: " + backend.view.rtt + " мс"
                                        : "Нет актуальной связи с роботом. Отображаемые снимки могут быть устаревшими."
            wrapMode: Text.Wrap
        }
    }
    KDDW.DockingArea {
        id: area
        uniqueName: "roki-operator-main"
        anchors.fill: parent
        KDDW.DockWidget {
            id: connectionDock
            objectName: "connectionDock"
            uniqueName: "connection"
            title: "Подключение"
            ConnectionPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: manualDock
            objectName: "manualDock"
            uniqueName: "manual"
            title: "Ручное управление"
            ManualPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: videoDock
            objectName: "videoDock"
            uniqueName: "video"
            title: "Видео"
            VideoPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: imageDock
            objectName: "imageDock"
            uniqueName: "mainVideo"
            title: "Изображение (QImage)"
            VideoImagePanel { id: imagePanel; anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: statusDock
            objectName: "statusDock"
            uniqueName: "status"
            title: "Состояние робота"
            StatusPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: slotsDock
            objectName: "slotsDock"
            uniqueName: "slots"
            title: "Слоты"
            CatalogPanel { kind: "slots"; anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: testsDock
            objectName: "testsDock"
            uniqueName: "tests"
            title: "Тесты"
            CatalogPanel { kind: "tests"; anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: parametersDock
            objectName: "parametersDock"
            uniqueName: "parameters"
            title: "Параметры"
            ParametersPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: dataDock
            objectName: "dataDock"
            uniqueName: "data"
            title: "Источники данных"
            DataSourcesPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: logsDock
            objectName: "logsDock"
            uniqueName: "logs"
            title: "Журнал"
            LogsPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: diagnosticsDock
            objectName: "diagnosticsDock"
            uniqueName: "diagnostics"
            title: "Диагностика"
            DiagnosticsPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        Component.onCompleted: {
            addDockWidget(connectionDock, KDDW.KDDockWidgets.Location_OnLeft, null, Qt.size(330, 450))
            connectionDock.addDockWidgetAsTab(manualDock)
            connectionDock.addDockWidgetAsTab(videoDock)
            connectionDock.setAsCurrentTab()
            addDockWidget(statusDock, KDDW.KDDockWidgets.Location_OnRight, connectionDock)
            statusDock.addDockWidgetAsTab(slotsDock)
            statusDock.addDockWidgetAsTab(testsDock)
            statusDock.addDockWidgetAsTab(parametersDock)
            statusDock.addDockWidgetAsTab(dataDock)
            statusDock.addDockWidgetAsTab(diagnosticsDock)
            statusDock.addDockWidgetAsTab(imageDock)
            imageDock.forceClose()
            statusDock.setAsCurrentTab()
            addDockWidget(logsDock, KDDW.KDDockWidgets.Location_OnBottom, null, Qt.size(1100, 260))
        }
    }
    KDDW.LayoutSaver { id: saver }
}
