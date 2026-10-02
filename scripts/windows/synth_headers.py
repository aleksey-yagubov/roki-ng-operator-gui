"""Synthesize module config/exports headers missing from the reconstructed SDK.

qtbase *-config.h files are copied from the qtbase build tree. For
qtdeclarative (never configured) both <mod>-config.h and <mod>exports.h are
synthesized: config headers carry only an include guard (feature tests then
fall back to their inert defaults) and exports headers define every
Q_*_EXPORT macro referenced by the staged module headers.
"""
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / ".deps" / "windows"
BUILD_BASE = ROOT / "build-qtbase"
SDK = ROOT / "sdk"
VERSION = "6.11.2"

QTBASE_SRC_DIRS = {
    "QtCore": "corelib", "QtGui": "gui", "QtWidgets": "widgets",
    "QtNetwork": "network", "QtXml": "xml", "QtConcurrent": "concurrent",
    "QtDBus": "dbus", "QtOpenGL": "opengl",
    "QtOpenGLWidgets": "openglwidgets", "QtPrintSupport": "printsupport",
    "QtSql": "sql", "QtTest": "testlib",
}

MODULES = [
    "QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtXml", "QtConcurrent",
    "QtDBus", "QtOpenGL", "QtOpenGLWidgets", "QtPrintSupport", "QtSql",
    "QtTest",
    "QtQml", "QtQmlIntegration", "QtQmlMeta", "QtQmlModels", "QtQmlWorkerScript",
    "QtQmlLocalStorage", "QtQmlXmlListModel", "QtQuick", "QtQuickTemplates2",
    "QtQuickControls2", "QtQuickControls2Impl", "QtQuickLayouts",
    "QtQuickShapes", "QtQuickWidgets", "QtQuickDialogs2", "QtQuickEffects",
    "QtLabsQmlModels", "QtLabsAnimation", "QtLabsFolderListModel",
    "QtLabsSettings", "QtLabsSharedImage", "QtLabsWavefrontMesh",
    "QtLabsPlatform",
]

EXPORT_MACRO = re.compile(r"\bQ_[A-Z][A-Z0-9_]*_EXPORT\b")
CONFIG_GUARD = re.compile(r"[^A-Za-z0-9]")


def module_short(module):
    return module[2:]  # QtCore -> Core


def module_prefix(module):
    if module == "QtTest":
        return "qttestlib"
    return module.lower()  # QtCore -> qtcore, QtQuickTemplates2 -> qtquicktemplates2


def copy_qtbase_config_headers():
    copied = []
    for module in QTBASE_SRC_DIRS:
        prefix = module_prefix(module)
        candidates = [
            BUILD_BASE / "src" / QTBASE_SRC_DIRS[module] / ("%s-config.h" % prefix),
            BUILD_BASE / "include" / module / ("%s-config.h" % prefix),
        ]
        src = next((c for c in candidates if c.exists()), None)
        if not src:
            continue
        for dest in (SDK / "include" / module,
                     SDK / "include" / module / VERSION / module):
            target = dest / src.name
            if not target.exists() or target.read_bytes() != src.read_bytes():
                shutil.copy2(src, target)
                copied.append(str(target))
    return copied


QT_FEATURE_USE = re.compile(r"QT_CONFIG\((\w+)\)|\bQT_FEATURE_(\w+)\b")


def copy_qtbase_private_config_headers():
    copied = []
    for module in QTBASE_SRC_DIRS:
        prefix = module_prefix(module)
        candidates = [
            BUILD_BASE / "src" / QTBASE_SRC_DIRS[module] / ("%s-config_p.h" % prefix),
            BUILD_BASE / "include" / module / VERSION / module / "private" / ("%s-config_p.h" % prefix),
        ]
        src = next((c for c in candidates if c.exists()), None)
        if not src:
            continue
        for dest in (SDK / "include" / module / VERSION / module,
                     SDK / "include" / module / VERSION / module / "private"):
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / src.name
            if not target.exists():
                shutil.copy2(src, target)
                copied.append(str(target))
    return copied


def synthesize_config_header(module):
    prefix = module_prefix(module)
    name = "%s-config.h" % prefix
    guard = "QT_%s_CONFIG_H" % CONFIG_GUARD.sub("_", module_short(module)).upper()
    include_dir = SDK / "include" / module
    features = set()
    if include_dir.is_dir():
        for header in include_dir.rglob("*.h"):
            if "exports" in header.name or header.name.endswith("-config.h"):
                continue
            try:
                content = header.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in QT_FEATURE_USE.finditer(content):
                features.add(match.group(1) or match.group(2))
    lines = ["#ifndef %s" % guard, "#define %s" % guard, "",
             "// Synthesized for the reconstructed Windows SDK. Feature values",
             "// follow the official Qt builds (enabled unless already defined).", ""]
    for feature in sorted(features):
        macro = "QT_FEATURE_%s" % feature
        lines.append("#if !defined(%s)" % macro)
        lines.append("#  define %s 1" % macro)
        lines.append("#endif")
    lines.append("")
    lines.append("#endif // %s" % guard)
    text = "\n".join(lines) + "\n"
    written = []
    for dest in (SDK / "include" / module,
                 SDK / "include" / module / VERSION / module):
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / name
        if not target.exists():
            target.write_text(text, encoding="ascii")
            written.append(str(target))
    return written


