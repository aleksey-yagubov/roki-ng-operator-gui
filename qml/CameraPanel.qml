import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "cameraScroll"
    property var kddockwidgets_min_size: Qt.size(380, 300)
    contentWidth: availableWidth
    clip: true
    onVisibleChanged: camera.watch(visible && poll.checked)
    ColumnLayout {
        width: root.availableWidth
        Label { text: "Runtime-камера · camera-worker"; font.bold: true }
        Label { text: "1600×1300 RAW10 → 800×650 BGR. Захват всегда с IMU, без запуска видеопередачи. Direct-gst настраивается в «Стримах»."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "cameraRefresh"; text: "Запросить состояние и controls"; enabled: backend.view.connected && !camera.view.busy; onClicked: camera.refresh() }
            CheckBox { id: poll; text: "Обновлять статус"; onToggled: camera.watch(checked && root.visible) }
        }
        RowLayout {
            Label { text: "Период, мкс" }
            SpinBox { id: duration; objectName: "cameraDuration"; from: 8333; to: 100000; value: 16667; editable: true; enabled: !camera.view.state.running }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "cameraStart"; text: "Запустить камеру"; enabled: camera.view.canEdit && controls.view.manual && !camera.view.state.running; onClicked: camera.start(duration.value) }
            Button { objectName: "cameraStop"; text: "Остановить камеру…"; enabled: camera.view.canEdit; onClicked: confirmStop.open() }
        }
        Dialog {
            id: confirmStop
            title: "Остановить камеру?"
            standardButtons: Dialog.Yes | Dialog.No
            modal: true
            Label { text: "Будут остановлены также зависимые детекторы, локализация и их передачи."; width: 300; wrapMode: Text.Wrap }
            onAccepted: camera.stop()
        }
        Label { text: !controls.view.manual ? "Для старта нужны управление и MANUAL." : ""; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { objectName: "cameraState"; text: (camera.view.state.running ? "Камера работает" : "Захват не подтверждён") + " · IMU: " + (camera.view.state.imu_sync?.state ?? "нет данных") + " · кадр: " + (camera.view.state.sequence ?? "—"); Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Точное сопоставление IMU готово только при synced. Aligning не означает остановку кадров."; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: camera.view.state.error || camera.view.notice; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "ISP · запрошенные значения и черновик"; font.bold: true }
        Repeater {
            model: camera.keys
            ColumnLayout {
                id: row
                required property string modelData
                property var meta: camera.view.metas[modelData] || ({})
                Layout.fillWidth: true
                Label { text: row.meta.description || row.modelData; Layout.fillWidth: true; wrapMode: Text.Wrap }
                RowLayout {
                    Layout.fillWidth: true
                    Label { text: row.modelData; Layout.fillWidth: true; wrapMode: Text.Wrap }
                    ValueEditor { Layout.preferredWidth: 140; meta: row.meta; initialValue: camera.view.values[row.modelData]; enabled: camera.view.canEdit && row.meta.supported !== false; onEdited: value => camera.edit(row.modelData, value) }
                }
                Label { text: "Запрошено: " + camera.view.requested[row.modelData] + " · " + (row.meta.supported === null ? "Поддержка ещё не проверена" : row.meta.supported === false ? "Не поддерживается" : "Поддерживается") + (row.meta.min !== undefined ? " · " + row.meta.min + " … " + row.meta.max : ""); Layout.fillWidth: true; wrapMode: Text.Wrap }
            }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { text: "Стандартные"; enabled: camera.view.canEdit; onClicked: camera.defaults() }
            Button { text: "Отменить черновик"; enabled: camera.view.dirty; onClicked: camera.discard() }
            Button { objectName: "cameraApply"; text: "Применить временно"; enabled: camera.view.canEdit && camera.view.dirty; onClicked: camera.apply(false) }
            Button { objectName: "cameraSave"; text: "Сохранить"; enabled: camera.view.canEdit && camera.view.dirty; onClicked: camera.apply(true) }
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { text: "Зафиксировать AE"; enabled: camera.view.canEdit && !!camera.view.state.running; onClicked: camera.freeze("exposure") }
            Button { text: "Зафиксировать AWB"; enabled: camera.view.canEdit && !!camera.view.state.running; onClicked: camera.freeze("white_balance") }
        }
        Label { text: "Применить и Freeze не записывают JSON. Сохранить записывает профиль робота. Controls относятся только к runtime-камере."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: "Измерено камерой (не запрошенные значения)"; font.bold: true }
        Label {
            property var measured: camera.view.state.measured_controls || ({})
            text: "Выдержка: " + (measured.exposure_us ?? "—") + " мкс · gain: " + (measured.gain ?? "—") + "\nWB: " + JSON.stringify(measured.colour_gains ?? null) + " · кадр: " + (measured.sequence ?? "—") + " · возраст: " + (camera.view.state.measured_age_ms ?? "—") + " мс"
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        RawDetails { text: JSON.stringify(camera.view.state, null, 2); Layout.fillWidth: true }
    }
}
