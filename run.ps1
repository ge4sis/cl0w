# cl0w — Windows 직접 실행 스크립트 (Docker 없이)
# 사용법: .\run.ps1
# 사전 준비: pip install -r requirements.txt
#            pip install python-dotenv   (선택, .env 자동 로드용)

param(
    [switch]$Install   # -Install 플래그 시 의존성 자동 설치
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── 의존성 설치 (선택) ────────────────────────────────────────────────────────
if ($Install) {
    Write-Host "Installing dependencies..." -ForegroundColor Cyan
    pip install -r requirements.txt
    pip install python-dotenv
}

# ── Python 확인 ───────────────────────────────────────────────────────────────
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python을 찾을 수 없습니다. https://python.org 에서 설치하세요."
    exit 1
}

# ── .env 파일 로드 (python-dotenv 미설치 시 수동 처리) ───────────────────────
if (Test-Path ".env") {
    Get-Content ".env" | ForEach-Object {
        $line = $_.Trim()
        # 빈 줄, 주석 제외
        if ($line -and -not $line.StartsWith("#")) {
            $idx = $line.IndexOf("=")
            if ($idx -gt 0) {
                $key   = $line.Substring(0, $idx).Trim()
                $value = $line.Substring($idx + 1).Trim()
                # 이미 환경변수가 설정된 경우 덮어쓰지 않음
                if (-not [System.Environment]::GetEnvironmentVariable($key)) {
                    [System.Environment]::SetEnvironmentVariable($key, $value, "Process")
                }
            }
        }
    }
    Write-Host ".env loaded" -ForegroundColor Green
} else {
    Write-Warning ".env 파일이 없습니다. .env.example 을 복사해 설정하세요."
    Write-Host "  Copy-Item .env.example .env" -ForegroundColor Yellow
    exit 1
}

# ── TELEGRAM_BOT_TOKEN 확인 ──────────────────────────────────────────────────
if (-not $env:TELEGRAM_BOT_TOKEN) {
    Write-Error "TELEGRAM_BOT_TOKEN 이 설정되지 않았습니다. .env 파일을 확인하세요."
    exit 1
}

# ── sessions / tools 디렉터리 보장 ───────────────────────────────────────────
New-Item -ItemType Directory -Force -Path "sessions" | Out-Null
New-Item -ItemType Directory -Force -Path "tools"    | Out-Null

# ── 실행 ─────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  ██████╗██╗      ██████╗ ██╗    ██╗" -ForegroundColor Magenta
Write-Host " ██╔════╝██║     ██╔═████╗██║    ██║" -ForegroundColor Magenta
Write-Host " ██║     ██║     ██║██╔██║██║ █╗ ██║" -ForegroundColor Magenta
Write-Host " ██║████╗██║     ████╔╝██║██║███╗██║" -ForegroundColor Magenta
Write-Host " ╚██████╔╝███████╗╚██████╔╝╚███╔███╔╝" -ForegroundColor Magenta
Write-Host "  ╚═════╝ ╚══════╝ ╚═════╝  ╚══╝╚══╝" -ForegroundColor Magenta
Write-Host ""
Write-Host "Starting cl0w (no container mode)..." -ForegroundColor Cyan
Write-Host "Stop with Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

python bot.py
