@echo off
REM Vouchsafe — one-click launcher for Windows
REM Double-click this file to start the audit tool.

cd /d "%~dp0"

if not exist venv (
    echo First-time setup: creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    echo Installing dependencies...
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate
)

echo.
echo Starting Vouchsafe...
echo Press Ctrl+C in this window to stop.
echo.
streamlit run app.py
pause