def synthesize_private_config_header(module):
    prefix = module_prefix(module)
    name = "%s-config_p.h" % prefix
    guard = "QT_%s_CONFIG_P_H" % CONFIG_GUARD.sub("_", module_short(module)).upper()
    versioned_dir = SDK / "include" / module / VERSION / module
    features = set()
    if versioned_dir.is_dir():
        for header in versioned_dir.rglob("*.h"):
            if header.name.endswith(("-config.h", "-config_p.h")) or "exports" in header.name:
                continue
            try:
                content = header.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for match in QT_FEATURE_USE.finditer(content):
                features.add(match.group(1) or match.group(2))
    lines = ["#ifndef %s" % guard, "#define %s" % guard, "",
             "// Synthesized for the reconstructed Windows SDK.", ""]
    for feature in sorted(features):
        macro = "QT_FEATURE_%s" % feature
        lines.append("#if !defined(%s)" % macro)
        lines.append("#  define %s 1" % macro)
        lines.append("#endif")
    lines.append("")
    lines.append("#endif // %s" % guard)
    text = "\n".join(lines) + "\n"
    for dest in (versioned_dir, versioned_dir / "private"):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / name).write_text(text, encoding="ascii")


def synthesize_exports_header(module):
    prefix = module_prefix(module)
    name = "%sexports.h" % prefix
    include_dir = SDK / "include" / module
    macros = set()
    if include_dir.is_dir():
        for header in include_dir.rglob("*.h"):
            try:
                content = header.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if "exports" in header.name:
                continue
            macros.update(EXPORT_MACRO.findall(content))
    macros.discard("Q_DECL_EXPORT")
    macros.discard("Q_DECL_IMPORT")
    guard = "QT_%sEXPORTS_H" % CONFIG_GUARD.sub("_", module_short(module)).upper()
    consumer_mark = "QT_%s_LIB" % module_short(module).upper()
    lines = ["#ifndef %s" % guard, "#define %s" % guard, "",
             "#include <QtCore/qglobal.h>", ""]
    for macro in sorted(macros):
        lines.append("#ifndef %s" % macro)
        lines.append("#  if defined(%s)" % consumer_mark)
        lines.append("#    define %s Q_DECL_IMPORT" % macro)
        lines.append("#  else")
        lines.append("#    define %s Q_DECL_EXPORT" % macro)
        lines.append("#  endif")
        lines.append("#endif")
    lines.append("")
    lines.append("#endif // %s" % guard)
    text = "\n".join(lines) + "\n"
    written = []
    for dest in (include_dir, SDK / "include" / module / VERSION / module):
        dest.mkdir(parents=True, exist_ok=True)
        target = dest / name
        target.write_text(text, encoding="ascii")
        written.append(str(target))
    return written, sorted(macros)


def main():
    copied = copy_qtbase_config_headers()
    copied += copy_qtbase_private_config_headers()
    print("qtbase config headers copied:", len(copied))
    for module in MODULES[12:]:
        prefix = module_prefix(module)
        for stale in (SDK / "include" / module / ("%s-config.h" % prefix),
                      SDK / "include" / module / VERSION / module / ("%s-config.h" % prefix)):
            if stale.exists():
                stale.unlink()
        synthesize_config_header(module)
    for module in MODULES[12:]:
        synthesize_private_config_header(module)
    total_macros = 0
    for module in MODULES[12:]:
        _, macros = synthesize_exports_header(module)
        total_macros += len(macros)
    print("exports macros covered:", total_macros)
    missing = []
    allowed_missing = {
        "qtconcurrent-config.h", "qtdbus-config.h", "qtopengl-config.h",
        "qtopenglwidgets-config.h",
        "qtconcurrent-config_p.h", "qtdbus-config_p.h", "qtopengl-config_p.h",
        "qtopenglwidgets-config_p.h",
    }
    for module in MODULES:
        prefix = module_prefix(module)
        names = ("%s-config.h" % prefix, "%sexports.h" % prefix,
                 "%s-config_p.h" % prefix)
        for name in names:
            if name in allowed_missing:
                continue
            probe = SDK / "include" / module / name
            if name.endswith("-config_p.h"):
                probe = SDK / "include" / module / VERSION / module / "private" / name
            if not probe.exists():
                missing.append("%s/%s" % (module, name))
    if missing:
        print("still missing:", missing)
        return 1
    print("SYNTH_HEADERS_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
