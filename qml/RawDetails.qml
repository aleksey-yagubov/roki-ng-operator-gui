import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property string text: ""
    Layout.fillWidth: true
    CheckBox { id: showRaw; text: "Показать исходный ответ" }
    TextArea {
        visible: showRaw.checked
        Layout.fillWidth: true
        text: root.text
        readOnly: true
        selectByMouse: true
        wrapMode: TextEdit.WrapAnywhere
    }
}
