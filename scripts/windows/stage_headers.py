"""Stage Qt module headers (qtbase + qtdeclarative) into the reconstructed SDK.

Uses the syncqt tool built from qtbase sources. Generates public forwarding
headers (include/<Module>) and copies real headers into the versioned layout
(include/<Module>/6.11.2/<Module>), then adds the private/ forwarding layer
used by <private/foo_p.h> includes. Generated headers (qconfig.h, *exports*.h)
are copied from the qtbase build tree.
"""
import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2] / ".deps" / "windows"
SRC_BASE = ROOT / "src" / "qtbase-everywhere-src-6.11.2"
SRC_DECL = ROOT / "src" / "qtdeclarative-everywhere-src-6.11.2"
BUILD_BASE = ROOT / "build-qtbase"
SDK = ROOT / "sdk"
SYNCQT = BUILD_BASE / "bin" / "syncqt.exe"
VERSION = "6.11.2"

QTBASE_MODULES = [
    ("QtCore", "src/corelib"),
    ("QtGui", "src/gui"),
    ("QtWidgets", "src/widgets"),
    ("QtNetwork", "src/network"),
    ("QtXml", "src/xml"),
    ("QtConcurrent", "src/concurrent"),
    ("QtDBus", "src/dbus"),
    ("QtOpenGL", "src/opengl"),
    ("QtOpenGLWidgets", "src/openglwidgets"),
    ("QtPrintSupport", "src/printsupport"),
    ("QtSql", "src/sql"),
    ("QtTest", "src/testlib"),
]

DECL_MODULES = [
    ("QtQml", "src/qml"),
    ("QtQmlIntegration", "src/qmlintegration"),
    ("QtQmlMeta", "src/qmlmeta"),
    ("QtQmlModels", "src/qmlmodels"),
    ("QtQmlWorkerScript", "src/qmlworkerscript"),
    ("QtQmlLocalStorage", "src/qmllocalstorage"),
    ("QtQmlXmlListModel", "src/qmlxmllistmodel"),
    ("QtQuick", "src/quick"),
    ("QtQuickTemplates2", "src/quicktemplates"),
    ("QtQuickControls2", "src/quickcontrols"),
    ("QtQuickControls2Impl", "src/quickcontrolsimpl"),
    ("QtQuickLayouts", "src/quicklayouts"),
    ("QtQuickShapes", "src/quickshapes"),
    ("QtQuickWidgets", "src/quickwidgets"),
    ("QtQuickDialogs2", "src/quickdialogs"),
    ("QtQuickEffects", "src/effects"),
    ("QtLabsQmlModels", "src/labs/qmlmodels"),
    ("QtLabsAnimation", "src/labs/animation"),
    ("QtLabsFolderListModel", "src/labs/folderlistmodel"),
    ("QtLabsSettings", "src/labs/settings"),
    ("QtLabsSharedImage", "src/labs/sharedimage"),
    ("QtLabsWavefrontMesh", "src/labs/wavefrontmesh"),
    ("QtLabsPlatform", "src/labs/platform"),
]

KNOWN_MODULES = [m for m, _ in QTBASE_MODULES] + [m for m, _ in DECL_MODULES]


def collect_headers(module_dir):
    headers = []
    for path in sorted(module_dir.rglob("*.h")):
        parts = set(p.lower() for p in path.parts)
        if "3rdparty" in parts or "tests" in parts or "doc" in parts:
            continue
        if ".syncqt_staging" in parts:
            continue
        # QPA headers (qplatform*) are only staged by full Qt builds with a
        # dedicated qpa include dir; the reconstructed SDK does not need them.
        if path.name.startswith("qplatform"):
            continue
        headers.append(path)
    return headers


def stage(module, module_dir):
    if not module_dir.is_dir():
        print("SKIP %s (%s missing)" % (module, module_dir))
        return True
    headers = collect_headers(module_dir)
    if not headers:
        print("SKIP %s (no headers)" % module)
        return True
    include_dir = SDK / "include" / module
    versioned_dir = SDK / "include" / module / VERSION / module
    binary_dir = ROOT / "build-syncqt" / module
    staging_dir = binary_dir / "staging"
    binary_dir.mkdir(parents=True, exist_ok=True)
    versioned_dir.mkdir(parents=True, exist_ok=True)
    rsp = binary_dir / "syncqt_args.txt"
    args = [
        "-module", module,
        "-sourceDir", str(module_dir),
        "-binaryDir", str(binary_dir),
        "-privateHeadersFilter", r".*_p\.h$",
        "-includeDir", str(include_dir),
        "-privateIncludeDir", str(versioned_dir),
        "-qpaIncludeDir", str(versioned_dir),
        "-rhiIncludeDir", str(versioned_dir),
        "-ssgIncludeDir", str(versioned_dir),
        "-stagingDir", str(staging_dir),
        "-knownModules", *KNOWN_MODULES,
        "-copy",
        "-headers", *[str(h) for h in headers],
    ]
    rsp.write_text("\n".join(args) + "\n", encoding="ascii")
    proc = subprocess.run([str(SYNCQT), "@" + str(rsp)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        print("FAIL %s\n%s\n%s" % (module, proc.stdout[-1500:], proc.stderr[-1500:]))
        return False
    print("OK %s (%d headers)" % (module, len(headers)))
    return True


def add_private_forwarding(module):
    versioned_dir = SDK / "include" / module / VERSION / module
    if not versioned_dir.is_dir():
        return 0
    private_dir = versioned_dir / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for header in sorted(versioned_dir.glob("*_p.h")):
        fwd = private_dir / header.name
        fwd.write_text('#include "../%s" // IWYU pragma: export\n' % header.name,
                       encoding="ascii")
        count += 1
    return count


def copy_generated_headers():
    """Copy configure-generated headers from the qtbase build tree."""
    copied = []
    for module, _ in QTBASE_MODULES:
        build_include = BUILD_BASE / "include" / module
        sdk_include = SDK / "include" / module
        sdk_versioned = sdk_include / VERSION / module
        if not build_include.is_dir():
            continue
        for extra in build_include.glob("*.h"):
            if extra.name.endswith("Depends"):
                continue
            for dest in (sdk_include, sdk_versioned):
                if not (dest / extra.name).exists():
                    shutil.copy2(extra, dest / extra.name)
                    copied.append("%s/%s" % (module, extra.name))
    return copied


def main():
    failures = []
    for module, rel in QTBASE_MODULES:
        if not stage(module, SRC_BASE / rel):
            failures.append(module)
    for module, rel in DECL_MODULES:
        if not stage(module, SRC_DECL / rel):
            failures.append(module)
    if failures:
        print("FAILED modules:", ", ".join(failures))
        return 1
    for module, _ in QTBASE_MODULES + DECL_MODULES:
        add_private_forwarding(module)
    copied = copy_generated_headers()
    print("generated headers copied:", len(copied))
    for item in copied[:20]:
        print("  ", item)
    print("HEADERS_STAGING_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
