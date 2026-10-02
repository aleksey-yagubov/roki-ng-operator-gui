"""Install the gi/GStreamer bootstrap into the user site-packages (Windows).

Copies gi/cairo from .deps/windows/gtk, writes the pointer files for the
.pth bootstrap and registers gi_gstreamer_win32_bootstrap so that
`import gi` + Gst typelibs work in any new Python process.
"""
import pathlib
import shutil
import sys
import sysconfig

REPO = pathlib.Path(__file__).resolve().parents[2]
GTK = REPO / ".deps" / "windows" / "gtk"
GST_CANDIDATES = [
    r"C:\Program Files\gstreamer\1.0\msvc_x86_64",
    r"C:\gstreamer\1.0\msvc_x86_64",
]


def main():
    sp = pathlib.Path(sysconfig.get_paths()["purelib"])
    gtk_sp = GTK / "lib" / "site-packages"
    for name in ("gi", "cairo"):
        src = gtk_sp / name
        if not src.is_dir():
            raise SystemExit("missing %s; run install_video_windows.bat fully" % src)
        dest = sp / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__"))

    gst = next((pathlib.Path(c) for c in GST_CANDIDATES
                if (pathlib.Path(c) / "bin" / "gstreamer-1.0-0.dll").exists()), None)
    if gst is None:
        raise SystemExit("GStreamer MSVC x64 not found; install gstreamer-1.0-msvc-x86_64 first")

    (sp / "gi_gstreamer_win32_gtkroot.txt").write_text(str(GTK), encoding="utf-8")
    (sp / "gi_gstreamer_win32_gstroot.txt").write_text(str(gst), encoding="utf-8")
    shutil.copy2(REPO / "scripts" / "windows" / "gi_gstreamer_win32_bootstrap.py",
                 sp / "gi_gstreamer_win32_bootstrap.py")
    (sp / "gi_gstreamer_win32_bootstrap.pth").write_text(
        "import gi_gstreamer_win32_bootstrap\n", encoding="ascii")
    print("gi bootstrap installed into", sp)


if __name__ == "__main__":
    sys.exit(main())
