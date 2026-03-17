#!/usr/bin/env bash
# cl0w — macOS / Linux 직접 실행 스크립트 (Docker 없이)
# 사용법: ./run.sh
# 사전 준비: pip install -r requirements.txt

set -euo pipefail

# ── 의존성 설치 (--install 플래그) ───────────────────────────────────────────
if [[ "${1:-}" == "--install" ]]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt python-dotenv
fi

# ── Python 확인 ───────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "Error: python3 not found. Install from https://python.org" >&2
    exit 1
fi

# ── .env 확인 ─────────────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    echo "Warning: .env not found. Copying from .env.example..."
    cp .env.example .env
    echo "Edit .env and fill in your tokens, then re-run."
    exit 1
fi

# ── sessions / tools 디렉터리 보장 ───────────────────────────────────────────
mkdir -p sessions tools

# ── 실행 ─────────────────────────────────────────────────────────────────────
printf "\033[35m"
cat << 'EOF'
 ██████╗██╗      ██████╗ ██╗    ██╗
██╔════╝██║     ██╔═████╗██║    ██║
██║     ██║     ██║██╔██║██║ █╗ ██║
██║████╗██║     ████╔╝██║██║███╗██║
╚██████╔╝███████╗╚██████╔╝╚███╔███╔╝
 ╚═════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝
EOF
printf "\033[0m"

echo ""
echo "Starting cl0w (no container mode)..."
echo "Stop with Ctrl+C"
echo ""

python3 bot.py
