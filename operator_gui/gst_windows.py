"""Set up the PyGObject + GStreamer environment on Windows before `import gi`.

PyGObject comes from a gvsbuild bundle (has Windows builds of gi for
cp3xx), GStreamer from the official MSVC x64 installer. The gvsbuild GLib
loads first so a single GLib instance serves both stacks (the DLL names
coincide, GStreamer's dependency resolves into the already-loaded copy).
"""
import ctypes
import os
import sys
from pathlib import Path

READY = False

_ROOT = Path(__file__).resolve().parents[1] / ".deps" / "windows"


def _first_existing(*paths):
    for candidate in paths:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def _has_gstreamer(root):
    return (root / "bin" / "gstreamer-1.0-0.dll").exists() or \
        (root / "bin" / "libgstreamer-1.0-0.dll").exists()


def _gstreamer_root():
    yield from (os.environ.get("GSTREAMER_ROOT"), r"C:\gstreamer\1.0\msvc_x86_64")
    for base in (r"C:\gstreamer", os.environ.get("ProgramFiles", r"C:\Program Files")):
        p = Path(base)
        if not p.is_dir():
            continue
        for cand in sorted(p.glob("gstreamer/1.0/msvc_x86_64*")):
            yield str(cand)
        for cand in sorted(p.glob("1.0/msvc_x86_64*")):
            yield str(cand)


def prepare():
    """Make `import gi` and Gst-1.0/GstVideo-1.0 typelibs work. Idempotent."""
    global READY
    if READY:
        return
    if sys.platform != "win32":
        READY = True
        return

    gtk = _first_existing(os.environ.get("GTK_ROOT"), _ROOT / "gtk")
    if gtk is None:
        raise RuntimeError(
            "gvsbuild GTK (PyGObject для Windows) не найден: скачайте GTK zip с "
            "https://github.com/wingtk/gvsbuild/releases в .deps/windows/gtk")
    gst_root = next((Path(c) for c in _gstreamer_root()
                     if c and _has_gstreamer(Path(c))), None)
    if gst_root is None:
        raise RuntimeError("GStreamer MSVC x64 не найден; установите gstreamer-1.0-msvc-x86_64")

    gtk_bin = str(gtk / "bin")
    gst_bin = str(gst_root / "bin")
    for dll_dir in (gtk_bin, gst_bin):
        os.add_dll_directory(dll_dir)
    # gvsbuild GLib must be the shared instance for both stacks.
    ctypes.CDLL(str(gtk / "bin" / "glib-2.0-0.dll"))
    ctypes.CDLL(str(gtk / "bin" / "girepository-2.0-0.dll"))

    site_packages = gtk / "lib" / "site-packages"
    if site_packages.is_dir() and str(site_packages) not in sys.path:
        sys.path.append(str(site_packages))

    typelib_dirs = [str(gtk / "lib" / "girepository-1.0")]
    for gir in (gst_root / "share" / "gir-1.0", gst_root / "lib" / "gir-1.0",
                gst_root / "lib" / "girepository-1.0"):
        if gir.is_dir():
            typelib_dirs.append(str(gir))
    existing = os.environ.get("GI_TYPELIB_PATH")
    if existing:
        typelib_dirs.append(existing)
    os.environ["GI_TYPELIB_PATH"] = ";".join(typelib_dirs)

    if "GST_PLUGIN_PATH" not in os.environ:
        os.environ["GST_PLUGIN_PATH"] = str(gst_root / "lib" / "gstreamer-1.0")

    READY = True
