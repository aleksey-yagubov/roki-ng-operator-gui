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
    property var docks: [connectionDock, manualDock, videoDock, cameraDock, statusDock, slotsDock, testsDock, parametersDock, gameDock, fieldDock, localisationDock, visionDock, dataDock, logsDock, diagnosticsDock]
    property var viewDocks: ({})
    Component {
        id: viewerFactory
        KDDW.DockWidget {
            id: viewerDock
            required property string viewId
            objectName: "viewDock-" + viewId
            uniqueName: "viewer-" + viewId
            title: "Просмотр " + viewId.slice(0, 8)
            StreamView { viewId: viewerDock.viewId; anchors.fill: parent; anchors.margins: 8 }
        }
    }
    function addViewer(ident) {
        if (viewDocks[ident]) return
        let dock = viewerFactory.createObject(area, {viewId:ident})
        if (!dock) return
        viewDocks[ident] = dock
        docks = docks.concat([dock])
        if (statusDock.isOpen)
            statusDock.addDockWidgetAsTab(dock)
        else
            area.addDockWidget(dock, KDDW.KDDockWidgets.Location_OnRight, null, Qt.size(420, 330))
        dock.open()
        dock.setAsCurrentTab()
    }
    function removeViewer(ident) {
        let dock = viewDocks[ident]
        if (!dock) return
        dock.forceClose()
        docks = docks.filter(d => d !== dock)
        delete viewDocks[ident]
        dock.destroy()
    }
    Connections {
        target: videoViews
        function onAdded(ident) { window.addViewer(ident) }
        function onRequested(ident) { window.showDock(window.viewDocks[ident]) }
        function onRemoved(ident) { window.removeViewer(ident) }
    }

    function showDock(dock) { dock.open(); dock.setAsCurrentTab() }
    function saveLayout() { backend.layoutResult("Сохранение раскладки: " + (videoViews.save() && saver.saveToFile(backend.layoutPath))) }
    function restoreLayout() {
        videoViews.restore()
        backend.layoutResult("Восстановление раскладки: " + saver.restoreFromFile(backend.layoutPath))
    }

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
                        MenuItem { text: "Камера"; onTriggered: showDock(cameraDock) }
                        MenuItem { text: "Стримы"; onTriggered: showDock(videoDock) }
                        MenuItem { objectName: "newVideoView"; text: "Открыть новый просмотр видео"; onTriggered: videoViews.add("") }
                        Menu {
                            id: viewsMenu
                            objectName: "existingVideoViewsMenu"
                            title: "Созданные просмотры"
                            visible: videoViews.entries.length > 0
                            Instantiator {
                                model: videoViews.entries
                                delegate: MenuItem {
                                    required property var modelData
                                    text: "Просмотр " + modelData.id.slice(0, 8)
                                    onTriggered: window.showDock(window.viewDocks[modelData.id])
                                }
                                onObjectAdded: (index, object) => viewsMenu.insertItem(index, object)
                                onObjectRemoved: (index, object) => viewsMenu.removeItem(object)
                            }
                        }
                        MenuItem { text: "Состояние"; onTriggered: showDock(statusDock) }
                        MenuItem { text: "Слоты"; onTriggered: showDock(slotsDock) }
                        MenuItem { text: "Тесты"; onTriggered: showDock(testsDock) }
                        MenuItem { text: "Параметры"; onTriggered: showDock(parametersDock) }
                        MenuItem { text: "Вратарь FIRA"; onTriggered: showDock(gameDock) }
                        MenuItem { text: "Локализация"; onTriggered: showDock(localisationDock) }
                        MenuItem { text: "Поле и ворота"; onTriggered: showDock(fieldDock) }
                        MenuItem { text: "Цвета и детекция"; onTriggered: showDock(visionDock) }
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
            objectName: "batteryStatus"
            width: parent.width
            padding: 5
            text: backend.view.connected ? (controls.view.owns ? "Управление получено. " : "Наблюдение. ") + "Аккумулятор: " + dataSources.power.text + ". RTT: " + backend.view.rtt + " мс"
                                        : "Нет актуальной связи с роботом. Отображаемые снимки могут быть устаревшими."
            HoverHandler { id: powerHover }
            ToolTip.visible: powerHover.hovered
            ToolTip.text: dataSources.power.details
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
            title: "Стримы"
            VideoPanel { anchors.fill: parent; anchors.margins: 8 }
        }
        KDDW.DockWidget {
            id: cameraDock
            objectName: "cameraDock"
            uniqueName: "runtimeCamera"
            title: "Камера"
            CameraPanel { anchors.fill: parent; anchors.margins: 8 }
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
            id: gameDock
            objectName: "gameDock"
            uniqueName: "game"
            title: "Вратарь FIRA"
            GamePanel { anchors.fill: parent; anchors.margins: 8; onRequestStreams: window.showDock(videoDock) }
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
            title:"Цвета и детекция"
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
            connectionDock.addDockWidgetAsTab(cameraDock)
            connectionDock.setAsCurrentTab()
            addDockWidget(statusDock, KDDW.KDDockWidgets.Location_OnRight, connectionDock)
            statusDock.addDockWidgetAsTab(slotsDock)
            statusDock.addDockWidgetAsTab(testsDock)
            statusDock.addDockWidgetAsTab(parametersDock)
            statusDock.addDockWidgetAsTab(gameDock)
            statusDock.addDockWidgetAsTab(fieldDock)
            statusDock.addDockWidgetAsTab(localisationDock)
            statusDock.addDockWidgetAsTab(visionDock)
            statusDock.addDockWidgetAsTab(dataDock)
            statusDock.addDockWidgetAsTab(diagnosticsDock)
            statusDock.setAsCurrentTab()
            addDockWidget(logsDock, KDDW.KDDockWidgets.Location_OnBottom, null, Qt.size(1100, 260))
            for (let entry of videoViews.entries) window.addViewer(entry.id)
        }
    }
    KDDW.LayoutSaver { id: saver }
}
