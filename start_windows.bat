@echo off
title AI Job Search Assistant

echo.
echo  ============================================
echo   AI Job Search Assistant — Startup Script
echo  ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

:: Install dependencies
echo [1/3] Installing backend dependencies...
cd /d "%~dp0backend"
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

:: Start backend in new window
echo [2/3] Starting backend API server...
start "JobAI Backend" cmd /k "cd /d "%~dp0backend" && uvicorn main:app --reload --port 8000"

:: Wait a moment
timeout /t 3 /nobreak >nul

:: Open frontend in browser
echo [3/3] Opening frontend in browser...
start "" "%~dp0frontend\index.html"

echo.
echo  ✅ All done!
echo  Backend API : http://localhost:8000
echo  API Docs    : http://localhost:8000/docs
echo  Frontend    : Opened in your browser
echo.
echo  Press any key to exit this launcher...
pause >nul
