import QtQuick
import QtQuick.Controls

TextArea {
    id: label
    readOnly: true
    selectByMouse: true
    wrapMode: TextEdit.Wrap
    padding: 0
    background: null
    persistentSelection: true
    TapHandler {
        acceptedButtons: Qt.RightButton
        onTapped: menu.popup()
    }
    Menu {
        id: menu
        MenuItem {
            text: "Копировать"
            enabled: label.selectedText.length > 0
            onTriggered: label.copy()
        }
        MenuItem {
            text: "Выделить всё"
            onTriggered: label.selectAll()
        }
    }
}
