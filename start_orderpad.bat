@echo off
title OrderPad server
cd /d "%~dp0backend"
echo.
echo   OrderPad - starting the shop server...
echo   (if Windows Firewall asks, click Allow for private networks)
echo.
python -m app.seed
echo.
echo   Phones on the shop WiFi: log in as admin and see
echo   Admin - Connect devices for the exact address to open.
echo   Keep this window open while the shop is running.
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
