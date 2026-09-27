import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

GroupBox {
    id: card
    property var schema: ({})
    property string testName
    property string raw
    property var values: ({})
    title: schema.title || testName
    function defaults() {
        let result = {}
        for (let key in (schema.parameters || {})) {
            let field = schema.parameters[key]
            result[key] = field.default ?? (field.choices ? field.choices[0] : "")
        }
        values = result
    }
    onSchemaChanged: defaults()
    function update(key, value) { let copy = Object.assign({}, values); copy[key] = value; values = copy }
    ColumnLayout {
        anchors.fill: parent
        Label { visible: !card.schema.parameters; text: "Описание запрашивается…" }
        Label { visible: card.schema.body_imu === true; text: "Использует IMU тела"; Layout.fillWidth: true; wrapMode: Text.Wrap }
        Repeater {
            model: Object.keys(card.schema.parameters || {})
            delegate: ColumnLayout {
                required property string modelData
                property var field: card.schema.parameters[modelData]
                visible: !field.when || card.values.mode === field.when
                Layout.fillWidth: true
                Label { text: modelData + (field.min !== undefined ? " [" + field.min + " … " + field.max + "]" : ""); Layout.fillWidth: true; wrapMode: Text.Wrap }
                ValueEditor { Layout.fillWidth: true; meta: field; initialValue: field.default ?? (field.choices ? field.choices[0] : ""); onEdited: value => card.update(modelData, value) }
            }
        }
        Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            text: (card.schema.unavailable_modes || {})[card.values.mode] || ""
            visible: text !== ""
        }
        Button {
            objectName: "startTest_" + card.testName
            text: "Запустить"
            enabled: controls.view.ready && !!card.schema.parameters && !(card.schema.unavailable_modes || {})[card.values.mode]
            onClicked: backend.startTest(card.testName, card.values)
        }
        RawDetails { text: card.raw }
    }
}
