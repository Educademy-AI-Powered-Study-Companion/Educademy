@echo off
cls
echo =================================
echo   Starting Educademy Application
echo =================================
echo.

echo Starting Flask Server in a new window...

start "Flask Server" cmd /k python app.py
echo.

timeout /t 1 /nobreak >nul

echo Opening application in your default browser...
start "" http://127.0.0.1:5000/

exit