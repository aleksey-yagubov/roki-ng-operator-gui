import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: scroll
    property var kddockwidgets_min_size: Qt.size(320, 280)
    contentWidth: availableWidth
    clip: true
    ColumnLayout {
        width: scroll.availableWidth
        Label { text: "Источник видео"; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
        ComboBox { id: sourceBackend; model:["runtime","direct-gst"]; enabled:video.view.canEditSettings; Layout.fillWidth:true }
        Label { text:sourceBackend.currentText === "runtime" ? "Сначала запустите runtime-камеру в панели «Цвета и камера». Этот поток показывает её кадры." : "Direct-gst — ручное видео; параметры runtime-камеры к нему не применяются."; wrapMode:Text.Wrap; Layout.fillWidth:true }
        Label { text: "Нужны управление и MANUAL. Видео запускается только кнопкой. IMU не включается."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Button { objectName: "videoCapabilitiesButton"; text: "Запросить возможности"; enabled: backend.view.connected && !video.view.pending; onClicked: video.getCapabilities() }
        Label { objectName: "videoCapabilitiesSummary"; text: video.view.capabilitiesSummary; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: video.view.startBlockedReason; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Button { text: "Включить ручной режим"; visible: controls.view.owns && !controls.view.manual; enabled: controls.view.canEnterManual; onClicked: controls.enterManual() }
        GridLayout {
            columns: 2
            Layout.fillWidth: true
            enabled: video.view.canEditSettings
            Label { text: "Сенсор RAW" }
            RowLayout {
                enabled:sourceBackend.currentText === "direct-gst"
                TextField { id: sw; objectName: "videoSensorWidth"; text: "1600"; Layout.preferredWidth: 65; inputMethodHints: Qt.ImhDigitsOnly }
                Label { text: "×" }
                TextField { id: sh; text: "1300"; Layout.preferredWidth: 65; inputMethodHints: Qt.ImhDigitsOnly }
                ComboBox { id: depth; model: ["10", "8"]; Layout.preferredWidth: 60 }
            }
            Label { text: "Выход" }
            RowLayout {
                TextField { id: ow; text: "800"; Layout.preferredWidth: 65; inputMethodHints: Qt.ImhDigitsOnly }
                Label { text: "×" }
                TextField { id: oh; text: "650"; Layout.preferredWidth: 65; inputMethodHints: Qt.ImhDigitsOnly }
            }
            Label { text: "FPS" }
            TextField { id: fps; text: "60"; Layout.fillWidth: true }
            Label { text: "Кодек" }
            ComboBox { id: codec; model: ["h264", "jpeg"]; Layout.fillWidth: true }
            Label { text: "Битрейт, бит/с"; enabled: codec.currentText === "h264" }
            TextField { id: bitrate; text: "2000000"; enabled: codec.currentText === "h264"; Layout.fillWidth: true }
            Label { text: "Декодер ПК" }
            ComboBox { id: decoder; model: codec.currentText === "h264" ? (Qt.platform.os === "osx" ? ["avdec_h264"] : ["vah264dec", "avdec_h264"]) : (Qt.platform.os === "osx" ? ["jpegdec"] : ["vajpegdec", "jpegdec"]); Layout.fillWidth: true }
            Label { text: "UDP-порт ПК" }
            SpinBox { id: port; from: 1024; to: 65535; value: 5004; editable: true; Layout.fillWidth: true }
        }
        Label { text: "JPEG: обе стороны выхода кратны 8 (например 800×648). Размеры сенсора вводятся явно, это не каталог проверенных режимов."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Flow {
            Layout.fillWidth: true
            spacing: 6
            Button {
                objectName: "videoStartButton"
                text: "Запустить видео"
                enabled: video.view.canStart
                onClicked: video.start({backend:sourceBackend.currentText,sensorWidth: sw.text, sensorHeight: sh.text, depth: depth.currentText,
                    width: ow.text, height: oh.text, fps: fps.text, codec: codec.currentText,
                    bitrate: bitrate.text, port: port.value, decoder: decoder.currentText})
            }
            Button { objectName: "videoStopButton"; text: "Остановить видео"; enabled: video.view.canStop; onClicked: video.stop() }
            Button { text: "Показать окно"; enabled: video.view.streamId !== ""; onClicked: video.showWindow() }
            Button { text: "Статус"; enabled: video.view.streamId !== "" && !video.view.pending; onClicked: video.refresh() }
        }
        Label { text: video.view.phase + " | " + video.view.size + " | показано кадров: " + video.view.frames; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { visible: video.view.stalled; text: "Нет новых кадров более 3 секунд. Проверьте отправку, UDP-порт и firewall."; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Label { text: video.view.error; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
        RawDetails { text: video.view.capabilities; Layout.fillWidth: true }
    }
}
