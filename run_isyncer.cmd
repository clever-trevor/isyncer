@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setting up virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Make sure Python 3.12+ is installed.
        pause
        exit /b 1
    )
    echo Installing dependencies...
    .venv\Scripts\pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo Failed to install dependencies.
        pause
        exit /b 1
    )
)

start .venv\Scripts\pythonw.exe main.py
