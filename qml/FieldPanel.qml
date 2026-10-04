import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ColumnLayout {
    id: root
    property var kddockwidgets_min_size: Qt.size(580,480)
    RowLayout {
        Button { text:"Загрузить карту"; enabled:backend.view.connected && !fieldEditor.view.busy; onClicked:fieldEditor.refresh() }
        Button { text:"+ Метка";enabled:fieldEditor.view.available && !fieldEditor.view.busy;onClicked:fieldEditor.addMark() }
        Button { objectName:"competitionFieldTemplate";text:"Шаблон 3,40 × 2,40";enabled:fieldEditor.view.available && !fieldEditor.view.busy;onClicked:fieldEditor.competitionTemplate() }
        ComboBox {
            Layout.fillWidth:true
            model:fieldEditor.view.keys.filter(k => k.startsWith("field."))
            onActivated:fieldEditor.select(currentText)
            currentIndex:model.indexOf(fieldEditor.view.selected)
        }
    }
    SelectableLabel { text:fieldEditor.view.notice; wrapMode:Text.Wrap; Layout.fillWidth:true }
    RowLayout {
        visible:fieldEditor.view.draftCount>0
        Button { text:"Сохранить всю карту";enabled:controls.view.owns && !controls.view.pending && !fieldEditor.view.busy;onClicked:fieldEditor.saveAll() }
        Button { text:"Отменить все черновики";enabled:!fieldEditor.view.busy;onClicked:fieldEditor.discardAll() }
        Label { text:fieldEditor.view.draftCount+" объектов изменено" }
    }
    RowLayout {
        Layout.fillWidth:true; Layout.fillHeight:true
        Canvas {
            id: map
            objectName:"fieldMap"
            Layout.fillWidth:true;Layout.fillHeight:true
            Layout.minimumWidth:220;Layout.minimumHeight:320
            property var values:fieldEditor.view.values
            property var g:values["field.geometry"] || null
            property real ppm:g ? Math.min((width-50)/g.carpet_width,(height-60)/g.carpet_length) : 1
            function px(y) { return width/2-y*ppm }
            function py(x) { return height/2-x*ppm }
            onValuesChanged:requestPaint()
            onWidthChanged:requestPaint()
            onHeightChanged:requestPaint()
            Connections { target:fieldEditor; function onChanged() { map.requestPaint() } }
            onPaint: {
                let c=getContext("2d");c.reset();c.fillStyle="#20282a";c.fillRect(0,0,width,height)
                if (!g) return
                c.fillStyle="#267447";c.fillRect(px(g.carpet_width/2),py(g.carpet_length/2),g.carpet_width*ppm,g.carpet_length*ppm)
                c.strokeStyle="#ffffff";c.lineWidth=Math.max(1,g.paint_width*ppm)
                c.strokeRect(px(g.width/2),py(g.length/2),g.width*ppm,g.length*ppm)
                c.beginPath();c.moveTo(px(g.width/2),py(0));c.lineTo(px(-g.width/2),py(0));c.stroke()
                c.beginPath();c.arc(px(0),py(0),g.circle_diameter*ppm/2,0,Math.PI*2);c.stroke()
                for (let key of Object.keys(values)) {
                    let m=values[key]
                    if (key.startsWith("field.mark.") && m.enabled) {
                        c.save();c.translate(px(m.y),py(m.x));c.rotate(-m.angle-Math.PI/2)
                        c.strokeStyle=key===fieldEditor.view.selected ? "#ff8fe9" : "white"
                        c.fillStyle=c.strokeStyle;c.lineWidth=Math.max(1,m.width*ppm)
                        if (m.kind==="ring" || m.kind==="disk") {
                            c.beginPath();c.arc(0,0,m.size*ppm/2,0,Math.PI*2)
                            if(m.kind==="disk") c.fill();else c.stroke()
                        } else {
                            c.beginPath();c.moveTo(-m.size*ppm/2,0);c.lineTo(m.size*ppm/2,0)
                            if(m.kind==="cross") {c.moveTo(0,-m.size2*ppm/2);c.lineTo(0,m.size2*ppm/2)}
                            c.stroke()
                        }
                        c.restore()
                        c.fillStyle="white";c.font="10px sans-serif";c.fillText(key.split('.').pop(),px(m.y)+5,py(m.x)-5)
                    }
                    if (key.startsWith("field.goal.")) {
                        c.strokeStyle=m.colour==="blue" ? "#45a4ff" : m.colour==="yellow" ? "#ffe347" : "white"
                        c.lineWidth=5;c.beginPath();c.moveTo(px(m.y-m.width/2),py(m.x));c.lineTo(px(m.y+m.width/2),py(m.x));c.stroke()
                        c.fillStyle=c.strokeStyle;c.font="12px sans-serif"
                        let own=Number(key.split('.').pop())===values["match.own_goal"]
                        c.fillText(own ? "Свои" : "Чужие",px(m.y)+5,py(m.x)+(m.x>0 ? -8 : 18))
                    }
                }
                c.fillStyle="white";c.font="12px sans-serif"
                c.fillText("+X ↑  +Y ←   "+g.length+" × "+g.width+" м",8,18)
                c.fillText("Клик/перетаскивание: позиция выбранной метки",8,height-8)
            }
            MouseArea {
                anchors.fill:parent
                function place(mouse) { if(map.g) fieldEditor.place((height/2-mouse.y)/map.ppm,(width/2-mouse.x)/map.ppm) }
                onPressed:mouse => place(mouse)
                onPositionChanged:mouse => { if(pressed) place(mouse) }
            }
        }
        ScrollView {
            Layout.preferredWidth:330;Layout.fillHeight:true
            contentWidth:availableWidth
            ColumnLayout {
                width:parent.width
                ObjectEditor {
                    enabled:!fieldEditor.view.busy
                    Layout.fillWidth:true
                    fields:fieldEditor.view.meta.fields || ({})
                    initialValue:fieldEditor.view.draft
                    onEdited:value => fieldEditor.edit(value)
                }
                Label { text:"Метки: cross — крест, ring — кольцо, disk — диск, line — отрезок. Угол от +X. Неизмеренные размеры — только черновая геометрия.";wrapMode:Text.Wrap;Layout.fillWidth:true }
                Button { text:"Стандартные значения";enabled:fieldEditor.view.available;onClicked:fieldEditor.defaults() }
                Button { text:"Отменить черновик";enabled:fieldEditor.view.dirty;onClicked:fieldEditor.discard() }
                Button { text:"Удалить метку";visible:fieldEditor.view.selected.startsWith("field.mark.");onClicked:fieldEditor.removeMark() }
                Button { text:"Сохранить выбранный объект";enabled:fieldEditor.view.dirty && controls.view.owns && !controls.view.pending;onClicked:fieldEditor.save() }
                RowLayout {
                    Label { text:"Свои ворота:" }
                    Button { objectName:"ownYellowGoal"; text:"Жёлтые"; checkable:true; checked:fieldEditor.view.ownColour==="yellow"; enabled:controls.view.owns && !controls.view.pending && fieldEditor.view.ownColourReady; onClicked:fieldEditor.ownColour("yellow") }
                    Button { objectName:"ownBlueGoal"; text:"Синие"; checkable:true; checked:fieldEditor.view.ownColour==="blue"; enabled:controls.view.owns && !controls.view.pending && fieldEditor.view.ownColourReady; onClicked:fieldEditor.ownColour("blue") }
                }
            }
        }
    }
}
