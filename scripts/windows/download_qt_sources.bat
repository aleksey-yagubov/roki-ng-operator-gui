@echo off
setlocal
set "W=%~dp0..\..\.deps\windows"
for %%I in ("%W%") do set "W=%%~fI"
set "SRC=%W%\src"
set "BASE=https://mirrors.tuna.tsinghua.edu.cn/qt/official_releases/qt/6.11/6.11.2/submodules"
if not exist "%SRC%" mkdir "%SRC%"
pushd "%SRC%"
curl -fSL --retry 10 --retry-all-errors -C - -o qtbase-everywhere-src-6.11.2.tar.xz "%BASE%/qtbase-everywhere-src-6.11.2.tar.xz" || exit /b 1
curl -fSL --retry 10 --retry-all-errors -C - -o qtdeclarative-everywhere-src-6.11.2.tar.xz "%BASE%/qtdeclarative-everywhere-src-6.11.2.tar.xz" || exit /b 1
if not exist qtbase-everywhere-src-6.11.2 (
  tar -xf qtbase-everywhere-src-6.11.2.tar.xz || exit /b 1
)
if not exist qtdeclarative-everywhere-src-6.11.2 (
  tar -xf qtdeclarative-everywhere-src-6.11.2.tar.xz || exit /b 1
)
if not exist "%W%\..\src\KDDockWidgets\CMakeLists.txt" (
  mkdir "%W%\..\src\KDDockWidgets"
  tar -xf "%ROOT%native\sources\KDDockWidgets-v2.4.1.tar.gz" -C "%W%\..\src\KDDockWidgets" --strip-components=1 || exit /b 1
)
popd
echo QT_SOURCES_OK
