@echo off
cd /d "%~dp0"
start "" cmd /c "timeout /t 3 >nul & start http://localhost:5000"
"venv\Scripts\python.exe" -X utf8 app.py
