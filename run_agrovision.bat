@echo off
title Agrovision Digital Twin Launcher
color 0A

echo =========================================
echo   Starting Agrovision Digital Twin...
echo =========================================

:: Change to the directory where this script is located
cd /d "%~dp0"

echo [1/3] Opening Dashboard in your default browser...
start "" "frontend\index.html"

echo [2/3] Changing to backend directory...
cd backend

echo [3/3] Activating virtual environment and starting server...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo Server is starting and listening on ALL network interfaces... (Press CTRL+C to stop)
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) else (
    echo [ERROR] Virtual environment not found at backend\venv!
    echo Please ensure you have created it and installed requirements.
    pause
)
