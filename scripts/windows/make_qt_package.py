"""Generate a minimal Qt6 CMake package for the reconstructed Windows SDK.

The package exposes IMPORTED targets for the Qt6 modules bundled with
PySide6. Link-time information comes from import libraries generated out of
the DLL export tables; run-time locations point at the PySide6 directory, so
binaries built against this package load the exact Qt build PySide6 uses.
"""
import pathlib

SDK = str(pathlib.Path(__file__).resolve().parents[2] / ".deps" / "windows" / "sdk").replace(chr(92), "/")
VERSION = "6.11.2"

DEPS = {
    "Core": [],
    "Gui": ["Core"],
    "Widgets": ["Gui"],
    "OpenGL": ["Gui"],
    "OpenGLWidgets": ["OpenGL", "Widgets"],
    "Network": ["Core"],
    "Xml": ["Core"],
    "Concurrent": ["Core"],
    "DBus": ["Core"],
    "Qml": ["Core", "Network"],
    "QmlIntegration": ["Core", "Qml"],
    "QmlMeta": ["Qml"],
    "QmlModels": ["Qml"],
    "QmlWorkerScript": ["Qml"],
    "QmlLocalStorage": ["Qml"],
    "Quick": ["Gui", "Qml", "QmlModels", "OpenGL"],
    "QuickTemplates2": ["Quick", "Gui"],
    "QuickControls2": ["QuickTemplates2", "Quick", "Gui"],
    "QuickControls2Impl": ["QuickControls2"],
    "QuickLayouts": ["Quick"],
    "QuickShapes": ["Quick", "QuickControls2"],
    "QuickWidgets": ["Quick", "Widgets"],
    "QuickDialogs2": ["Quick", "QuickControls2"],
    "QuickEffects": ["Quick"],
}

PRIVATE_EXTRA = {
    "CorePrivate": ("Core", ["Core"]),
    "GuiPrivate": ("Gui", ["Gui", "CorePrivate"]),
    "WidgetsPrivate": ("Widgets", ["Widgets", "GuiPrivate", "CorePrivate"]),
    "QmlPrivate": ("Qml", ["Qml", "GuiPrivate", "CorePrivate"]),
    "QuickPrivate": ("Quick", ["Quick", "QmlPrivate", "GuiPrivate", "CorePrivate"]),
    "QuickTemplates2Private": ("QuickTemplates2", ["QuickTemplates2", "QuickPrivate"]),
    "QuickControls2Private": ("QuickControls2", ["QuickControls2", "QuickPrivate"]),
    "QuickControls2ImplPrivate": ("QuickControls2Impl", ["QuickControls2Impl", "QuickControls2Private"]),
}

QT6_CONFIG = r"""# Reconstructed Qt6 package for the ROKI operator Windows build.
set(Qt6_VERSION "@VERSION@")
set(QT_VERSION "@VERSION@")
set(QT_VERSION_MAJOR 6)
set(QT_VERSION_MINOR 11)
set(QT_VERSION_PATCH 2)

if(NOT TARGET Qt6::moc)
    add_executable(Qt6::moc IMPORTED)
    set_target_properties(Qt6::moc PROPERTIES IMPORTED_LOCATION "@SDK@/bin/moc.exe")
endif()
if(NOT TARGET Qt6::rcc)
    add_executable(Qt6::rcc IMPORTED)
    set_target_properties(Qt6::rcc PROPERTIES IMPORTED_LOCATION "@SDK@/bin/rcc.exe")
endif()
if(EXISTS "@SDK@/bin/qtpaths.exe" AND NOT TARGET Qt6::qtpaths)
    add_executable(Qt6::qtpaths IMPORTED)
    set_target_properties(Qt6::qtpaths PROPERTIES IMPORTED_LOCATION "@SDK@/bin/qtpaths.exe")
endif()
set(QT_MOC_EXECUTABLE "@SDK@/bin/moc.exe" CACHE FILEPATH "moc executable" FORCE)
set(QT_RCC_EXECUTABLE "@SDK@/bin/rcc.exe" CACHE FILEPATH "rcc executable" FORCE)

set(Qt6_COMPILED_WITH_SANITIZER_OPTIONS FALSE)
set(Qt6_INSTALLED_LIBS_PER_CONFIG TRUE)

# The reconstructed SDK defines every staged module up front so that
# transitive INTERFACE_LINK_LIBRARIES references always resolve.
set(_roki_all_modules Core Gui Widgets OpenGL OpenGLWidgets Network Xml
    Concurrent DBus Qml QmlIntegration QmlMeta QmlModels QmlWorkerScript QmlLocalStorage
    QmlXmlListModel Quick QuickTemplates2 QuickControls2 QuickControls2Impl
    QuickLayouts QuickShapes QuickWidgets QuickDialogs2 QuickEffects)
foreach(_comp IN LISTS _roki_all_modules)
    include("@SDK@/lib/cmake/Qt6/Qt6${_comp}/Qt6${_comp}Config.cmake" OPTIONAL)
    set(Qt6${_comp}_FOUND TRUE)
endforeach()
foreach(_comp IN LISTS _roki_all_modules)
    include("@SDK@/lib/cmake/Qt6/Qt6${_comp}Private/Qt6${_comp}PrivateConfig.cmake" OPTIONAL)
endforeach()

foreach(_comp IN LISTS Qt6_FIND_COMPONENTS)
    if(_comp STREQUAL "BuildInternals" OR _comp STREQUAL "BuildInternalsPrivate")
        set(Qt6${_comp}_FOUND TRUE)
        continue()
    endif()
    if(NOT Qt6${_comp}_FOUND)
        if(Qt6_FIND_REQUIRED_${_comp})
            set(Qt6_NOT_FOUND_MESSAGE "Component ${_comp} is not available in the reconstructed SDK")
        endif()
    endif()
endforeach()
if(NOT DEFINED Qt6Core_VERSION)
    set(Qt6Core_VERSION "@VERSION@")
endif()
set(Qt6Core_VERSION_MAJOR 6)
set(Qt6Core_VERSION_MINOR 11)
set(Qt6Core_VERSION_PATCH 2)
"""

