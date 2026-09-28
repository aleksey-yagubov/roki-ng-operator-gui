import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var fields: ({})
    property var initialValue: ({})
    property var value: ({})
    property var fieldKeys: []
    signal edited(var value)
    property var labels: ({length:"Длина поля, м",width:"Ширина / толщина, м",
        carpet_length:"Длина покрытия, м",carpet_width:"Ширина покрытия, м",
        circle_diameter:"Диаметр центра, м",circle_measured:"Круг измерен",
        paint_width:"Ширина линии, м",x:"X, м",y:"Y, м",size:"Диаметр / длина, м",
        size2:"Второе плечо, м",angle:"Угол, рад",enabled:"Включено",
        kind:"Тип",height:"Высота, м",colour:"Цвет",measured:"Размеры измерены"})
    function update(key,v) { let next=Object.assign({},value); next[key]=v; value=next; edited(next) }
    onInitialValueChanged: value=Object.assign({},initialValue || {})
    function refreshKeys() {
        let next=Object.keys(fields)
        if (JSON.stringify(next)!==JSON.stringify(fieldKeys)) fieldKeys=next
    }
    onFieldsChanged: refreshKeys()
    Component.onCompleted: { value=Object.assign({},initialValue || {});refreshKeys() }
    Repeater {
        model: root.fieldKeys
        RowLayout {
            required property string modelData
            property var spec: root.fields[modelData]
            property bool isBool: spec === "bool"
            property bool isChoice: !isBool && typeof spec[0] === "string"
            Label { text: root.labels[modelData] || modelData; Layout.preferredWidth: 155 }
            CheckBox {
                visible: parent.isBool
                checked: root.initialValue ? root.initialValue[parent.modelData] === true : false
                onToggled: root.update(parent.modelData,checked)
            }
            ComboBox {
                visible: parent.isChoice
                model: parent.isChoice ? parent.spec : []
                currentIndex: parent.isChoice ? Math.max(0,parent.spec.indexOf((root.initialValue || {})[parent.modelData])) : 0
                onActivated: root.update(parent.modelData,currentText)
                Layout.fillWidth: true
            }
            TextField {
                visible: !parent.isBool && !parent.isChoice
                text: String((root.initialValue || {})[parent.modelData] ?? "")
                selectByMouse: true
                onTextEdited: root.update(parent.modelData,text)
                Layout.fillWidth: true
            }
        }
    }
}
