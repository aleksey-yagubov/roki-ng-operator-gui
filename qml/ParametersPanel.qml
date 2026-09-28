import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: panel
    property var kddockwidgets_min_size: Qt.size(300, 280)
    Connections {
        target: backend
        function onParameterGroupsChanged() {
            group.currentIndex = 0
            backend.filterParameters("Все", search.text)
        }
    }
    Button {
        objectName: "parametersButton"
        text: "Запросить ключи"
        enabled: backend.view.connected && !backend.view.catalogsBusy
        onClicked: backend.requestCatalog("parameters")
    }
    RowLayout {
        Layout.fillWidth: true
        ComboBox {
            id: group
            objectName: "parameterGroup"
            Layout.fillWidth: true
            model: backend.parameterGroups
            onActivated: backend.filterParameters(currentText, search.text)
        }
        TextField {
            id: search
            objectName: "parameterSearch"
            Layout.fillWidth: true
            placeholderText: "Поиск ключа"
            onTextEdited: backend.filterParameters(group.currentText, text)
        }
    }
    ListView {
        id: keys
        objectName: "parametersList"
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 80
        clip: true
        model: parametersModel
        ScrollBar.vertical: ScrollBar {}
        delegate: ItemDelegate {
            required property var entry
            required property int index
            width: ListView.view.width
            text: entry.name
            highlighted: ListView.isCurrentItem
            onClicked: { keys.currentIndex = index; backend.inspectParameter(entry.name) }
        }
        Label { anchors.centerIn: parent; visible: keys.count === 0; text: "Нет ключей: запросите список или измените фильтр"; width: parent.width; wrapMode: Text.Wrap; horizontalAlignment: Text.AlignHCenter }
    }
    ScrollView {
        id: scroll
        objectName: "parameterDetailScroll"
        visible: backend.view.paramKey !== ""
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(details.implicitHeight, panel.height * 0.6)
        Layout.minimumHeight: Math.min(100, panel.height * 0.3)
        clip: true
        contentWidth: availableWidth
        ColumnLayout {
            id: details
            width: scroll.availableWidth
            Label { text: backend.view.paramKey || "Выберите параметр"; font.bold: true; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
            Label { text: backend.parameter.description || "Описание ещё не получено"; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "Тип: " + (backend.parameter.type || "-") + " | Пределы: "
                      + (backend.parameter.min ?? "-") + " … " + (backend.parameter.max ?? "-")
            }
            Label {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "Применение: " + ({live: "сразу", next_job: "со следующего движения", restart: "после перезапуска", next_frame: "со следующего кадра", next_request:"следующий запрос камеры",next_localisation:"при следующем запуске локализации"}[backend.parameter.apply] || backend.parameter.apply || "-")
            }
            ValueEditor {
                id: editor
                objectName: "parameterEditor"
                Layout.fillWidth: true
                meta: backend.parameter
                initialValue: backend.parameter.value
                enabled: controls.view.owns && !controls.view.pending && backend.parameter.value !== undefined
            }
            Flow {
                Layout.fillWidth: true
                spacing: 6
                Button {
                    objectName: "saveParameterButton"
                    text: "Сохранить значение"
                    enabled: editor.enabled
                    onClicked: backend.saveParameter(backend.view.paramKey, editor.value)
                }
                Button { text: "Перечитать"; enabled: backend.view.connected && backend.view.paramKey !== ""; onClicked: backend.inspectParameter(backend.view.paramKey) }
                Button { text: "Вернуть стандартное"; enabled: editor.enabled && backend.parameter.default !== undefined; onClicked: backend.saveParameter(backend.view.paramKey,backend.parameter.default) }
            }
            Label { visible: !controls.view.owns; text: "Для записи нажмите «Получить управление» в верхней панели."; Layout.fillWidth: true; wrapMode: Text.Wrap }
            Label { text: controls.view.error; visible: text !== ""; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RawDetails { objectName: "parameterDetails"; text: backend.view.paramText }
        }
    }
}
