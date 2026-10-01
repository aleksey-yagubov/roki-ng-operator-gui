import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    property var kddockwidgets_min_size: Qt.size(420, 280)
    ColumnLayout {
        width: root.availableWidth
        Label { text: "FIRA · Пенальти · Вратарь"; font.bold: true }
        Label { text: "Наблюдение вычисляет решения без движений. Физический запуск разрешается роботом только после проверки геометрии (game.geometry_verified)."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            Label { text: "Задержка, с" }
            SpinBox { id: delay; objectName: "gameDelay"; from: 0; to: 30; value: 0 }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "gameObserve"; text: "Запустить наблюдение"; enabled: game.view.canStart; onClicked: game.start(true, delay.value) }
            Button { objectName: "gamePhysicalStart"; text: "Запустить с физическими движениями"; enabled: game.view.canStart; onClicked: game.start(false, delay.value) }
            Button { objectName: "gameStop"; text: "Остановить игру"; enabled: game.view.canStop; onClicked: game.stop() }
            Button { objectName: "gameRefresh"; text: "Запросить статус"; enabled: game.view.canRefresh; onClicked: game.refresh() }
        }
        Label { text: game.view.blockedReason; visible: !game.view.canStart; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { objectName: "gameError"; text: game.view.error; color: "#b03030"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { objectName: "gameState"; text: (game.view.fresh ? "" : "Нет актуального статуса. ") + game.view.state + " · " + (game.view.observeOnly ? "наблюдение" : "физические движения"); wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: game.view.reason; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "Решение: " + game.view.decision + " · Резерв перемещения (оценка): " + game.view.travel + " м · Задание: " + game.view.jobId; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "Мяч: " + game.view.ball; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "Данные локализации с valid=false не подтверждают готовность к игре. Геометрию поля и направление движений нужно проверить перед физическим запуском."; wrapMode: Text.Wrap; Layout.fillWidth: true }
    }
}
