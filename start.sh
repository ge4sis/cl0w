#!/usr/bin/env bash
set -e

VENV_DIR=".venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

source "$VENV_DIR/Scripts/activate" 2>/dev/null || source "$VENV_DIR/bin/activate"

echo "Starting cl0w..."
python bot.py
