@echo off
echo Cleaning up any orphaned processes on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /F /PID %%a 2>nul
)
echo Starting Assay Web Application (Liquid Light UI)...
python run_app.py
pause
