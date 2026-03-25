@echo off
setlocal

set VENV_DIR=.venv

echo === cl0w setup ===

if not exist "%VENV_DIR%" (
    echo [1/3] Creating virtual environment...
    python -m venv %VENV_DIR%
) else (
    echo [1/3] Virtual environment already exists, skipping.
)

call %VENV_DIR%\Scripts\activate.bat

echo [2/3] Installing dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo [3/3] Checking config files...
if not exist ".env" (
    copy .env.example .env
    echo   .env created from template -- fill in your values.
) else (
    echo   .env already exists, skipping.
)

if not exist "mcp.json" (
    copy mcp.json.example mcp.json
    echo   mcp.json created from template -- add your MCP servers.
) else (
    echo   mcp.json already exists, skipping.
)

if not exist "personas\" (
    xcopy /e /i personas.example personas
    echo   personas/ created and seeded with examples.
) else (
    echo   personas/ already exists, skipping.
)

if not exist "skills\" (
    xcopy /e /i skills.example skills
    echo   skills/ created and seeded with examples.
) else (
    echo   skills/ already exists, skipping.
)

echo.
echo === Setup complete ===
echo Next steps:
echo   1. Edit .env        (add TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS)
echo   2. Edit mcp.json    (add MCP servers, or leave empty)
echo   3. Run: start.bat
