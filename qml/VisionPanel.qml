import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    property var kddockwidgets_min_size:Qt.size(600,450)
    contentWidth:availableWidth
    clip:true
    property var names:({orange_ball:"Оранжевый мяч",green_field:"Зелёное поле",white_marking:"Белая разметка",blue_posts:"Синие стойки",yellow_posts:"Жёлтые стойки",white_posts:"Белые стойки"})
    property var labels:({l_min:"L минимум",l_max:"L максимум",a_min:"a минимум",a_max:"a максимум",b_min:"b минимум",b_max:"b максимум",pixels_min:"Минимум пикселей",box_area_min:"Минимум площади рамки",
        "camera.exposure_us":"Выдержка, мкс","camera.analogue_gain":"Аналоговое усиление","camera.ae_enabled":"Автоэкспозиция","camera.awb_enabled":"Автобаланс белого","camera.white_balance.red_gain":"Красный gain","camera.white_balance.blue_gain":"Синий gain"})
    onVisibleChanged:visionTuning.watch(visible && watching.checked)
    Component.onDestruction:visionTuning.watch(false)
    ColumnLayout {
        width:root.availableWidth
        Flow {
            Layout.fillWidth:true;spacing:6
            Button {text:"Загрузить настройки";enabled:backend.view.connected && !visionTuning.view.busy;onClicked:visionTuning.refresh()}
            Button {text:"Статус камеры/детектора";enabled:backend.view.connected && !visionTuning.view.busy;onClicked:visionTuning.status()}
            CheckBox {id:watching;text:"Обновлять статус";onToggled:visionTuning.watch(checked && root.visible)}
        }
        Label {text:visionTuning.view.notice;Layout.fillWidth:true;wrapMode:Text.Wrap}
        Label {text:controls.view.error;visible:text!=="";Layout.fillWidth:true;wrapMode:Text.Wrap}
        Flow {
            Layout.fillWidth:true;spacing:6
            Button {text:"Запустить runtime-камеру";enabled:controls.view.manual && !controls.view.pending;onClicked:visionTuning.action("camera.start")}
            Button {text:"Остановить камеру";enabled:controls.view.owns && !controls.view.pending;onClicked:visionTuning.action("camera.stop")}
            Label {text:"Калибровочный захват без IMU; видео запускается отдельно, источник runtime.";width:350;wrapMode:Text.Wrap}
        }
        TabBar {id:tabs;objectName:"tuningTabs";Layout.fillWidth:true;TabButton {text:"Цвета и детекция"} TabButton {text:"Камера"} }
        ColumnLayout {
            visible:tabs.currentIndex===0
            Layout.fillWidth:true
            ComboBox {
                id:profile
                enabled:!visionTuning.view.busy
                Layout.fillWidth:true
                model:visionTuning.view.profiles.map(k => ({key:k,label:root.names[k] || k}))
                textRole:"label"
                currentIndex:visionTuning.view.profiles.indexOf(visionTuning.view.profile)
                onActivated:visionTuning.select(visionTuning.view.profiles[currentIndex])
            }
            RowLayout {
                Layout.fillWidth:true
                Button {text:"Взять кадр для настройки";onClicked:visionTuning.snapshot()}
                Label {text:"Допуск пипетки"}
                SpinBox {id:tolerance;from:0;to:30;value:8;editable:true}
            }
            Label {text:visionTuning.view.sourceLabel;Layout.fillWidth:true;wrapMode:Text.Wrap}
            RowLayout {
                Layout.fillWidth:true
                Image {
                    id:previewSource
                    objectName:"tuningSource"
                    Layout.fillWidth:true;Layout.preferredHeight:230
                    fillMode:Image.PreserveAspectFit;cache:false
                    source:visionTuning.view.hasImage ? "image://tuning/source/"+visionTuning.view.serial : ""
                    MouseArea {
                        anchors.fill:parent
                        onClicked:mouse => {
                            let u=(mouse.x-(previewSource.width-previewSource.paintedWidth)/2)/previewSource.paintedWidth
                            let v=(mouse.y-(previewSource.height-previewSource.paintedHeight)/2)/previewSource.paintedHeight
                            visionTuning.pick(u,v,tolerance.value)
                        }
                    }
                }
                Image {
                    objectName:"tuningMask"
                    Layout.fillWidth:true;Layout.preferredHeight:230
                    fillMode:Image.PreserveAspectFit;cache:false
                    source:visionTuning.view.hasImage ? "image://tuning/mask/"+visionTuning.view.serial : ""
                }
            }
            Label {text:"Слева — снимок (клик: пипетка), справа — локальная LAB-маска. Выбрано пикселей: "+visionTuning.view.pixels+". Маска на декодированном кадре — приблизительный preview, не результат детектора робота.";Layout.fillWidth:true;wrapMode:Text.Wrap}
            Repeater {
                model:visionTuning.labKeys
                RowLayout {
                    id:colourRow
                    required property string modelData
                    property var entry:({key:modelData,meta:visionTuning.view.metas[modelData] || {},value:visionTuning.view.values[modelData]})
                    Layout.fillWidth:true
                    property string suffix:modelData.split('.').pop()
                    Label {text:root.labels[colourRow.suffix] || colourRow.suffix;Layout.preferredWidth:160}
                    Slider {
                        visible:colourRow.suffix.startsWith('l_') || colourRow.suffix.startsWith('a_') || colourRow.suffix.startsWith('b_')
                        Layout.fillWidth:true
                        from:colourRow.entry.meta.min ?? 0;to:colourRow.entry.meta.max ?? 100;stepSize:1
                        value:colourRow.entry.value ?? from
                        onMoved:visionTuning.edit(colourRow.modelData,Math.round(value))
                    }
                    ValueEditor {
                        Layout.preferredWidth:95
                        meta:colourRow.entry.meta;initialValue:colourRow.entry.value
                        onEdited:value => visionTuning.edit(colourRow.modelData,value)
                    }
                }
            }
            Flow {
                Layout.fillWidth:true;spacing:6
                Button {text:"Стандартный фильтр";enabled:!visionTuning.view.busy && profile.count>0;onClicked:visionTuning.defaults("lab")}
                Button {text:"Сохранить фильтр";enabled:controls.view.owns && !controls.view.pending && !visionTuning.view.busy;onClicked:visionTuning.save("lab")}
                Button {text:"Запустить детектор на роботе";enabled:controls.view.manual && !controls.view.pending && profile.count>0;onClicked:visionTuning.action("detection.start")}
                Button {text:"Остановить детектор";enabled:controls.view.owns && !controls.view.pending;onClicked:visionTuning.action("detection.stop")}
            }
            Label {text:"Детектор робота (сохранённые параметры, свой номер кадра):";font.bold:true}
            Label {
                property var result:visionTuning.view.detector.result
                text:result ? "Кадр "+result.frame_sequence+" · "+(root.names[result.profile] || result.profile)+" · областей: "+result.total_blobs+" · возраст: "+visionTuning.view.detector.age_ms+" мс" : "Результат ещё не получен. Запустите детектор и запросите статус."
                Layout.fillWidth:true;wrapMode:Text.Wrap
            }
            RawDetails {text:JSON.stringify(visionTuning.view.detector,null,2);Layout.fillWidth:true}
        }
        ColumnLayout {
            visible:tabs.currentIndex===1
            Layout.fillWidth:true
            Repeater {
                model:visionTuning.cameraKeys
                RowLayout {
                    id:cameraRow
                    required property string modelData
                    property var entry:({meta:visionTuning.view.metas[modelData] || {},value:visionTuning.view.values[modelData]})
                    Layout.fillWidth:true
                    Label {text:root.labels[cameraRow.modelData] || cameraRow.modelData;Layout.preferredWidth:180}
                    ValueEditor {Layout.fillWidth:true;meta:cameraRow.entry.meta;initialValue:cameraRow.entry.value;onEdited:value => visionTuning.edit(cameraRow.modelData,value)}
                }
            }
            Label {text:"Ручные значения при включённой автоматике сохраняются, но не являются её измеренным результатом. Изменения применяются после сохранения без перезапуска runtime-камеры.";Layout.fillWidth:true;wrapMode:Text.Wrap}
            Flow {
                Layout.fillWidth:true;spacing:6
                Button {text:"Стандартная камера";enabled:!visionTuning.view.busy && visionTuning.view.cameraRows.length>0;onClicked:visionTuning.defaults("camera")}
                Button {text:"Сохранить камеру";enabled:controls.view.owns && !controls.view.pending && !visionTuning.view.busy;onClicked:visionTuning.save("camera")}
                Button {text:"Зафиксировать экспозицию";enabled:controls.view.owns && !controls.view.pending;onClicked:visionTuning.freeze("exposure")}
                Button {text:"Зафиксировать баланс белого";enabled:controls.view.owns && !controls.view.pending;onClicked:visionTuning.freeze("white_balance")}
            }
            Label {text:"Фактические значения из метаданных камеры:";font.bold:true}
            Label {
                property var measured:visionTuning.view.camera.measured_controls
                text:measured ? "Кадр "+measured.sequence+" · возраст: "+visionTuning.view.camera.measured_age_ms+" мс\nВыдержка: "+(measured.exposure_us ?? "нет данных")+" мкс · gain: "+(measured.gain ?? "нет данных")+"\nWB: "+JSON.stringify(measured.colour_gains) : "Метаданные ещё не получены. Запросите статус работающей runtime-камеры."
                Layout.fillWidth:true;wrapMode:Text.Wrap
            }
            RawDetails {text:JSON.stringify(visionTuning.view.camera,null,2);Layout.fillWidth:true}
        }
        Button {text:"Отменить все черновики";enabled:visionTuning.view.dirty;onClicked:visionTuning.discard()}
    }
}
