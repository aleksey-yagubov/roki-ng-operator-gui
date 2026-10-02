import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "gamePanel"
    signal requestStreams()
    property string selectedStream: ""
    property string frameUrl: ""
    property var reception: { streams.view; return streams.reception(selectedStream) }
    function updateFrame() { frameUrl = streams.imageUrl(selectedStream) }
    onSelectedStreamChanged: updateFrame()
    onReceptionChanged: updateFrame()
    Connections {
        target: streams
        function onFramesChanged() { root.updateFrame() }
        function onReceiversChanged() {
            if (!streams.receivers.some(s => s.id === root.selectedStream)) root.selectedStream = ""
        }
    }
    clip: true
    contentWidth: availableWidth
    property var kddockwidgets_min_size: Qt.size(420, 280)
    ColumnLayout {
        width: root.availableWidth
        SelectableLabel { text: "FIRA · Пенальти · Вратарь"; font.bold: true }
        SelectableLabel { text: "Наблюдение вычисляет решения без движений. Физический запуск разрешается роботом только после проверки геометрии (game.geometry_verified)."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            SelectableLabel { text: "Задержка, с" }
            SpinBox { id: delay; objectName: "gameDelay"; from: 0; to: 30; value: 0 }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "gameObserve"; text: game.view.fresh && game.view.running && game.view.observeOnly ? "Наблюдение уже запущено" : "Запустить наблюдение"; enabled: game.view.canObserve; onClicked: game.start(true, delay.value) }
            Button { objectName: "gamePhysicalStart"; text: "Запустить с физическими движениями"; enabled: game.view.canStart; onClicked: game.start(false, delay.value) }
            Button { objectName: "gameStop"; text: "Остановить игру"; enabled: game.view.canStop; onClicked: game.stop() }
            Button { objectName: "gameRefresh"; text: "Запросить статус"; enabled: game.view.canRefresh; onClicked: game.refresh() }
            Button { objectName: "gameSubscribe"; text: game.view.watching ? "Отключить данные игры" : "Получать данные игры"; enabled: game.view.canRefresh && !game.view.subscriptionPending; onClicked: game.watch(!game.view.watching) }
        }
        SelectableLabel { text: game.view.canObserve && !game.view.canStart ? "Наблюдение само включит MANUAL. Команды движения не отправляются." : game.view.blockedReason; visible: !game.view.canStart; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameError"; text: game.view.error; color: "#b03030"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameState"; text: (game.view.fresh ? "" : "Нет актуального статуса. ") + game.view.state + " · " + (game.view.observeOnly ? "наблюдение" : "физические движения"); wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: game.view.reason; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Решение: " + game.view.decision + " · Резерв перемещения (оценка): " + game.view.travel + " м · Задание: " + game.view.jobId; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Мяч: " + game.view.ball; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Button { objectName: "gameOpenStreams"; text: "Выбрать / запросить видео в «Стримах»"; onClicked: root.requestStreams() }
        ComboBox {
            objectName: "gameVideoSelector"
            Layout.fillWidth: true; model: streams.receivers; textRole: "label"
            currentIndex: model.findIndex(s => s.id === root.selectedStream)
            enabled: count > 0
            displayText: currentIndex < 0 ? (count ? "Выберите принимаемый поток" : "Нет принимаемых потоков") : currentText
            onActivated: root.selectedStream = model[currentIndex].id
        }
        SelectableLabel {
            text: "Разметка мяча видна только в потоке, который её публикует. Доступные выходы объявляет робот; GUI не создаёт отдельный поток ball."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        SelectableLabel {
            text: root.reception.error || (root.reception.active ? (root.reception.size || "Ожидание кадра")
                + " · " + (root.reception.fps ?? "—") + " FPS" : "Выберите поток после запуска приёма в «Стримах».")
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        SelectableLabel { text: "Нет новых кадров видео"; visible: root.reception.stalled || false }
        Image {
            objectName: "gameVideoImage"; source: root.frameUrl; cache: false; fillMode: Image.PreserveAspectFit
            visible: root.reception.active; Layout.fillWidth: true; Layout.preferredHeight: 260
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button {
                objectName: "gamePositionRefresh"; text: "Обновить свою позицию"
                enabled: game.view.canRefresh && !localisation.view.pending && !localisation.view.checking
                onClicked: { if (!localisation.view.checked) localisation.check(); else localisation.refresh() }
            }
            Button {
                objectName: "gameWatchPosition"
                text: localisation.view.watching ? "Отключить данные позиции" : "Получать данные позиции"
                enabled: game.view.canRefresh && !localisation.view.subscriptionPending
                onClicked: localisation.watch(!localisation.view.watching)
            }
        }
        SelectableLabel {
            Layout.fillWidth: true; wrapMode: Text.Wrap
            text: localisation.view.fresh && localisation.view.pose.length === 3
                ? (localisation.view.result.valid ? "Позиция на поле: x=" : "Предварительная позиция, не подтверждена: x=") + localisation.view.pose[0].toFixed(2) + " м, y=" + localisation.view.pose[1].toFixed(2) + " м, угол=" + (localisation.view.pose[2]*180/Math.PI).toFixed(1) + "°"
                : "Позиция не подтверждена. " + localisation.view.status
        }
        SelectableLabel { text: "Подписка localisation.state общая с картой и «Источниками данных». Она не запускает локализацию. Начальную позицию и запуск задайте в панели «Локализация»."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Данные локализации с valid=false не подтверждают готовность к игре. Геометрию поля и направление движений нужно проверить перед физическим запуском."; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
