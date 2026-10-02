@echo off
setlocal
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 echo VCVARS_FAIL & exit /b 1
"%LOCALAPPDATA%\Python\bin\python.exe" "%~dp0gen_import_libs.py"
exit /b %ERRORLEVEL%
