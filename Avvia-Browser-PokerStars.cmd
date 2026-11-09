@echo off
setlocal
cd /d "%~dp0"
rem Prefer the installed Python: virtual-environment executables may be
rem blocked by Device Guard even when the installed interpreter is allowed.
set "capturePython=python"
python -c "import browser_capture" >nul 2>&1
if not errorlevel 1 goto launch

set "capturePython=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if exist "%capturePython%" (
    "%capturePython%" -c "import browser_capture" >nul 2>&1
    if not errorlevel 1 goto launch
)

set "capturePython=.venv\Scripts\python.exe"
if exist "%capturePython%" (
    "%capturePython%" -c "import browser_capture" >nul 2>&1
    if not errorlevel 1 goto launch
)

set "capturePython=.venv-training\Scripts\python.exe"
if exist "%capturePython%" (
    "%capturePython%" -c "import browser_capture" >nul 2>&1
    if not errorlevel 1 goto launch
)

echo Nessun interprete Python disponibile con le dipendenze del bot.
echo Se Device Guard blocca anche Python installato, contatta l'amministratore.
pause
exit /b 1

:launch
"%capturePython%" browser_capture.py %*
set "captureExit=%errorlevel%"
if not "%captureExit%"=="0" pause
exit /b %captureExit%
