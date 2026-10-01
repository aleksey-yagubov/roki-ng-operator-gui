import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: scroll
    property var kddockwidgets_min_size: Qt.size(300, 220)
    contentWidth: availableWidth
    clip: true
    ColumnLayout {
        width: scroll.availableWidth
        spacing: 10
        Label { text: "Диагностика клиента"; font.bold: true }
        Label { text: "RTT ответов: " + backend.view.rtt + " мс" }
        Label { text: "Пропуски sequence: " + backend.view.gaps }
        Label { text: "Некорректные пакеты: " + backend.view.invalid }
        Label { text: "Видеоприёмников: " + streams.view.active.length + " · просмотров: " + videoViews.entries.length; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: streams.view.error; visible: text.length > 0; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label { text: "OSD: интеграция отложена"; font.bold: true; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Label {
            text: "Промахи кеша OSD пока не измеряются. При интеграции здесь появятся счётчики: кадр вытеснен, ещё не получен, потеряна привязка sequence. Последняя ошибка будет показывать слой и номер кадра. Молчаливое отбрасывание недопустимо."
            Layout.fillWidth: true
            wrapMode: Text.Wrap
        }
        Label { text: backend.view.notice || "Ошибок команд нет"; Layout.fillWidth: true; wrapMode: Text.WrapAnywhere }
    }
}
