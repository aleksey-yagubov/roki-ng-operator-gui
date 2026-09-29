import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import com.kdab.dockwidgets 2.0 as KDDW

ApplicationWindow {
    id: window
    function applyMacPalette() {
        if (Qt.platform.os === "osx") {
            palette.window = "#f0f1f3"
            palette.windowText = "#202124"
            palette.base = "#ffffff"
            palette.alternateBase = "#f4f5f7"
            palette.text = "#202124"
            palette.button = "#e8eaed"
            palette.buttonText = "#202124"
            palette.highlight = "#2463b4"
            palette.highlightedText = "#ffffff"
            palette.placeholderText = "#626974"
            palette.disabled.windowText = "#787e87"
            palette.disabled.text = "#787e87"
            palette.disabled.buttonText = "#787e87"
        }
    }
    objectName: "operatorWindow"
    visible: true
    width: 1200
    height: 800
    // KDDW keeps the combined dock minima; smaller windows clip the right column.
    minimumWidth: 1200
    minimumHeight: 800
    title: "ROKI NG Operator"
    onClosing: Qt.quit()
    property var docks: [connectionDock, manualDock, videoDock, imageDock, statusDock, catalogDock, parametersDock, fieldDock, localisationDock, visionDock, dataDock, logsDock, diagnosticsDock]
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
        Flow {
            width: parent.width
            padding: 4
            spacing: 6
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
                    MenuItem { text: "Слоты и тесты"; onTriggered: showDock(catalogDock) }
                    MenuItem { text: "Параметры"; onTriggered: showDock(parametersDock) }
                    MenuItem { text: "Локализация"; onTriggered: showDock(localisationDock) }
                    MenuItem { text: "Поле и ворота"; onTriggered: showDock(fieldDock) }
                    MenuItem { text: "Цвета и камера"; onTriggered: showDock(visionDock) }
                    MenuItem { text: "Источники данных"; onTriggered: showDock(dataDock) }
                    MenuItem { text: "Журнал"; onTriggered: showDock(logsDock) }
                    MenuItem { text: "Диагностика"; onTriggered: showDock(diagnosticsDock) }
                }
            }
            ToolButton { objectName: "saveLayoutButton"; text: "Сохранить раскладку"; onClicked: saveLayout() }
            ToolButton { objectName: "restoreLayoutButton"; text: "Восстановить"; onClicked: restoreLayout() }
            ToolButton {
                objectName: "acquireButton"
                text: "Получить управление"
                visible: !controls.view.owns
                enabled: backend.view.connected && !controls.view.pending
                onClicked: controls.acquire()
            }
            ToolButton {
                objectName: "releaseButton"
                text: "Отдать управление"
                visible: controls.view.owns
                enabled: controls.view.pending !== "control.release"
                onClicked: controls.release()
            }
            ToolButton { text: "Управление"; onClicked: showDock(manualDock) }
            ToolButton { text: "Завершить цикл"; enabled: controls.view.owns; onClicked: controls.stop(false) }
            ToolButton { objectName: "hardStopButton"; text: "СБРОС ОЧЕРЕДИ"; font.bold: true; enabled: controls.view.owns; onClicked: controls.stop(true) }
            Label {
                padding: 8
                text: backend.view.connection + " | " + backend.view.robot + " | " + backend.view.mode
                elide: Text.ElideRight
                width: Math.min(implicitWidth, window.width - 16)
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
            id: catalogDock
            objectName: "catalogDock"
            uniqueName: "catalog"
            title: "Слоты и тесты"
            CatalogPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: parametersDock
            objectName: "parametersDock"
            uniqueName: "parameters"
            title: "Параметры"
            ParametersPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: fieldDock
            objectName: "fieldDock"
            uniqueName: "field"
            title: "Поле и ворота"
            FieldPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: localisationDock
            objectName: "localisationDock"
            uniqueName: "localisation"
            title: "Локализация"
            LocalisationPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id:visionDock
            objectName:"visionDock"
            uniqueName:"visionTuning"
            title:"Цвета и камера"
            VisionPanel {anchors.fill:parent;anchors.margins:8}
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
        window.applyMacPalette()
            addDockWidget(connectionDock, KDDW.KDDockWidgets.Location_OnLeft, null, Qt.size(330, 450))
            connectionDock.addDockWidgetAsTab(manualDock)
            connectionDock.addDockWidgetAsTab(videoDock)
            connectionDock.setAsCurrentTab()
            addDockWidget(statusDock, KDDW.KDDockWidgets.Location_OnRight, connectionDock)
            statusDock.addDockWidgetAsTab(catalogDock)
            statusDock.addDockWidgetAsTab(parametersDock)
            statusDock.addDockWidgetAsTab(fieldDock)
            statusDock.addDockWidgetAsTab(localisationDock)
            statusDock.addDockWidgetAsTab(visionDock)
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
