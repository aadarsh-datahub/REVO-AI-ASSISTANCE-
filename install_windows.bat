@echo off
setlocal
cd /d "%~dp0"
echo.
echo ================================
echo   REVO OS - Windows Installer
echo ================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
  echo Python not found. Install Python 3.11 or 3.12 from https://www.python.org/downloads/
  pause
  exit /b 1
)
if not exist ".venv" (
  echo Creating virtual environment...
  python -m venv .venv
)
call ".venv\Scripts\activate.bat"
python setup.py
if errorlevel 1 (
  echo Setup failed. Check the error above.
  pause
  exit /b 1
)
echo.
echo Setup complete. Add API keys in config\api_keys.json, then run start_revo.bat
echo.
pause
