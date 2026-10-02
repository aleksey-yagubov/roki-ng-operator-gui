@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 echo VCVARS_FAIL & exit /b 1
set "PATH=%LOCALAPPDATA%\Python\pythoncore-3.14-64\Scripts;%PATH%"
set "W=%~dp0..\..\.deps\windows"
for %%I in ("%W%") do set "W=%%~fI"

cmake -S "%W%\src\qtbase-everywhere-src-6.11.2" -B "%W%\build-qtbase" -G Ninja ^
  -DCMAKE_BUILD_TYPE=Release ^
  -DCMAKE_INSTALL_PREFIX="%W%\sdk" ^
  -DBUILD_SHARED_LIBS=ON ^
  -DQT_BUILD_EXAMPLES=OFF -DQT_BUILD_TESTS=OFF -DQT_BUILD_BENCHMARKS=OFF ^
  -DQT_BUILD_DOCS=OFF ^
  -DQT_QMAKE_TARGET_MKSPEC=win32-msvc
if errorlevel 1 echo CONFIGURE_FAIL & exit /b 1

cmake --build "%W%\build-qtbase" --target moc rcc syncqt qtpaths --parallel 11
if errorlevel 1 echo TOOLS_BUILD_FAIL & exit /b 1

if not exist "%W%\sdk\bin" mkdir "%W%\sdk\bin"
copy /y "%W%\build-qtbase\bin\moc.exe" "%W%\sdk\bin\" >nul
copy /y "%W%\build-qtbase\bin\rcc.exe" "%W%\sdk\bin\" >nul
copy /y "%W%\build-qtbase\bin\qtpaths.exe" "%W%\sdk\bin\" >nul
copy /y "%W%\build-qtbase\bin\Qt6Core.dll" "%W%\sdk\bin\" >nul
echo QTBASE_TOOLS_OK
