import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    clip: true
    contentWidth: availableWidth
    property var kddockwidgets_min_size: Qt.size(580, 320)
    onVisibleChanged: if (!visible) localisation.watch(false)
    ColumnLayout {
    width: root.availableWidth
    Flow {
        Layout.fillWidth: true; spacing: 6
        Button { objectName: "localisationCheck"; text: localisation.view.checking ? "Проверяю…" : "Проверить возможности"; enabled: backend.view.connected && !localisation.view.checking; onClicked: localisation.check() }
        Button { objectName: "localisationCamera"; text: "Камера + IMU"; enabled: localisation.view.available && controls.view.manual && !controls.view.pending; onClicked: localisation.startCamera() }
        Button { objectName: "localisationRefresh"; text: "Обновить"; enabled: localisation.view.available && !localisation.view.pending; onClicked: localisation.refresh() }
        CheckBox { text: "Обновлять 2 раза/с"; enabled: localisation.view.available; checked: localisation.view.watching; onToggled: localisation.watch(checked) }
    }
    Label { objectName: "localisationNotice"; text: localisation.view.notice; wrapMode: Text.Wrap; Layout.fillWidth: true }
    RowLayout {
        Label { text: "Старт X, м" }
        TextField { id: priorX; objectName: "localisationPriorX"; text: "0"; Layout.preferredWidth: 65; selectByMouse: true }
        Label { text: "Y, м" }
        TextField { id: priorY; objectName: "localisationPriorY"; text: "0"; Layout.preferredWidth: 65; selectByMouse: true }
        Label { text: "Yaw, °" }
        TextField { id: priorYaw; objectName: "localisationPriorYaw"; text: "0"; Layout.preferredWidth: 65; selectByMouse: true }
    }
    RowLayout {
        Button {
            objectName: "localisationStart"
            text: "Запустить с этой позой"
            enabled: localisation.view.available && !localisation.view.running && controls.view.manual && !controls.view.pending
            onClicked: localisation.start(Number(priorX.text.replace(",", ".")), Number(priorY.text.replace(",", ".")), Number(priorYaw.text.replace(",", ".")))
        }
        Button { objectName: "localisationStop"; text: "Остановить локализацию"; enabled: localisation.view.available && controls.view.owns && !controls.view.pending; onClicked: localisation.stop() }
    }
    Label { objectName: "localisationStatus"; text: localisation.view.status; font.bold: true; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Label { text: localisation.view.error; visible: text.length > 0; color: "#b03030"; Layout.fillWidth: true; wrapMode: Text.Wrap }
    Canvas {
        id: map
        objectName: "localisationMap"
        Layout.fillWidth: true; Layout.preferredHeight: 300; Layout.minimumHeight: 220
        property var data: localisation.view
        onDataChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            let c=getContext("2d"); c.reset(); c.fillStyle="#20282a"; c.fillRect(0,0,width,height)
            let g=data.geometry
            c.fillStyle="white"; c.font="13px sans-serif"
            if (!g.length) { c.fillText("Карта появится после запуска локализации",15,30); return }
            let ppm=Math.min((width-50)/g.carpet_width,(height-50)/g.carpet_length)
            function px(y) { return width/2-y*ppm }
            function py(x) { return height/2-x*ppm }
            c.fillStyle="#267447"; c.fillRect(px(g.carpet_width/2),py(g.carpet_length/2),g.carpet_width*ppm,g.carpet_length*ppm)
            c.strokeStyle="white"; c.lineWidth=Math.max(1,g.paint_width*ppm)
            c.strokeRect(px(g.width/2),py(g.length/2),g.width*ppm,g.length*ppm)
            c.beginPath(); c.moveTo(px(g.width/2),py(0)); c.lineTo(px(-g.width/2),py(0)); c.stroke()
            c.beginPath(); c.arc(px(0),py(0),g.circle_diameter*ppm/2,0,Math.PI*2); c.stroke()
            let p=data.pose
            if(p.length===3) {
                c.strokeStyle="#ffad42"; c.fillStyle="#ffad42"; c.lineWidth=3
                c.beginPath(); c.arc(px(p[1]),py(p[0]),7,0,Math.PI*2); c.fill()
                c.beginPath(); c.moveTo(px(p[1]),py(p[0])); c.lineTo(px(p[1]+.25*Math.sin(p[2])),py(p[0]+.25*Math.cos(p[2]))); c.stroke()
            }
            c.fillStyle="white"; c.fillText("+X ↑   +Y ←   "+g.length+" × "+g.width+" м",8,18)
            c.fillText("Оранжевый: диагностический кандидат",8,height-8)
        }
    }
    Label {
        Layout.fillWidth: true; wrapMode: Text.Wrap
        text: {
            let v=localisation.view, r=v.result, p=v.pose
            let pose=p.length===3 ? "X "+p[0].toFixed(2)+" м; Y "+p[1].toFixed(2)+" м; yaw "+(p[2]*180/Math.PI).toFixed(1)+"°\n" : ""
            return pose+"Возраст: "+(v.ageMs ?? "—")+" мс; кадр: "+(r.frame_sequence ?? "—")+
                "; отрезков: "+(r.lines ?? "—")+"; круг: "+(r.circle ? "да" : "нет")+
                "\nСовпадение: "+({matched:"согласовано",weak:"слабое",ambiguous:"неоднозначно"}[r.fit_state] || "нет оценки")+
                "; доля совпавших: "+(r.inlier_fraction===undefined ? "—" : (100*r.inlier_fraction).toFixed(0)+"%")+
                "; остаток: "+(r.median_residual_m===undefined ? "—" : r.median_residual_m.toFixed(3)+" м")+
                "\nКарта запуска: "+(v.configurationId || "—")+". Изменения редактора требуют перезапуска локализации."
        }
    }
    Label { text: "Размер круга и высота камеры требуют проверки. Ворота пока выдаются как цветные кандидаты; они не определяют сторону поля в фильтре."; Layout.fillWidth: true; wrapMode: Text.Wrap }
}
}
