@echo off
set VENV_DIR=.venv

if not exist "%VENV_DIR%" (
    echo Virtual environment not found. Run setup.bat first.
    exit /b 1
)

call %VENV_DIR%\Scripts\activate.bat

echo Starting cl0w...
python bot.py
