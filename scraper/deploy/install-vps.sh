#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash deploy/install-vps.sh [--project-dir /opt/betto] [--python python3] [--run-live-test] [--no-systemd]

Environment:
  HLTV_PROXY_URL       Optional. If set and .env is missing, the script writes it to .env.
  HLTV_DAILY_CAP       Optional. Defaults to 100 for the pilot deployment.

Run this from the scraper directory after the repo has been copied or pulled on the VPS:
  cd /opt/betto/scraper
  HLTV_PROXY_URL='http://username:password@gate.decodo.com:7000' bash deploy/install-vps.sh --run-live-test
EOF
}

PROJECT_DIR=""
PYTHON_BIN="python3"
RUN_LIVE_TEST=0
INSTALL_SYSTEMD=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --run-live-test)
      RUN_LIVE_TEST=1
      shift
      ;;
    --no-systemd)
      INSTALL_SYSTEMD=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRAPER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ -z "$PROJECT_DIR" ]]; then
  PROJECT_DIR="$(cd "$SCRAPER_DIR/.." && pwd)"
fi
SCRAPER_DIR="$PROJECT_DIR/scraper"

if [[ ! -f "$SCRAPER_DIR/requirements.txt" ]]; then
  echo "Could not find scraper/requirements.txt at: $SCRAPER_DIR" >&2
  echo "Use --project-dir /path/to/betto if the repo is not in the current location." >&2
  exit 1
fi

echo "==> Installing OS packages"
if [[ "$PYTHON_BIN" == "python3" ]]; then
  VENV_PACKAGE="python3-venv"
else
  VENV_PACKAGE="$PYTHON_BIN-venv"
fi
sudo apt-get update
sudo apt-get install -y "$PYTHON_BIN" "$VENV_PACKAGE" git rsync ca-certificates curl

echo "==> Creating virtualenv"
cd "$SCRAPER_DIR"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo "==> Installing Playwright Chromium"
.venv/bin/python -m playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium

echo "==> Preparing .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  if [[ -n "${HLTV_PROXY_URL:-}" ]]; then
    .venv/bin/python - <<PY
import os
from pathlib import Path

path = Path(".env")
text = path.read_text(encoding="utf-8")
text = text.replace("HLTV_PROXY_URL=http://username:password@gate.decodo.com:7000", f"HLTV_PROXY_URL={os.environ['HLTV_PROXY_URL']}")
text = text.replace("HLTV_DAILY_CAP=100", f"HLTV_DAILY_CAP={os.environ.get('HLTV_DAILY_CAP', '100')}")
path.write_text(text, encoding="utf-8")
PY
  else
    echo "Created .env from .env.example."
    echo "Edit .env and set HLTV_PROXY_URL before running live scraping."
  fi
fi
chmod 600 .env

echo "==> Running preflight"
if ! .venv/bin/python -m scraper.cli preflight --create-dirs; then
  echo "Preflight failed. Fix .env, then rerun:" >&2
  echo "  cd $SCRAPER_DIR && .venv/bin/python -m scraper.cli preflight --create-dirs" >&2
  exit 1
fi

if [[ "$RUN_LIVE_TEST" -eq 1 ]]; then
  echo "==> Running limited live test"
  .venv/bin/python -m scraper.cli test-live
fi

if [[ "$INSTALL_SYSTEMD" -eq 1 ]]; then
  echo "==> Installing systemd unit and timer"
  service_file="/etc/systemd/system/hltv-scraper.service"
  timer_file="/etc/systemd/system/hltv-scraper.timer"
  sudo tee "$service_file" >/dev/null <<EOF
[Unit]
Description=HLTV scraper run
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=$SCRAPER_DIR/.venv/bin/python -m scraper.cli run
ExecStartPost=$SCRAPER_DIR/.venv/bin/python -m scraper.cli backup --out-dir $SCRAPER_DIR/backups
Nice=10
EOF

  sudo tee "$timer_file" >/dev/null <<'EOF'
[Unit]
Description=Run HLTV scraper every 6 hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now hltv-scraper.timer
  sudo systemctl list-timers hltv-scraper.timer --no-pager
fi

echo "==> Done"
echo "Useful commands:"
echo "  cd $SCRAPER_DIR && .venv/bin/python -m scraper.cli status"
echo "  journalctl -u hltv-scraper.service -n 100 --no-pager"
echo "  sudo systemctl start hltv-scraper.service"
