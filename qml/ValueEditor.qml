import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: root
    property var meta: ({})
    property var initialValue: undefined
    readonly property var value: meta.choices ? choice.currentText : meta.type === "bool" ? boolean.checked : number.text
    signal edited(var value)
    function reset() {
        if (meta.choices)
            choice.currentIndex = Math.max(0, meta.choices.indexOf(initialValue))
        else if (meta.type === "bool")
            boolean.checked = initialValue === true
        else
            number.text = initialValue === undefined ? "" : String(initialValue)
    }
    onInitialValueChanged: reset()
    Component.onCompleted: reset()
    ComboBox {
        id: choice
        visible: !!root.meta.choices
        Layout.fillWidth: true
        model: root.meta.choices || []
        onActivated: root.edited(currentText)
    }
    CheckBox {
        id: boolean
        visible: !root.meta.choices && root.meta.type === "bool"
        text: checked ? "Да" : "Нет"
        onToggled: root.edited(checked)
    }
    TextField {
        id: number
        objectName: "valueInput"
        visible: !root.meta.choices && root.meta.type !== "bool"
        Layout.fillWidth: true
        selectByMouse: true
        placeholderText: root.meta.type === "int" ? "Целое число" : "Значение"
        onTextEdited: root.edited(text)
    }
}
