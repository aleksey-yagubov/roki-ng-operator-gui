@echo off
setlocal
set "ROOT=%~dp0..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
"%LOCALAPPDATA%\Python\bin\python.exe" "%ROOT%\roki_operator.py" %*
