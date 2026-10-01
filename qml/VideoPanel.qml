import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    objectName: "streamsScroll"
    property var kddockwidgets_min_size: Qt.size(400, 340)
    contentWidth: availableWidth
    clip: true
    property string selected: ""
    property string seenCreated: ""
    property string sourceId: ""
    property var detail: { streams.view; return streams.detail(selected) }
    property var reception: { streams.view; return streams.reception(selected) }
    property bool busy: streams.view.busyKeys.indexOf(selected) >= 0
    property var source: streams.view.sources.find(s => s.id === sourceId) || ({})
    property bool direct: source.id === "direct-gst"
    onSelectedChanged: streams.inspect(selected)
    Connections {
        target: backend
        function onChanged() {
            if (!backend.view.connected) {
                root.selected = ""
                root.sourceId = ""
                root.seenCreated = ""
            }
        }
    }
    Connections {
        target: streams
        function onChanged() {
            if (streams.view.lastCreated && root.seenCreated !== streams.view.lastCreated) {
                root.seenCreated = streams.view.lastCreated
                root.selected = streams.view.lastCreated
            }
            if (!streams.view.sources.some(s => s.id === root.sourceId))
                root.sourceId = streams.view.sources.length ? streams.view.sources[0].id : ""
        }
    }
    ColumnLayout {
        width: root.availableWidth
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button { objectName: "videoCatalogButton"; text: "Запросить источники и передачи"; enabled: backend.view.connected && !streams.view.catalogBusy; onClicked: streams.refresh() }
            Button { objectName: "addVideoView"; text: "+ Просмотр"; onClicked: videoViews.add(root.reception.active ? root.selected : "") }
        }
        SelectableLabel { text: streams.view.error; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap }
        GroupBox {
            title: "Новое определение передачи"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                ComboBox {
                    id: sources; objectName: "streamSource"
                    Layout.fillWidth: true; model: streams.view.sources; textRole: "name"
                    currentIndex: model.findIndex(s => s.id === root.sourceId)
                    onActivated: root.sourceId = model[currentIndex].id
                    displayText: root.source.name || root.source.id || "Сначала запросите источники"
                }
                Label { text: root.source.id ? root.source.id + " · " + (root.source.available ? "Доступен" : "Сейчас недоступен: " + (root.source.reason || "нет данных")) : "Список не запрошен"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { text: "Определение можно создать заранее. Создание не запускает захват и передачу."; Layout.fillWidth: true; wrapMode: Text.Wrap }
                GridLayout {
                    objectName: "directCaptureFields"
                    visible: root.direct
                    Layout.fillWidth: true; columns: 2
                    Label { text: "Сенсор, ширина" }
                    TextField { id: sw; text: "1600"; Layout.fillWidth: true }
                    Label { text: "Сенсор, высота" }
                    TextField { id: sh; text: "1300"; Layout.fillWidth: true }
                    Label { text: "RAW" }
                    ComboBox { id: depth; model: ["10", "8"]; Layout.fillWidth: true }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 2
                    Label { text: "Выход, ширина" }
                    TextField { id: widthInput; text: "800"; Layout.fillWidth: true }
                    Label { text: "Выход, высота" }
                    TextField { id: heightInput; text: "648"; Layout.fillWidth: true }
                    Label { text: root.direct ? "FPS захвата" : "Потолок FPS кодера" }
                    TextField { id: fps; text: "60"; Layout.fillWidth: true }
                    Label { text: "Предел FPS передачи"; visible: !root.direct }
                    TextField { id: maxFps; text: "15"; visible: !root.direct; Layout.fillWidth: true }
                    Label { text: "Кодек" }
                    ComboBox { id: codec; model: root.source.stream_settings?.codecs || []; Layout.fillWidth: true }
                    Label { text: "Битрейт, бит/с"; visible: codec.currentText === "h264" }
                    TextField { id: bitrate; text: "2000000"; visible: codec.currentText === "h264"; Layout.fillWidth: true }
                }
                Label { text: codec.currentText === "jpeg" ? "Для JPEG размеры кратны 8, например 800×648." : "Геометрия, кодек и источник меняются пересозданием."; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Button {
                    objectName: "streamCreate"
                    text: "Создать определение"
                    enabled: streams.view.canCreate && !!root.source.id
                    onClicked: streams.create({source: root.source.id, sensorWidth: sw.text, sensorHeight: sh.text, depth: depth.currentText,
                        width: widthInput.text, height: heightInput.text, fps: fps.text, max_fps: maxFps.text, codec: codec.currentText, bitrate: bitrate.text})
                }
                Button { text: "Список проверен: разрешить новое создание"; visible: !streams.view.canCreate && streams.view.canManage && !streams.view.busyKeys.includes("create"); onClicked: streams.acknowledgeUnknownCreate() }
            }
        }
        GroupBox {
            title: "Передачи на роботе"
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                ComboBox {
                    id: transmissions; objectName: "videoTransmissionList"
                    model: streams.view.streams.map(s => ({id:s.stream_id, label:s.source + " · " + s.stream_id + " · " + s.state}))
                    textRole: "label"; Layout.fillWidth: true
                    currentIndex: model.findIndex(s => s.id === root.selected)
                    onActivated: root.selected = model[currentIndex].id
                }
                Label { text: root.selected ? "ID: " + root.selected + " · " + (root.detail.state || "Запрос состояния…") + " · получателей: " + (root.detail.receivers ?? "—") : "Выберите передачу"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                Label { text: "Кодек: " + (root.detail.spec?.codec?.name || "—") + " · " + (root.detail.spec?.output?.width || "—") + "×" + (root.detail.spec?.output?.height || "—") + " · фактический FPS кодера: " + (root.detail.actual_fps ?? "—"); Layout.fillWidth: true; wrapMode: Text.Wrap }
                GridLayout {
                    Layout.fillWidth: true; columns: 2
                    Label { text: "UDP-порт приёмника" }
                    SpinBox { id: port; from: 1024; to: 65535; value: 5004; editable: true; enabled: !root.reception.active && !root.busy; Layout.fillWidth: true }
                    Label { text: "Декодер ПК" }
                    ComboBox {
                        id: decoder; Layout.fillWidth: true; enabled: !root.reception.active && !root.busy
                        model: root.detail.encoding_name === "JPEG" ? (Qt.platform.os === "linux" ? ["vajpegdec", "jpegdec"] : ["jpegdec"]) : (Qt.platform.os === "linux" ? ["vah264dec", "avdec_h264"] : ["avdec_h264"])
                    }
                }
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    Button { objectName: "streamStart"; text: "Запустить и принимать"; enabled: streams.view.canManage && !!root.detail.spec && !root.busy && !root.reception.active; onClicked: streams.connectStream(root.selected, port.value, decoder.currentText, true) }
                    Button { objectName: "videoAttachButton"; text: "Подключить мой приёмник"; enabled: backend.view.connected && ["starting","running"].includes(root.detail.state) && !root.busy && !root.reception.active; onClicked: streams.connectStream(root.selected, port.value, decoder.currentText, false) }
                    Button { objectName: "videoDetachButton"; text: "Отключить мой приёмник"; enabled: backend.view.connected && !!root.selected && !root.busy; onClicked: streams.detach(root.selected) }
                    Button { text: "Статус"; enabled: backend.view.connected && !!root.selected && !root.busy; onClicked: streams.inspect(root.selected) }
                }
                SelectableLabel { text: root.reception.error || ("Приём: " + root.reception.phase + " · " + (root.reception.fps ?? "—") + " FPS"); Layout.fillWidth: true; wrapMode: Text.Wrap }
                Flow {
                    Layout.fillWidth: true; spacing: 6
                    Button { objectName: "streamStop"; text: "Остановить для всех"; enabled: streams.view.canManage && !!root.selected && !root.busy; onClicked: streams.manage(root.selected, "stop") }
                    Button { objectName: "streamDestroy"; text: "Удалить определение"; enabled: streams.view.canManage && !!root.selected && !root.busy; onClicked: streams.manage(root.selected, "destroy") }
                }
                RowLayout {
                    visible: !!root.detail.spec && root.detail.spec.source !== "direct-gst"
                    Label { text: "Предел FPS" }
                    SpinBox { id: liveFps; from: 1; to: Math.max(1, Math.floor(root.detail.spec?.output?.fps || 1)); value: Math.min(15, to); editable: true }
                    Button { text: "Применить"; enabled: streams.view.canManage && !root.busy; onClicked: streams.update(root.selected, "max_fps", liveFps.value) }
                }
                RowLayout {
                    visible: root.detail.spec?.codec?.name === "h264"
                    TextField { id: newBitrate; text: "2000000"; Layout.fillWidth: true; placeholderText: "Битрейт" }
                    Button { text: "Изменить битрейт"; enabled: streams.view.canManage && root.detail.state === "stopped" && !root.busy; onClicked: streams.update(root.selected, "bitrate", Number(newBitrate.text)) }
                }
                Label { text: "Каждая передача использует отдельный UDP-порт. Просмотры одного стрима делят приёмник и декодер; закрытие просмотра не отключает приём."; Layout.fillWidth: true; wrapMode: Text.Wrap }
                RawDetails { text: JSON.stringify(root.detail, null, 2); Layout.fillWidth: true }
            }
        }
    }
}
