@echo off
setlocal enabledelayedexpansion

title FireWatch AI - Satellite Observation Triage Dashboard

echo =====================================================================
echo                FIREWATCH AI - EARTH OBSERVATION DASHBOARD
echo        Satellite-Based Active Fire Observation Triage ^& Decision Support
echo =====================================================================
echo.

:: Check for Python installation
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not found in your PATH.
    echo Please install Python 3.11 or higher and ensure 'Add to PATH' is checked.
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

:: Display Python version
for /f "tokens=*" %%i in ('python --version') do set PYTHON_VER=%%i
echo [*] Detected: %PYTHON_VER%

:: Check if requirements are installed
echo [*] Checking dependencies...
python -c "import streamlit, pandas, numpy, folium, streamlit_folium, plotly, sklearn, pydantic, requests, sqlite3" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] Installing missing dependencies from requirements.txt...
    python -m pip install -r requirements.txt
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
) else (
    echo [*] All core dependencies verified.
)

:: Create .env if not exists
if not exist .env (
    if exist .env.example (
        echo [*] Initializing .env from .env.example...
        copy .env.example .env >nul
    )
)

echo.
echo =====================================================================
echo Launching FireWatch AI Streamlit Dashboard...
echo Browser will automatically open at: http://localhost:8501
echo Press Ctrl+C in this terminal window to stop the server.
echo =====================================================================
echo.

python -m streamlit run app.py --server.headless=false

if %ERRORLEVEL% neq 0 (
    echo.
    echo [!] Server stopped or exited with code %ERRORLEVEL%.
    pause
)
