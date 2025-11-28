@echo off
REM ==============================================
REM LOCAL DEVELOPMENT - Run TTS Web App
REM ==============================================
REM This script runs the app locally for testing
REM Changes will NOT affect your production website
REM ==============================================

echo.
echo ============================================
echo   Cheap TTS - Local Development Server
echo ============================================
echo.

REM Check if Python is available
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH
    echo Please install Python and add it to your PATH
    pause
    exit /b 1
)

REM Check if .env exists
if not exist ".env" (
    echo WARNING: .env file not found
    echo Creating from .env.example...
    if exist ".env.example" (
        copy ".env.example" ".env"
        echo Please edit .env with your local settings
    ) else (
        echo ERROR: .env.example not found either
    )
)

REM Create virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing/updating dependencies...
pip install -r requirements.txt -q

REM Create output directory
if not exist "webapp\output" mkdir webapp\output

echo.
echo ============================================
echo   Starting local server...
echo   Open: http://localhost:5000
echo   Press Ctrl+C to stop
echo ============================================
echo.

REM Run the Flask app directly (not gunicorn on Windows)
set FLASK_DEBUG=True
python -m webapp.app
