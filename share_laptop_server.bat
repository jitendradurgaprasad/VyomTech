@echo off
setlocal enabledelayedexpansion

title FireWatch AI - Laptop Public Server Gateway

echo =====================================================================
echo       FIREWATCH AI - LAPTOP CLOUD GATEWAY & PUBLIC SERVER
echo =====================================================================
echo.
echo [*] Operating System: Windows
echo [*] Host Server: Local Laptop
echo [*] Operator: mjdp4317@gmail.com
echo [*] Forwarding Port: 8501 (Streamlit Engine)
echo.

:: Verify local Streamlit is running
python -c "import socket; s = socket.socket(); s.connect(('localhost', 8501))" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] Streamlit server is not running on port 8501.
    echo [*] Launching Streamlit dashboard in background...
    start /b python -m streamlit run app.py --server.port 8501 --server.headless true
    timeout /t 5 >nul
)

echo.
echo =====================================================================
echo [✓] CONNECTING YOUR LAPTOP TO SECURE HTTPS PUBLIC TUNNEL...
echo [✓] Keep this window open to maintain your laptop as the live server!
echo =====================================================================
echo.

if exist cloudflared.exe (
    echo [*] Launching Cloudflare global secure tunnel...
    cloudflared.exe tunnel --url http://localhost:8501
) else (
    echo [*] Launching SSH secure tunnel...
    ssh -o StrictHostKeyChecking=no -R 80:localhost:8501 nokey@localhost.run
)

echo.
echo [!] Tunnel closed.
pause
