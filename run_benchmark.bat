@echo off
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto RUN
echo .venv not found. Run setup_windows.bat first.
pause
exit /b 1

:RUN
.venv\Scripts\python.exe main.py --repetitions 30
if errorlevel 1 goto FAIL
pause
exit /b 0

:FAIL
echo.
echo Something went wrong. See the messages above.
pause
exit /b 1
