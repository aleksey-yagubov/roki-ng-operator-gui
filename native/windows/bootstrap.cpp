// Register the upstream Qt Quick frontend for Qt versions without its QML plugin.
#include <kddockwidgets/KDDockWidgets.h>
#include <kddockwidgets/qtquick/Platform.h>
#include <QGuiApplication>
#include <QQmlEngine>

extern "C" const char *roki_docking_qt_version() { return QT_VERSION_STR; }

extern "C" int roki_docking_initialize(void *engine)
{
    if (!qGuiApp || !engine)
        return 1;
    try {
        KDDockWidgets::initFrontend(KDDockWidgets::FrontendType::QtQuick);
        KDDockWidgets::QtQuick::Platform::instance()->setQmlEngine(static_cast<QQmlEngine *>(engine));
        return 0;
    } catch (...) {
        return 2;
    }
}
