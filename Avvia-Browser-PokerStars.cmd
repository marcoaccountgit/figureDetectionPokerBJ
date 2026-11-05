@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" browser_capture.py
) else if exist ".venv-training\Scripts\python.exe" (
    ".venv-training\Scripts\python.exe" browser_capture.py
) else (
    python browser_capture.py
)
if errorlevel 1 pause
