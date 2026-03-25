#!/usr/bin/env bash
set -e

VENV_DIR=".venv"

echo "=== cl0w setup ==="

# Create venv if not exists
if [ ! -d "$VENV_DIR" ]; then
    echo "[1/3] Creating virtual environment..."
    python -m venv "$VENV_DIR"
else
    echo "[1/3] Virtual environment already exists, skipping."
fi

# Activate
source "$VENV_DIR/Scripts/activate" 2>/dev/null || source "$VENV_DIR/bin/activate"

# Install dependencies
echo "[2/3] Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

# Copy config templates if not present
echo "[3/3] Checking config files..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  .env created from template — fill in your values."
else
    echo "  .env already exists, skipping."
fi

if [ ! -f "mcp.json" ]; then
    cp mcp.json.example mcp.json
    echo "  mcp.json created from template — add your MCP servers."
else
    echo "  mcp.json already exists, skipping."
fi

if [ ! -d "personas" ]; then
    cp -r personas.example personas
    echo "  personas/ created and seeded with examples."
else
    echo "  personas/ already exists, skipping."
fi

if [ ! -d "skills" ]; then
    cp -r skills.example skills
    echo "  skills/ created and seeded with examples."
else
    echo "  skills/ already exists, skipping."
fi

echo ""
echo "=== Setup complete ==="
echo "Next steps:"
echo "  1. Edit .env        (add TELEGRAM_BOT_TOKEN and ALLOWED_USER_IDS)"
echo "  2. Edit mcp.json    (add MCP servers, or leave empty)"
echo "  3. Run: ./start.sh"
