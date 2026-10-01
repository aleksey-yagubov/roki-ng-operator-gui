import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    property string ballImage: ""
    function updateBallImage() { ballImage = streams.imageUrl(streams.view.ballStream) }
    Connections { target: streams; function onFramesChanged() { root.updateBallImage() } }
    Timer { interval: 500; running: root.visible && game.view.running; repeat: true; onTriggered: { if (!localisation.view.checked) localisation.check(); else localisation.refresh() } }
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
        }
        SelectableLabel { text: game.view.canObserve && !game.view.canStart ? "Наблюдение само включит MANUAL. Команды движения не отправляются." : game.view.blockedReason; visible: !game.view.canStart; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameError"; text: game.view.error; color: "#b03030"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameState"; text: (game.view.fresh ? "" : "Нет актуального статуса. ") + game.view.state + " · " + (game.view.observeOnly ? "наблюдение" : "физические движения"); wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: game.view.reason; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Решение: " + game.view.decision + " · Резерв перемещения (оценка): " + game.view.travel + " м · Задание: " + game.view.jobId; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Мяч: " + game.view.ball; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            Button { objectName: "gameVideoStart"; text: "Показать видео и мяч"; enabled: game.view.running && streams.view.canManage && !streams.view.busyKeys.includes("create"); onClicked: streams.showBall(ballPort.value) }
            SpinBox { id: ballPort; from: 1024; to: 65535; value: 5010; editable: true }
            Button { text: "Отключить видео"; enabled: !!streams.view.ballStream; onClicked: streams.detach(streams.view.ballStream) }
        }
        SelectableLabel { text: streams.view.error || streams.reception(streams.view.ballStream).error || "Видео с рамкой мяча; оранжевая рамка — наблюдение ещё не подтверждено."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: streams.reception(streams.view.ballStream).stalled ? "Нет новых кадров видео" : ""; visible: text.length > 0 }
        Image { objectName: "gameVideoImage"; source: root.ballImage; cache: false; fillMode: Image.PreserveAspectFit; Layout.fillWidth: true; Layout.preferredHeight: 390 }
        Button { text: "Обновить свою позицию"; onClicked: { localisation.check(); localisation.refresh() } }
        SelectableLabel {
            Layout.fillWidth: true; wrapMode: Text.Wrap
            text: localisation.view.fresh && localisation.view.pose.length === 3
                ? (localisation.view.result.valid ? "Позиция на поле: x=" : "Предварительная позиция, не подтверждена: x=") + localisation.view.pose[0].toFixed(2) + " м, y=" + localisation.view.pose[1].toFixed(2) + " м, угол=" + (localisation.view.pose[2]*180/Math.PI).toFixed(1) + "°"
                : "Позиция не подтверждена. " + localisation.view.status
        }
        SelectableLabel { text: "Начальную позицию и запуск локализации задайте в панели «Локализация»."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Данные локализации с valid=false не подтверждают готовность к игре. Геометрию поля и направление движений нужно проверить перед физическим запуском."; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
