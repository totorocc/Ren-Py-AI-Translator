@echo off
REM Launch the Ren'Py AI Translator (Windows).
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)

if not exist ".venv" (
    echo Creating virtual environment...
    %PY% -m venv .venv
)
call ".venv\Scripts\activate.bat"

python -c "import webview" 2>nul
if %errorlevel% neq 0 (
    echo Installing dependencies...
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
)

python main.py
pause
