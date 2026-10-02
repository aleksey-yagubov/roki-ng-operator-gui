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
    property var detail: { streams.view; return streams.detail(selected) }
    property var reception: { streams.view; return streams.reception(selected) }
    property bool busy: streams.view.busyKeys.includes(selected)
    property bool running: ["starting", "running"].includes(detail.state)
    property string keySignature: Object.keys(detail.controls || {}).join("|")
    property var controlKeys: keySignature ? keySignature.split("|") : []
    onSelectedChanged: streams.select(selected)
    Connections {
        target: streams
        function onOutputsChanged() {
            if (!streams.outputs.some(s => s.name === root.selected))
                root.selected = streams.outputs.length ? streams.outputs[0].name : ""
        }
    }
    Dialog {
        id: confirmStop
        objectName: "videoStopConfirm"
        property string outputName: ""
        title: "Остановить для всех?"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: "Другие операторы тоже потеряют видео.\nОстановить «" + confirmStop.outputName + "»?" }
        onAccepted: streams.stop(outputName)
    }
    ColumnLayout {
        width: root.availableWidth
        Button {
            objectName: "videoCatalogButton"
            text: "Запросить видеовыходы"
            enabled: backend.view.connected && !streams.view.catalogBusy
            onClicked: streams.refresh()
        }
        Label { text: streams.view.error; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap }
        ComboBox {
            objectName: "videoTransmissionList"
            model: streams.outputs; textRole: "label"; Layout.fillWidth: true
            currentIndex: model.findIndex(s => s.name === root.selected)
            displayText: currentIndex >= 0 ? currentText : "Сначала запросите видеовыходы"
            onActivated: root.selected = model[currentIndex].name
        }
        Label {
            text: (root.detail.state || "Нет данных") + " · получателей: " + (root.detail.receivers ?? "—")
                + (root.detail.available === false ? " · " + (root.detail.reason || "Недоступен") : "")
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        Flow {
            Layout.fillWidth: true; spacing: 6
            Button {
                objectName: "streamWatch"
                text: root.reception.active ? "Открыть просмотр" : "Смотреть"
                enabled: backend.view.connected && streams.view.supported && !!root.selected && !root.busy && !root.reception.stopping
                    && (root.running || (streams.view.canManage && root.detail.available === true))
                onClicked: streams.watch(root.selected, autoPort.checked ? 0 : port.value, decoder.currentText)
            }
            Button {
                objectName: "videoDetachButton"; text: "Отключиться"
                enabled: backend.view.connected && (root.detail.subscribed === true
                    || ["inspecting", "preparing", "joining", "reconciling", "receiving"].includes(root.reception.phase))
                onClicked: streams.unsubscribe(root.selected)
            }
            Button {
                objectName: "openStreamView"; text: "Ещё просмотр"
                enabled: root.reception.active
                onClicked: videoViews.add(root.selected)
            }
        }
        Label {
            text: root.reception.error || ("Приём: " + root.reception.phase + " · "
                + (root.reception.fps ?? "—") + " FPS · порт " + (root.reception.port || "—"))
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        Label {
            text: "H.264 · FPS кодера: " + (root.detail.actual_fps ?? "—")
                + " · производитель: " + (root.detail.producer?.publishing ? "публикует" : root.detail.producer?.requested ? "запрошен" : "не запрошен")
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        Label { text: root.detail.error || ""; visible: text.length > 0; Layout.fillWidth: true; wrapMode: Text.Wrap }
        GroupBox {
            title: "Общие настройки видеовыхода"
            visible: !!root.selected
            Layout.fillWidth: true
            ColumnLayout {
                anchors.fill: parent
                Label {
                    text: streams.view.canManage ? "Изменения применяются отдельно. После запуска доступны только live-поля."
                        : "Для изменения настроек и запуска остановленного выхода получите управление."
                    Layout.fillWidth: true; wrapMode: Text.Wrap
                }
                Repeater {
                    model: root.controlKeys
                    delegate: ColumnLayout {
                        required property string modelData
                        property var meta: root.detail.controls?.[modelData] || ({})
                        property bool canEdit: { streams.view; return streams.editable(root.selected, modelData) }
                        Layout.fillWidth: true
                        Label {
                            text: modelData + (meta.fixed ? " (фиксировано)" : meta.live ? " (live)" : "")
                                + (meta.min !== undefined ? " · " + meta.min + " … " + meta.max : "")
                            Layout.fillWidth: true; wrapMode: Text.Wrap
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            ValueEditor {
                                id: editor
                                objectName: "videoSetting-" + modelData
                                meta: parent.parent.meta
                                initialValue: root.detail.settings?.[modelData]
                                enabled: parent.parent.canEdit
                                Layout.fillWidth: true
                                Connections {
                                    target: root
                                    function onSelectedChanged() { editor.reset() }
                                }
                            }
                            Button {
                                objectName: "videoApply-" + modelData
                                text: "Применить"; visible: !meta.fixed; enabled: canEdit
                                onClicked: streams.update(root.selected, modelData, editor.value)
                            }
                        }
                    }
                }
            }
        }
        CheckBox { id: advanced; text: "Дополнительные настройки приёмника" }
        GridLayout {
            visible: advanced.checked; Layout.fillWidth: true; columns: 2
            Label { text: "Декодер ПК" }
            ComboBox {
                id: decoder; objectName: "videoDecoder"
                model: Qt.platform.os === "linux" ? ["vah264dec", "avdec_h264"] : ["avdec_h264"]
                Layout.fillWidth: true; enabled: !root.reception.active && !root.busy
            }
            CheckBox { id: autoPort; text: "Автоматический UDP-порт"; checked: true }
            SpinBox {
                id: port; from: 1024; to: 65535; value: 5004; editable: true
                enabled: !autoPort.checked && !root.reception.active && !root.busy
                Layout.fillWidth: true
            }
        }
        Button {
            objectName: "streamStop"; text: "Остановить для всех"
            enabled: streams.view.canManage && root.running && !root.busy
            onClicked: {
                if ((root.detail.receivers || 0) > (root.detail.subscribed ? 1 : 0)) {
                    confirmStop.outputName = root.selected
                    confirmStop.open()
                } else streams.stop(root.selected)
            }
        }
        Label {
            text: "Просмотры одного выхода используют общий приёмник. Закрытие панели не отключает приём. Последний получатель отключился — передача остановлена; автономная игра продолжается."
            Layout.fillWidth: true; wrapMode: Text.Wrap
        }
        RawDetails { text: JSON.stringify(root.detail, null, 2); Layout.fillWidth: true }
    }
}
