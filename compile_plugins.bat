@echo off
echo Compiling Python plugins...

set "VENV_PATH=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PATH%" (
    echo Error: Python virtual environment not found at %VENV_PATH%
    echo Please ensure you have a virtual environment set up.
    goto :eof
)

echo Compiling test_modules...
"%VENV_PATH%" -m compileall -f test_modules

echo Compiling drivers...
"%VENV_PATH%" -m compileall -f drivers

echo Plugin compilation complete.
pause
