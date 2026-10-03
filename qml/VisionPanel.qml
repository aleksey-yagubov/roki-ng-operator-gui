import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: root
    property var kddockwidgets_min_size:Qt.size(600,450)
    contentWidth:availableWidth
    clip:true
    property var names:({orange_ball:"Оранжевый мяч",green_field:"Зелёное поле",white_marking:"Белая разметка",blue_posts:"Синие стойки",yellow_posts:"Жёлтые стойки",white_posts:"Белые стойки"})
    property var labels:({l_min:"L минимум",l_max:"L максимум",a_min:"a минимум",a_max:"a максимум",b_min:"b минимум",b_max:"b максимум",pixels_min:"Минимум пикселей",box_area_min:"Минимум площади рамки"})
    property string diagnosticFrame: ""
    function updateDiagnosticFrame() { diagnosticFrame = streams.imageUrl("detection") }
    Connections {
        target: streams
        function onFramesChanged() { root.updateDiagnosticFrame() }
        function onChanged() { root.updateDiagnosticFrame() }
    }
    onVisibleChanged: { visionTuning.watch(visible && watching.checked); if (!visible) visionTuning.live(false) }
    Component.onDestruction: { visionTuning.watch(false); visionTuning.live(false) }
    ColumnLayout {
        width:root.availableWidth
        Flow {
            Layout.fillWidth:true;spacing:6
            Button {text:"Загрузить настройки";enabled:backend.view.connected && !visionTuning.view.busy;onClicked:visionTuning.refresh()}
            Button {text:"Статус детектора";enabled:backend.view.connected && !visionTuning.view.busy;onClicked:visionTuning.status()}
            CheckBox {id:watching;text:"Обновлять статус";checked:visionTuning.view.watching;onToggled:visionTuning.watch(checked && root.visible)}
        }
        SelectableLabel {text:visionTuning.view.notice;Layout.fillWidth:true;wrapMode:Text.Wrap}
        SelectableLabel {text:controls.view.error;visible:text!=="";Layout.fillWidth:true;wrapMode:Text.Wrap}
        Label {text:"Камера и ISP настраиваются в панели «Камера». Видео запрашивается отдельно в «Стримах».";Layout.fillWidth:true;wrapMode:Text.Wrap}
        ComboBox {
            id:previewStream
            objectName:"tuningStream"
            Layout.fillWidth:true
            model:streams.receivers
            textRole:"label"
            currentIndex:model.findIndex(s => s.id === visionTuning.view.previewStream)
            displayText:currentIndex >= 0 ? currentText : "Выберите принимаемый стрим"
            onActivated:visionTuning.selectStream(model[currentIndex].id)
        }
        ColumnLayout {
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
                Button {objectName:"tuningSnapshot";text:"Зафиксировать кадр";onClicked:visionTuning.snapshot()}
                CheckBox {objectName:"tuningLive";text:"Live 5 Гц";checked:visionTuning.view.live;onToggled:visionTuning.live(checked)}
                Label {text:"Допуск пипетки"}
                SpinBox {id:tolerance;from:0;to:30;value:8;editable:true}
            }
            Label {text:visionTuning.view.sourceLabel;Layout.fillWidth:true;wrapMode:Text.Wrap}
            RowLayout {
                Layout.fillWidth:true
                Image {
                    id:previewSource
                    objectName:"tuningSource"
                    Layout.fillWidth:true;Layout.preferredHeight:320
                    fillMode:Image.PreserveAspectFit;cache:false
                    source:visionTuning.view.hasImage ? "image://tuning/source/"+visionTuning.view.serial : ""
                    MouseArea {
                        anchors.fill:parent
                        onPressed:visionTuning.live(false)
                        onClicked:mouse => {
                            let u=(mouse.x-(previewSource.width-previewSource.paintedWidth)/2)/previewSource.paintedWidth
                            let v=(mouse.y-(previewSource.height-previewSource.paintedHeight)/2)/previewSource.paintedHeight
                            visionTuning.pick(u,v,tolerance.value)
                        }
                    }
                }
                Image {
                    objectName:"tuningMask"
                    Layout.fillWidth:true;Layout.preferredHeight:320
                    fillMode:Image.PreserveAspectFit;cache:false
                    source:visionTuning.view.hasImage ? "image://tuning/mask/"+visionTuning.view.serial : ""
                }
            }
            Label {text:"Слева — кадр (нажатие фиксирует кадр для пипетки), справа — локальная LAB-маска. Выбрано пикселей: "+visionTuning.view.pixels+". Маска на декодированном кадре — приблизительный preview, не результат детектора робота.";Layout.fillWidth:true;wrapMode:Text.Wrap}
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
                        objectName: "tuningEditor-" + colourRow.suffix
                        commitOnFinish: true
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
            }
            Label {text:"Площадь: «Минимум пикселей» — размер цветной области, «Минимум площади рамки» — ширина × высота. Введите число, нажмите Enter, затем «Сохранить фильтр».";Layout.fillWidth:true;wrapMode:Text.Wrap}
            Label {text:"Проверка на роботе — сохранённые thresholds, без команд движения";font.bold:true;Layout.fillWidth:true;wrapMode:Text.Wrap}
            SelectableLabel {text:visionTuning.view.detector.error || visionTuning.view.detector.video?.error || "";visible:text.length>0;color:"#b03030";Layout.fillWidth:true;wrapMode:Text.Wrap}
            ComboBox {
                objectName:"tuningDetectorMode"
                model:["LAB: выбранный цвет", "Мяч: игровой алгоритм + IMU"]
                currentIndex:visionTuning.view.detectorMode === "ball" ? 1 : 0
                onActivated:visionTuning.selectDetector(currentIndex === 1 ? "ball" : "colour")
                Layout.fillWidth:true
            }
            Flow {
                Layout.fillWidth:true;spacing:6
                Button {objectName:"tuningDetectorStart";text:"Запустить проверку";enabled:controls.view.owns && (controls.view.manual || (controls.view.mode === "GAME" && visionTuning.view.detectorMode === "colour")) && (visionTuning.view.detectorMode === "ball" || profile.count>0) && !controls.view.pending && !visionTuning.view.detector.running;onClicked:visionTuning.action("detection.start")}
                Button {text:"Остановить проверку";enabled:controls.view.owns && !controls.view.pending;onClicked:visionTuning.action("detection.stop")}
                Button {text:"Обновить список стримов";enabled:backend.view.connected;onClicked:streams.refresh()}
            }
            Label {text:"После запуска в «Стримах» выберите detection → «Смотреть»: видео появится ниже. Маски вычислены на исходном кадре робота; черновик ползунков на них не влияет до сохранения. Для пипетки используйте camera.";Layout.fillWidth:true;wrapMode:Text.Wrap}
            Image {
                objectName:"tuningRobotVideo"
                Layout.fillWidth:true;Layout.preferredHeight:source.toString() !== "" ? 520 : 0
                fillMode:Image.PreserveAspectFit;cache:false;source:root.diagnosticFrame
            }
            Label {
                property var reception: { streams.view; return streams.reception("detection") }
                visible:reception.stalled || false
                text:"Нет новых диагностических кадров — изображение выше устарело. Проверьте статус детектора и камеры."
                color:"#b03030";Layout.fillWidth:true;wrapMode:Text.Wrap
            }
            Label {
                property var result:visionTuning.view.detector.result
                text:result ? "Кадр "+result.frame_sequence+" · "+(visionTuning.view.detector.mode === "ball" ? (result.valid ? "мяч найден: X="+result.x_m.toFixed(3)+", Y="+result.y_m.toFixed(3)+" м" : "мяч не принят: "+result.reason) : (root.names[result.profile] || result.profile)+" · областей: "+result.total_blobs+" · отсев по площади: "+result.area_rejected)+" · возраст: "+visionTuning.view.detector.age_ms+" мс" : "Результат ещё не получен. Запустите детектор и запросите статус."
                Layout.fillWidth:true;wrapMode:Text.Wrap
            }
            Label {text:"Мяч: сверху — исходник с решениями и оранжевая маска; снизу — зелёная и белая опора. selected — выбран; no_field — нет опоры; projection — луч вне калибровки/над горизонтом; range — вне допустимой дальности; area_rejected — отсев по площади. Красные рамки — отклонённые кандидаты. Выбор прекращается на первом подходящем из десяти нижних кандидатов, как в игре.";Layout.fillWidth:true;wrapMode:Text.Wrap}
            Label {text:"Координаты мяча: X вперёд, Y влево относительно направления головы, метры. Нужны синхронизация IMU и профиль камеры. Диагностика не ставит робота в стойку: высота камеры должна соответствовать game.camera_height_m; у расслабленного робота дальность может быть неверной. Линии, круг и ворота проверяются через «Локализацию» и стрим localisation.";Layout.fillWidth:true;wrapMode:Text.Wrap}
            RawDetails {text:JSON.stringify(visionTuning.view.detector,null,2);Layout.fillWidth:true}
        }
        Button {text:"Отменить все черновики";enabled:visionTuning.view.dirty;onClicked:visionTuning.discard()}
    }
}
