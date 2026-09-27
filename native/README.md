# Готовая нативная зависимость

`qml/com/kdab/dockwidgets/` содержит KDDockWidgets v2.4.1: QML-плагин,
его общую библиотеку, симлинки SONAME и QML-файлы. Приложение само добавляет
этот каталог импорта; устанавливать файлы в `/usr` не нужно.

## Совместимость

- Архитектура: Linux x86_64, не ARM и не Windows.
- Проверенная среда: системные Qt/PySide6 6.11.2, glibc 2.44.
- Сама библиотека требует символы до GLIBC_2.38 и GLIBCXX_3.4.32 включительно.
  Это нижняя граница только для этих файлов, не гарантия для всех зависимостей Qt.
- Qt Quick использует private API: другую версию Qt нельзя считать совместимой.
  Смешивание системного Qt с Qt из pip-wheel отдельно не проверялось.
- RUNPATH обеих библиотек: `$ORIGIN`. Системные Qt и остальные зависимости
  не включены. Проверить разрешение библиотек можно через
  `ldd native/qml/com/kdab/dockwidgets/libkddockwidgetsplugin.so`.

Для другой среды пересоберите зависимость через
`bash scripts/build_kddockwidgets.sh`. Полный build-каталог не распространяется.
Готовый модуль занимает около 4,2 МиБ без архива исходников.

## Исходники и лицензии

Исходный проект: https://github.com/KDAB/KDDockWidgets

Точная ревизия: `c1d28d25ef5ba077915bcb2b6fa9e14df2a361f8` (v2.4.1).
Архив [sources/KDDockWidgets-v2.4.1.tar.gz](sources/KDDockWidgets-v2.4.1.tar.gz)
содержит исходники этой ревизии без `.git` и без сборочных результатов.
Изменения для Wayland: [патч](../scripts/patches/kddw-wayland-drop.patch).
Рецепт и параметры сборки: [build_kddockwidgets.sh](../scripts/build_kddockwidgets.sh).

Для получения именно изменённых исходников распакуйте архив и примените патч:

```sh
tar -xzf native/sources/KDDockWidgets-v2.4.1.tar.gz -C /tmp
git -C /tmp/KDDockWidgets apply "$PWD/scripts/patches/kddw-wayland-drop.patch"
```

KDDockWidgets: GPL-2.0-only OR GPL-3.0-only; коммерческая лицензия доступна
от KDAB отдельно. Лицензии и сведения о сторонних компонентах находятся
в [licenses/KDDockWidgets](licenses/KDDockWidgets/) и в архиве исходников.
Qt, PySide6 и GStreamer устанавливаются отдельно и имеют собственные лицензии.
