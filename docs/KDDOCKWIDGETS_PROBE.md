# Проверка KDDockWidgets из Python

Дата: 2026-09-25. Хост Linux x86-64, compositor labwc/Wayland.

## Среда

| Компонент | Версия |
| --- | --- |
| Python | 3.14 |
| PySide6 и системный Qt | 6.11.2 |
| GStreamer / qml6glsink | 1.28.7 |
| KDDockWidgets | 2.4.1 |
| Исходный commit KDDockWidgets | c1d28d25ef5ba077915bcb2b6fa9e14df2a361f8 |

Сборка: Release, Qt Quick frontend, QML module ON, Python bindings OFF,
examples/tests OFF, spdlog OFF. CMake + Ninja, 8 параллельных задач.
Нативные библиотеки и QML-модуль устанавливаются только в папку проекта.
Исходники KDDockWidgets и системный GStreamer не правились.

## Подтверждённые результаты

- PySide6 загружает `import com.kdab.dockwidgets 2.0` через локальный QML-плагин.
- Python-биндинги KDDockWidgets не нужны для создания панелей в QML.
- Нажатие кнопки в QML вызывает Python Slot, изменённое Python Property видно в QML.
- Клики по кнопкам выносят панель в окно и возвращают назад; состояние isFloating проверяется.
- Скрытие/открытие панели проходит; состояние isOpen проверяется.
- Объединение во вкладки и восстановление раскладки проверены, сохранены скриншоты.
- Окно проверено в размерах 1100x720 и 800x600 без видео; это не исчерпывающий тест всех DPI.
- Неподвижное видео через qml6glsink работает вместе с QML-оверлеем.
- Счётчик rendered увеличивается; в коротком стационарном тесте dropped=0.

Пайплайн теста:

```text
videotestsrc is-live=true pattern=ball
  ! video/x-raw,width=800,height=650,framerate=60/1
  ! glupload ! glcolorconvert ! queue ! qml6glsink
```

Тест не измеряет сетевую задержку, производительность аппаратного декодера или
полный zero-copy путь. Также не проверена серия drag-and-drop жестов мышью:
автоматизация нажимает настоящие QML-кнопки, которые вызывают операции docking.

## Сбой переноса видео

При первом переводе видео в floating-окно процесс завершается SIGABRT:

```text
gst_video_frame_map_id: assertion 'info->finfo->format == meta->format' failed
gstqsg6material.cc:497: GstQSG6Material::setBuffer(GstBuffer*): code should not be reached
```

Перед сбоем регистрируется `videoItem.windowChanged`: старое окно -> null -> новое окно.
Ошибка воспроизведена и с плагином из каталога сборки, и с модулем из `native/qml`.
AA_ShareOpenGLContexts уже включён; сам по себе он этот случай не исправляет.
Sink переводится в READY перед GL-элементами пайплайна, как требует документация.

Вероятная причина по исходникам GStreamer 1.28.7:

1. `Qt6GLVideoItem::updatePaintNode` создаёт новый GstQSG6Material, когда oldNode отсутствует.
2. Новый материал инициализирует пустой GstVideoInfo в конструкторе.
3. Вызов `tex->setCaps()` выполняется только при `priv->caps_change`.
4. При смене окна формат потока не менялся, поэтому новый материал может остаться без caps.
5. Следующий `setBuffer()` пытается сопоставить кадр с неинициализированным форматом и падает.

Это объяснение по коду и месту падения, не доказательство, что один патч устранит
все проблемы переноса: вопросы GL-контекстов и времени жизни ресурсов ещё требуют тестов.

Исходники для проверки:

- [qt6glitem.cc, GStreamer 1.28.7](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gst-plugins-good/ext/qt6/qt6glitem.cc)
- [gstqsg6material.cc, GStreamer 1.28.7](https://github.com/GStreamer/gstreamer/blob/1.28.7/subprojects/gst-plugins-good/ext/qt6/gstqsg6material.cc)
- [Требования qml6glsink к GL-контекстам](https://gstreamer.freedesktop.org/documentation/qml6/qml6glsink.html)

## Вывод для архитектуры

KDDockWidgets подходит для Python/QML и локальной поставки папкой. Но обещать
безопасную миграцию работающего qml6glsink между окнами на проверенной версии нельзя.

Перед интеграцией видео нужно отдельно выбрать и проверить решение: исправление
upstream-плагина или управляемое пересоздание видеоповерхности при смене окна.
Не добавлять обходы в каждую панель. Сессия приёма/декодирования должна принадлежать
медиаслою приложения, а не жизненному циклу dock-панели. Перенос панели не должен
посылать роботу stop/start камеры.

До решения проблемы обычный docking проверяется без видео. Флаг `--video`
предназначен для эксперимента и воспроизведения, а не для рабочего управления роботом.
