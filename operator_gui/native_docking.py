"""Use the local macOS KDDockWidgets build without loading Linux ELF plugins."""
import ctypes
import sys

from PySide6.QtCore import qVersion

_library=None


def configure(engine,root):
    global _library
    if sys.platform!='darwin':
        engine.addImportPath(str(root/'native/qml'))
        return
    from shiboken6 import getCppPointer
    library=root/'.deps/macos/bootstrap/libroki_docking_bootstrap.dylib'
    if not library.exists():
        raise RuntimeError('Build the macOS dependency with scripts/build_macos.sh first')
    version_file=root/'.deps/macos/qt-version.txt'
    if not version_file.exists() or version_file.read_text().strip()!=qVersion():
        raise RuntimeError('Qt build mismatch; use scripts/build_macos.sh and scripts/run_macos.sh')
    _library=ctypes.CDLL(str(library))
    _library.roki_docking_qt_version.restype=ctypes.c_char_p
    built=_library.roki_docking_qt_version().decode()
    if built!=qVersion():
        raise RuntimeError(f'Docking Qt {built} differs from Python Qt {qVersion()}; use scripts/run_macos.sh')
    _library.roki_docking_initialize.argtypes=[ctypes.c_void_p]
    _library.roki_docking_initialize.restype=ctypes.c_int
    if _library.roki_docking_initialize(getCppPointer(engine)[0]):
        raise RuntimeError('Cannot initialize native docking against this Qt application')