CONFIG_VERSION = r"""set(PACKAGE_VERSION "@VERSION@")
if(PACKAGE_VERSION VERSION_LESS PACKAGE_FIND_VERSION)
    set(PACKAGE_VERSION_COMPATIBLE FALSE)
else()
    set(PACKAGE_VERSION_COMPATIBLE TRUE)
    if(PACKAGE_FIND_VERSION STREQUAL PACKAGE_VERSION)
        set(PACKAGE_VERSION_EXACT TRUE)
    endif()
endif()
"""

MODULE_CONFIG = r"""# Reconstructed Qt6 module @M@
include_guard(GLOBAL)
if(NOT TARGET Qt6::Core)
    include("@SDK@/lib/cmake/Qt6/Qt6Config.cmake" OPTIONAL)
endif()
set(Qt6@M@_VERSION "@VERSION@")
if(NOT TARGET Qt6::@M@)
    add_library(Qt6::@M@ SHARED IMPORTED)
    set_target_properties(Qt6::@M@ PROPERTIES
        IMPORTED_IMPLIB "@SDK@/lib/Qt6@M@.lib"
        IMPORTED_LOCATION "@PYSIDE@/Qt6@M@.dll"
        INTERFACE_INCLUDE_DIRECTORIES "@SDK@/include;@SDK@/include/Qt@M@;@SDK@/include/Qt@M@/@VERSION@;@SDK@/include/Qt@M@/@VERSION@/Qt@M@"
        INTERFACE_COMPILE_DEFINITIONS "$<$<NOT:$<CONFIG:Debug>>:QT_NO_DEBUG>;QT5_NULL_STRINGS=0;QT_@MU@_LIB;QT_DLL"
        INTERFACE_COMPILE_OPTIONS "$<$<COMPILE_LANGUAGE:CXX>:/Zc:__cplusplus;/permissive->"
        INTERFACE_LINK_LIBRARIES "@DEPS@"
    )
    set(Qt6@M@_LIBRARIES Qt6::@M@)
endif()
"""

PRIVATE_CONFIG = r"""# Reconstructed Qt6 private module @P@
include_guard(GLOBAL)
if(NOT TARGET Qt6::Core)
    include("@SDK@/lib/cmake/Qt6/Qt6Config.cmake" OPTIONAL)
endif()
if(NOT TARGET Qt6::@P@)
    add_library(Qt6::@P@ INTERFACE IMPORTED)
    set_target_properties(Qt6::@P@ PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "@SDK@/include;@SDK@/include/Qt@M@;@SDK@/include/Qt@M@/@VERSION@;@SDK@/include/Qt@M@/@VERSION@/Qt@M@"
        INTERFACE_LINK_LIBRARIES "@DEPS@"
    )
    set_property(TARGET Qt6::@P@ APPEND PROPERTY
        INTERFACE_COMPILE_DEFINITIONS "QT_@MU@_LIB")
endif()
"""


def main():
    import PySide6

    pyside = str(pathlib.Path(PySide6.__file__).resolve().parent).replace(chr(92), "/")
    cmake_root = pathlib.Path(SDK) / "lib" / "cmake" / "Qt6"
    cmake_root.mkdir(parents=True, exist_ok=True)

    (cmake_root / "Qt6Config.cmake").write_text(
        QT6_CONFIG.replace("@VERSION@", VERSION).replace("@SDK@", SDK))
    (cmake_root / "Qt6ConfigVersion.cmake").write_text(
        CONFIG_VERSION.replace("@VERSION@", VERSION))

    for mod, deps in DEPS.items():
        dep_str = ";".join("Qt6::" + x for x in deps)
        text = (MODULE_CONFIG.replace("@M@", mod)
                .replace("@MU@", mod.upper())
                .replace("@DEPS@", dep_str)
                .replace("@SDK@", SDK)
                .replace("@PYSIDE@", pyside)
                .replace("@VERSION@", VERSION))
        for d in (cmake_root / ("Qt6" + mod),
                  pathlib.Path(SDK) / "lib" / "cmake" / ("Qt6" + mod)):
            d.mkdir(parents=True, exist_ok=True)
            (d / ("Qt6" + mod + "Config.cmake")).write_text(text)

    for priv, (mod, deps) in PRIVATE_EXTRA.items():
        dep_str = ";".join("Qt6::" + x for x in deps)
        text = (PRIVATE_CONFIG.replace("@P@", priv)
                .replace("@M@", mod)
                .replace("@MU@", mod.upper())
                .replace("@DEPS@", dep_str)
                .replace("@SDK@", SDK)
                .replace("@VERSION@", VERSION))
        for d in (cmake_root / ("Qt6" + priv),
                  pathlib.Path(SDK) / "lib" / "cmake" / ("Qt6" + priv)):
            d.mkdir(parents=True, exist_ok=True)
            (d / ("Qt6" + priv + "Config.cmake")).write_text(text)

    print("Qt6 package written to", cmake_root)


if __name__ == "__main__":
    main()
