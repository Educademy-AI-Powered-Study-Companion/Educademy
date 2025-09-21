@echo off
cls
echo =================================
echo   Starting Educademy Application
echo =================================
echo.

echo Starting Flask Server in a new window...
:: This command opens a new window titled "Flask Server" and runs the app.
:: The /k flag keeps the window open to display logs.
start "Flask Server" cmd /k python app.py
echo.

echo Waiting for server to initialize...
:: Waits 5 seconds to give the server time to start before opening the browser.
timeout /t 5 /nobreak >nul
echo.

echo Opening application in your default browser...
start "" http://127.0.0.1:5000/

:: The main script will now close, but the server window will remain open.
exit