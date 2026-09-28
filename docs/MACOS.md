# Сборка и запуск на macOS

Проверено на Apple Silicon, macOS 26.3.1, Python 3.11, Homebrew Qt 6.7.3 и PySide6 6.7.3.
Это существующий ROKI NG Operator с теми же панелями и протоколом.

Нужны Xcode Command Line Tools, Homebrew Qt с private headers, CMake, Ninja и Python 3.11.
Из корня репозитория:

```sh
scripts/build_macos.sh
scripts/run_macos.sh --robot 192.168.0.120
```

Можно задать QT_PREFIX, PYTHON и BUILD_JOBS при сборке. Версия PySide6 подбирается точно под Qt; Python должен поддерживаться этой версией PySide6.
Исходники KDDockWidgets берутся из приложенного native/sources/KDDockWidgets-v2.4.1.tar.gz.
Все результаты и отдельное Python-окружение находятся в .deps/macos, Linux-плагин не заменяется.

На macOS используется регистрация QML-типов через initFrontend и небольшой C++ bootstrap.
Устаревшая зависимость Qt от AGL исключается локальным CMake hook; системные файлы не редактируются.
Запускайте через run_macos.sh: он выбирает Homebrew Qt целиком, чтобы не смешивать его с Qt внутри wheel PySide6.
Проверка версии до загрузки bootstrap защищает от случайного запуска другим Python-окружением.
При ошибке загрузки GUI поток UDP корректно завершается.

Добавлена настройка IPv4 DF через Darwin IP_DONTFRAG (28, netinet/in.h), без изменения протокола.
Запуск только заполняет адрес: соединение, управление и камера включаются оператором отдельно.
Для видео установите GStreamer и PyGObject в окружение GUI:

```sh
scripts/install_gstreamer_macos.sh
```

Скрипт проверяет настоящий приёмник локальными RTP-потоками H.264 и JPEG до QImage. На macOS выбирайте avdec_h264 / jpegdec и вывод appsink → QImage. Linux VA-декодеры на Mac недоступны. GPU-вывод qml6glsink требует отдельного совместимого Qt-плагина и этой установкой не гарантируется.
Это локальная сборка из исходников, не автономный подписанный .app/DMG.

Проверка: 35 тестов `python -m unittest discover -s tests` прошли с указанным Qt.
Основное окно и встроенные вкладки проверены при живом запуске; подключение к физическому роботу и приём видео в эту проверку не входили.

Оформление на macOS: Fusion и явная светлая палитра QML-окна. Это устраняет конфликт системной тёмной темы с белыми поверхностями KDDockWidgets 2.4. Настройки оформления macOS не меняются.

Установлено и проверено: GStreamer 1.28.7, PyGObject 3.58.0 в .deps/macos/venv. Реальный MediaWorker принял локальные RTP H.264 и JPEG и выдал QImage 320×240; 13 тестов видео/настроек прошли. Физическая камера робота в этой проверке не участвовала.
run_macos.sh добавляет Homebrew lib в DYLD_FALLBACK_LIBRARY_PATH для загрузки библиотек, названных в GI typelibs.
