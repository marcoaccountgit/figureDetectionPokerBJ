@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" recognize.py --camera 0 --output artifacts\webcam
) else if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" recognize.py --camera 0 --output artifacts\webcam
) else (
    py -3 recognize.py --camera 0 --output artifacts\webcam
)
if errorlevel 1 pause
