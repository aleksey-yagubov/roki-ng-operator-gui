@echo off
setlocal
set "W=%~dp0..\..\.deps\windows"
for %%I in ("%W%") do set "W=%%~fI"
set "DL=%TEMP%"
set "GST_VER=1.28.7"
set "GTK_VER=2026.8.0"

if not exist "C:\Program Files\gstreamer\1.0\msvc_x86_64\bin\gstreamer-1.0-0.dll" (
  echo == GStreamer %GST_VER%: downloading installer
  curl -fSL --retry 10 --retry-all-errors -C - -o "%DL%\gstreamer-%GST_VER%.exe" ^
    "https://gstreamer.freedesktop.org/data/pkg/windows/%GST_VER%/msvc/gstreamer-1.0-msvc-x86_64-%GST_VER%.exe" || exit /b 1
  echo == GStreamer: silent install (a few minutes)
  "%DL%\gstreamer-%GST_VER%.exe" /quiet /log "%DL%\gst_install.log" || exit /b 1
) else (
  echo == GStreamer already installed
)

if not exist "%W%\gtk\lib\site-packages\gi" (
  echo == gvsbuild GTK %GTK_VER%: downloading PyGObject bundle
  curl -fSL --retry 10 --retry-all-errors -C - -o "%DL%\gtk-%GTK_VER%.zip" ^
    "https://github.com/wingtk/gvsbuild/releases/download/%GTK_VER%/GTK4_Gvsbuild_%GTK_VER%_x64.zip" || exit /b 1
  if not exist "%W%\gtk" mkdir "%W%\gtk"
  pushd "%W%\gtk"
  "%LOCALAPPDATA%\Python\bin\python.exe" -c "import zipfile, sys; z=zipfile.ZipFile(r'%DL%\gtk-%GTK_VER%.zip'); names=z.namelist(); keep=[n for n in names if n.startswith(('bin/','lib/site-packages/','lib/girepository-1.0/','lib/glib-2.0/'))]; z.extractall('.', members=keep)" || exit /b 1
  popd
) else (
  echo == gvsbuild GTK already extracted
)

"%LOCALAPPDATA%\Python\bin\python.exe" "%~dp0install_gi_bootstrap.py" || exit /b 1
echo VIDEO_WINDOWS_OK
