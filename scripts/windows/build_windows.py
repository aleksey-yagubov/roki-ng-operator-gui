"""Build the Windows docking dependency (KDDockWidgets) end to end.

Steps:
  1. configure qtbase from sources and build host tools (moc/rcc/syncqt/qtpaths)
  2. stage Qt headers (qtbase + qtdeclarative) into the reconstructed SDK
  3. generate MSVC import libraries from the PySide6-bundled Qt DLLs
  4. generate the reconstructed Qt6 CMake package
  5. build KDDockWidgets (QtQuick frontend) and the docking bootstrap DLL

Prerequisites:
  - Visual Studio 2022 Build Tools (VCTools workload)
  - Python with: PySide6==6.11.2, msgpack, numpy, cmake, ninja
  - Qt sources: .deps/windows/src/qtbase-everywhere-src-6.11.2 and
    .deps/windows/src/qtdeclarative-everywhere-src-6.11.2 (download via
    scripts/windows/download_qt_sources.bat)
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
W = REPO / ".deps" / "windows"
SDK = W / "sdk"
VCBAT = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"

MODULES = "build_qtbase_tools stage_headers synth_headers gen_import_libs make_qt_package build_kddw".split()

STUBS_LINE = "# Windows port: stubs for Qt private symbols not exported by the PySide6 Qt build"


def patch_kddw_sources():
    """Apply the Windows stubs to a fresh KDDockWidgets source extraction."""
    src = REPO / ".deps" / "src" / "KDDockWidgets" / "src"
    stubs = src / "qtprivate_pyside_stubs.cpp"
    if not stubs.exists():
        shutil.copy2(REPO / "native" / "windows" / "qtprivate_pyside_stubs.cpp", stubs)
    cmake = src / "CMakeLists.txt"
    text = cmake.read_text(encoding="utf-8")
    if "qtprivate_pyside_stubs.cpp" not in text:
        with cmake.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write("\n%s\ntarget_sources(kddockwidgets PRIVATE qtprivate_pyside_stubs.cpp)\n"
                     % STUBS_LINE)


def log(*args):
    print("[build_windows]", *args, flush=True)


def run_bat(bat, name):
    log("=== %s" % name)
    proc = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr)[-2000:]
    if proc.returncode != 0:
        log("%s FAILED (exit %s):\n%s" % (name, proc.returncode, tail))
        sys.exit(1)
    log("%s OK" % name)


def run_py(script, name):
    log("=== %s" % name)
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    tail = (proc.stdout + proc.stderr)[-2000:]
    if proc.returncode != 0:
        log("%s FAILED (exit %s):\n%s" % (name, proc.returncode, tail))
        sys.exit(1)
    log("%s OK" % name)


def main():
    only = set(sys.argv[1:])
    if not Path(VCBAT).exists():
        sys.exit("Visual Studio 2022 Build Tools not found at %s" % VCBAT)
    qtbase = W / "src" / "qtbase-everywhere-src-6.11.2"
    decl = W / "src" / "qtdeclarative-everywhere-src-6.11.2"
    if not qtbase.is_dir() or not decl.is_dir():
        sys.exit("Qt sources missing in %s; run scripts/windows/download_qt_sources.bat first"
                 % (W / "src"))

    steps = [
        ("build_qtbase_tools", lambda: run_bat(REPO / "scripts" / "windows" / "build_qtbase_tools.bat",
                                               "qtbase host tools")),
        ("stage_headers", lambda: run_py(REPO / "scripts" / "windows" / "stage_headers.py",
                                         "stage Qt headers")),
        ("synth_headers", lambda: run_py(REPO / "scripts" / "windows" / "synth_headers.py",
                                         "synthesize config/exports headers")),
        ("gen_import_libs", lambda: run_bat(REPO / "scripts" / "windows" / "gen_import_libs.bat",
                                            "generate import libraries")),
        ("make_qt_package", lambda: run_py(REPO / "scripts" / "windows" / "make_qt_package.py",
                                           "generate Qt6 CMake package")),
        ("patch_kddw", patch_kddw_sources),
        ("build_kddw", lambda: run_bat(REPO / "scripts" / "windows" / "build_kddw.bat",
                                       "build KDDockWidgets + bootstrap")),
    ]
    for key, action in steps:
        if only and key not in only:
            continue
        action()

    (W / "qt-version.txt").write_text("6.11.2\n", encoding="ascii")
    log("done: docking dependency is at", W / "bootstrap")


if __name__ == "__main__":
    main()
