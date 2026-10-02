"""Make `import gi` with Gst-1.0/GstVideo-1.0 typelibs work out of the box.

Written by scripts/windows/install_video_windows.bat: two pointer files with
the gvsbuild GTK root and the GStreamer MSVC root. All failures are silent so
a normal Python session is never broken by this hook.
"""
import ctypes
import os
from pathlib import Path

_COOKIES = []


def _read_pointer(name):
    pointer = Path(__file__).with_name(name)
    if pointer.exists():
        value = pointer.read_text(encoding='utf-8').strip()
        if value and Path(value).is_dir():
            return Path(value)
    return None


def _setup():
    gtk = _read_pointer('gi_gstreamer_win32_gtkroot.txt')
    gst = _read_pointer('gi_gstreamer_win32_gstroot.txt')
    path = os.environ.get('PATH', '')
    typelibs = []
    if gtk:
        bin_dir = str(gtk / 'bin')
        _COOKIES.append(os.add_dll_directory(bin_dir))
        if bin_dir.lower() not in path.lower().split(';'):
            path = bin_dir + ';' + path
        for name in ('glib-2.0-0.dll', 'girepository-2.0-0.dll', 'girepository-1.0-1.dll'):
            dll = gtk / 'bin' / name
            if dll.exists():
                ctypes.CDLL(str(dll))
        for gir in (gtk / 'lib' / 'girepository-1.0',):
            if gir.is_dir():
                typelibs.append(str(gir))
    if gst:
        bin_dir = str(gst / 'bin')
        _COOKIES.append(os.add_dll_directory(bin_dir))
        if bin_dir.lower() not in path.lower().split(';'):
            path = bin_dir + ';' + path
        for gir in (gst / 'lib' / 'girepository-1.0', gst / 'share' / 'gir-1.0'):
            if gir.is_dir():
                typelibs.append(str(gir))
        plugins = gst / 'lib' / 'gstreamer-1.0'
        if plugins.is_dir() and 'GST_PLUGIN_PATH' not in os.environ:
            os.environ['GST_PLUGIN_PATH'] = str(plugins)
    if path != os.environ.get('PATH', ''):
        os.environ['PATH'] = path
    if typelibs:
        existing = os.environ.get('GI_TYPELIB_PATH')
        if existing:
            typelibs.append(existing)
        os.environ['GI_TYPELIB_PATH'] = ';'.join(typelibs)


try:
    _setup()
except Exception:
    pass
