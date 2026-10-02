# Сборка и запуск на Windows

Проверено на Windows 11 (x86_64), Python 3.14, MSVC 14.44 (VS 2022 Build Tools),
PySide6 6.11.2 (Qt из pip-wheel), GStreamer 1.28.7 MSVC, gvsbuild GTK 2026.8.0.
Это тот же ROKI NG Operator с теми же панелями и протоколом, что на Linux.

## Что требуется установить

1. **Visual Studio 2022 Build Tools**, workload VCTools (MSVC, Windows SDK).
   Нужен только на этапе сборки KDDockWidgets; приложению компилятор не нужен.
2. **Python** с пакетами: `pip install PySide6==6.11.2 "msgpack>=1.1,<2" "numpy>=2,<3" cmake ninja`
3. **GStreamer MSVC x64** для видео: `gstreamer-1.0-msvc-x86_64-<ver>.exe` с
   https://gstreamer.freedesktop.org/data/pkg/windows/ — тихая установка `/quiet`.
4. **gvsbuild GTK zip** для PyGObject (`gi`): https://github.com/wingtk/gvsbuild/releases —
   файл `GTK4_Gvsbuild_<ver>_x64.zip`. Распаковывается в `.deps/windows/gtk`.

Шаги 3–4 автоматизированы скриптом:

```bat
scripts\windows\install_video_windows.bat
```

## Сборка зависимости докинга (KDDockWidgets)

Linux-плагин KDDockWidgets из `native/qml` на Windows не работает, а официального
Windows SDK Qt с сайта qt.io здесь не использовать: Qt нужен ровно той сборки, что
внутри pip-колеса PySide6. Поэтому собирается реконструированный SDK из того, что
уже есть на машине: заголовки берутся из исходников Qt 6.11.2 (TUNA-зеркало),
import-библиотеки генерируются из DLL, поставляемых внутри PySide6, host-инструменты
(moc/rcc/syncqt/qtpaths) собираются из исходников qtbase — целиком собирать Qt не нужно.

```bat
scripts\windows\download_qt_sources.bat
python scripts\windows\build_windows.py
```

Результат: `.deps/windows/bootstrap/` (kddockwidgets-qt62.dll + roki_docking_bootstrap.dll).
Приложение само загружает его через ctypes и регистрирует QtQuick-фронтенд
(как на macOS). Несовпадение версии Qt обнаруживается по `.deps/windows/qt-version.txt`.

Приватные символы Qt, которые официальный SDK экспортирует, а сборка Qt внутри
PySide6 — нет, закрыты локальными заглушками `native/windows/qtprivate_pyside_stubs.cpp`
(подмешивается в сборку KDDockWidgets скриптом). Эти символы вызываются только из
inline-кода приватных заголовков; на работу докинга они не влияют.

## Запуск

```bat
scripts\windows\run_windows.bat --robot 172.30.0.1
```

Запуск только заполняет адрес: соединение, управление и камера включаются оператором
отдельно, как на других платформах.

## Видео

PyGObject ставится в системный Python копированием `gi`/`cairo` из
`.deps/windows/gtk/lib/site-packages` (либо этот каталог добавляется в `sys.path`).
Окружение поднимает `operator_gui/gst_windows.py` перед `import gi`:
gvsbuild-вариант GLib загружается первым и становится общим для обоих стеков —
отдельной копии GLib из GStreamer не образуется.

Для H.264 доступны аппаратные декодеры: **d3d11h264dec** (Direct3D 11, работает на
любом GPU с DX11, включая встройку Intel — выбран по умолчанию) и **nvh264dec**
(NVIDIA NVDEC; элемент присутствует только если установлены CUDA-плагины GStreamer).
Программный запасной вариант — avdec_h264. Выбор декодера — в панели «Стримы»,
дополнительные настройки приёмника.

Проверка приёмника локальным RTP-потоком H.264 до QImage (в т.ч. аппаратный декодер):

```bat
python scripts\check_gstreamer.py
```

## Проверка

`python -m unittest discover -s tests` — 114 тестов, зелёные.
`python scripts/test_operator_gui.py` — полная GUI-сюита с фиктивным роботом
(докинг, панели, восстановление раскладки, ручной режим, стримы).

Фикстура `tests/fake_robot.py` на Windows переживает ICMP port unreachable
(WinError 10054), которое на Linux игнорируется само собой.

## Ограничения

- Видео: используется официальный GStreamer MSVC; предупреждение о невозможности
  загрузить плагин `gstpython.dll` безвредно (это gst-python из комплекта, нам он
  не нужен).
- Wayland-патч KDDockWidgets на Windows не применяется (он Linux-specific).
- Плагин gstpython из состава GStreamer не используется; нужен только gi из gvsbuild.
