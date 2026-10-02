"""Use the local Windows/macOS KDDockWidgets bootstrap without loading Linux ELF plugins."""
import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import qVersion

_library=None


def _engine_handle(engine):
    from shiboken6 import getCppPointer
    return getCppPointer(engine)[0]


def _check_qt_version(stamp_dir):
    version_file = stamp_dir / 'qt-version.txt'
    if not version_file.exists() or version_file.read_text().strip() != qVersion():
        raise RuntimeError(f'Docking was built for another Qt; run scripts/build_windows.py ({qVersion()} active)')


def _load_bootstrap(engine, library):
    global _library
    _library = ctypes.CDLL(str(library))
    _library.roki_docking_qt_version.restype = ctypes.c_char_p
    built = _library.roki_docking_qt_version().decode()
    if built != qVersion():
        raise RuntimeError(f'Docking Qt {built} differs from Python Qt {qVersion()}; rebuild it')
    _library.roki_docking_initialize.argtypes = [ctypes.c_void_p]
    _library.roki_docking_initialize.restype = ctypes.c_int
    if _library.roki_docking_initialize(_engine_handle(engine)):
        raise RuntimeError('Cannot initialize native docking against this Qt application')


def _configure_windows(engine, root):
    deps = root / '.deps' / 'windows'
    _check_qt_version(deps)
    import PySide6
    os.add_dll_directory(str(Path(PySide6.__file__).resolve().parent))
    for candidate in (deps / 'bootstrap' / 'roki_docking_bootstrap.dll',
                      deps / 'bootstrap' / 'Release' / 'roki_docking_bootstrap.dll'):
        if candidate.exists():
            _load_bootstrap(engine, candidate)
            return
    raise RuntimeError('Build the Windows docking dependency with scripts/build_windows.py first')


def _configure_darwin(engine, root):
    library=root/'.deps/macos/bootstrap/libroki_docking_bootstrap.dylib'
    if not library.exists():
        raise RuntimeError('Build the macOS dependency with scripts/build_macos.sh first')
    _check_qt_version(root/'.deps/macos')
    _load_bootstrap(engine, library)


def configure(engine,root):
    if sys.platform=='win32':
        _configure_windows(engine, root)
    elif sys.platform=='darwin':
        _configure_darwin(engine, root)
    else:
        engine.addImportPath(str(root/'native/qml'))
