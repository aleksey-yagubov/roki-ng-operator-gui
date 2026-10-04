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
        SelectableLabel { text: "Автономная игра"; font.bold: true }
        Button {
            text: "Загрузить настройки игры и ворот"
            enabled: backend.view.connected && !fieldEditor.view.busy
            onClicked: { fieldEditor.refresh(); game.loadSettings() }
        }
        SelectableLabel {
            text: fieldEditor.view.ownColour === "yellow" ? "Свои: жёлтые. Бьём в синие."
                : fieldEditor.view.ownColour === "blue" ? "Свои: синие. Бьём в жёлтые."
                : "Загрузите карту и проверьте цвета ворот."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        RowLayout {
            enabled: fieldEditor.view.ownColourReady && game.view.canStart
            Button { text: "Свои жёлтые"; onClicked: fieldEditor.ownColour("yellow") }
            Button { text: "Свои синие"; onClicked: fieldEditor.ownColour("blue") }
        }
        SelectableLabel { text: fieldEditor.view.notice; Layout.fillWidth: true; wrapMode: Text.Wrap }
        CheckBox {
            objectName: "gameVisualLocalisation"
            text: "Локализация по камере (для исходного футбола, со следующего старта)"
            enabled: game.view.visualLocalisationKnown && game.view.canStart && (role.currentText === "forward" || role.currentText === "FIRA_penalty_Goalkeeper")
            checked: game.view.visualLocalisation
            onClicked: game.setVisualLocalisation(checked)
        }
        SelectableLabel { text: "Запуск включает движения. Стартовый манёвр center настраивается через params: game.forward.kick_off_ride. Повторный ввод — после готовности Pick up."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        RowLayout {
            ComboBox { id: role; objectName: "gameRole"; model: ["FIRA_penalty_Goalkeeper", "forward", "ball_kick_test", "simple_football"] }
            ComboBox { id: entry; objectName: "gameEntry"; model: ["center", "left", "right"]; enabled: role.currentText === "forward" || role.currentText === "simple_football" }
        }
        SelectableLabel {
            visible: role.currentText === "simple_football"
            text: "Simple football: без карты и одометрии. Left/right: ввод вперёд. Немедленный center: kickoff на 60° вбок, до 30 с. Задержка отключает kickoff. Прыжки с 250 мм, до 15 на попытку."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        SelectableLabel {
            visible: role.currentText === "ball_kick_test"
            text: "Тест подхода и удара: мяч перед роботом, свободное место впереди. Без ворот, карты и kickoff. До 5 прыжков доводки, один удар и завершение. При потере мяча или ошибке — завершение без повтора."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        RowLayout {
            SelectableLabel { text: "Задержка, с" }
            SpinBox { id: delay; objectName: "gameDelay"; from: 0; to: 30; value: 0 }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "gameStart"; text: game.view.pickupReady ? "Повторный ввод" : "Запустить игру"; enabled: game.view.canStart; onClicked: game.start(role.currentText, entry.currentText, delay.value) }
            Button { objectName: "gamePause"; text: "Пауза"; enabled: game.view.canPause; onClicked: game.pause() }
            Button { objectName: "gameResume"; text: "Продолжить"; enabled: game.view.canResume; onClicked: game.resume() }
            Button { objectName: "gamePickup"; text: "Pick up"; enabled: game.view.canPickup; onClicked: game.pickup() }
            Button { objectName: "gameConfirmUpright"; text: "Робот установлен вертикально"; visible: game.view.confirmationRequired; enabled: game.view.canConfirm; onClicked: game.confirmUpright() }
            Button { objectName: "gameStop"; text: "Остановить игру"; enabled: game.view.canStop; onClicked: game.stop() }
            Button { objectName: "gameRefresh"; text: "Запросить статус"; enabled: game.view.canRefresh; onClicked: game.refresh() }
            Button { objectName: "gameSubscribe"; text: game.view.watching ? "Отключить данные игры" : "Получать данные игры"; enabled: game.view.canRefresh && !game.view.subscriptionPending; onClicked: game.watch(!game.view.watching) }
        }
        SelectableLabel { text: game.view.blockedReason; visible: !game.view.canStart; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameError"; text: game.view.error; color: "#b03030"; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { objectName: "gameState"; text: (game.view.fresh ? "" : "Нет актуального статуса. ") + game.view.role + " · " + game.view.state + " · " + game.view.phase; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Восстановление: " + game.view.recovery + " · Попытка вставания: " + game.view.recoveryAttempt + (game.view.pickupReady ? " · Готов к переносу" : ""); wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: game.view.reason; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Решение: " + game.view.decision + " · Пройденный путь (одометрия): " + game.view.travel + " м · Задание: " + game.view.jobId; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Оценка положения: " + game.view.position; wrapMode: Text.Wrap; Layout.fillWidth: true }
        SelectableLabel { text: "Последняя визуальная поправка: " + game.view.correction; wrapMode: Text.Wrap; Layout.fillWidth: true }
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
