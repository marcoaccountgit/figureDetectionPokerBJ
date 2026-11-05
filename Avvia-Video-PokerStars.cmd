@echo off
setlocal
cd /d "%~dp0"
set "tableVideo=%USERPROFILE%\Videos\Screen Recordings\Screen Recording 2026-11-04 213508.mp4"
if not "%~1"=="" set "tableVideo=%~1"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" recognize.py --video "%tableVideo%" --detector model --profile pokerstars --preview --fps 5 --output artifacts\pokerstars-video
) else if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" recognize.py --video "%tableVideo%" --detector model --profile pokerstars --preview --fps 5 --output artifacts\pokerstars-video
) else (
    py -3 recognize.py --video "%tableVideo%" --detector model --profile pokerstars --preview --fps 5 --output artifacts\pokerstars-video
)
if errorlevel 1 pause
