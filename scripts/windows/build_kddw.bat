@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 echo VCVARS_FAIL & exit /b 1
set "PATH=%LOCALAPPDATA%\Python\pythoncore-3.14-64\Scripts;%PATH%"
set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "W=%ROOT%\.deps\windows"
set "SDK=%W%\sdk"

cmake -S "%ROOT%\.deps\src\KDDockWidgets" -B "%W%\build-kddw" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_PREFIX_PATH="%SDK%" ^
  -DCMAKE_INSTALL_PREFIX="%W%\install" ^
  -DKDDockWidgets_FRONTENDS=qtquick ^
  -DKDDockWidgets_QML_MODULE=OFF ^
  -DKDDockWidgets_EXAMPLES=OFF ^
  -DKDDockWidgets_TESTS=OFF ^
  -DKDDockWidgets_PYTHON_BINDINGS=OFF ^
  -DKDDockWidgets_NO_SPDLOG=ON
if errorlevel 1 echo KDDW_CONFIGURE_FAIL & exit /b 1

cmake --build "%W%\build-kddw" --parallel 11
if errorlevel 1 echo KDDW_BUILD_FAIL & exit /b 1

cmake --install "%W%\build-kddw"
if errorlevel 1 echo KDDW_INSTALL_FAIL & exit /b 1

cmake -S "%ROOT%\native\windows" -B "%W%\bootstrap-build" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_PREFIX_PATH="%W%\install;%SDK%"
if errorlevel 1 echo BOOTSTRAP_CONFIGURE_FAIL & exit /b 1

cmake --build "%W%\bootstrap-build" --parallel 11
if errorlevel 1 echo BOOTSTRAP_BUILD_FAIL & exit /b 1

if not exist "%W%\bootstrap" mkdir "%W%\bootstrap"
copy /y "%W%\bootstrap-build\roki_docking_bootstrap.dll" "%W%\bootstrap\" >nul
copy /y "%W%\install\bin\*.dll" "%W%\bootstrap\" >nul
echo KDDW_WINDOWS_OK
