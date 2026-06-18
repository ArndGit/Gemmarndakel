@echo off
setlocal

cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo uv wurde nicht gefunden.
    echo.
    echo Bitte installiere uv und starte diesen Launcher danach erneut.
    echo https://docs.astral.sh/uv/getting-started/installation/
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Initialisiere lokale Umgebung mit uv sync ...
    uv sync --frozen
    if errorlevel 1 (
        echo.
        echo uv sync ist fehlgeschlagen.
        echo.
        pause
        exit /b 1
    )
)

set "PYTHON_EXE=%CD%\.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"

start "" "%PYTHON_EXE%" "%CD%\main.py"
exit /b 0
