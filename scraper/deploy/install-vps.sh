#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash deploy/install-vps.sh [--project-dir /opt/betto] [--python python3] [--run-live-test] [--no-systemd]

Environment:
  HLTV_PROXY_URL           Required for live scraping. Written to .env if missing.
  HLTV_DAILY_CAP           Optional. Defaults to 100 for pilot deployment.
  HLTV_BACKFILL_MAX_PAGE   Optional. Hard stop page for historical backfill.
  HLTV_BACKFILL_STOP_DATE  Optional. Date boundary (e.g. 2023-09-27 for CS2 era).
  HLTV_ALERT_WEBHOOK_URL   Optional. Webhook for backfill completion alerts.

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

# ── OS packages ──────────────────────────────────────────────────────
echo "==> Installing OS packages"
if [[ "$PYTHON_BIN" == "python3" ]]; then
  VENV_PACKAGE="python3-venv"
else
  VENV_PACKAGE="$PYTHON_BIN-venv"
fi
sudo apt-get update -qq
sudo apt-get install -y -qq "$PYTHON_BIN" "$VENV_PACKAGE" git rsync ca-certificates curl jq

# ── Python venv ──────────────────────────────────────────────────────
echo "==> Creating virtualenv"
cd "$SCRAPER_DIR"
"$PYTHON_BIN" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

# ── Playwright ───────────────────────────────────────────────────────
echo "==> Installing Playwright Chromium"
.venv/bin/python -m playwright install chromium
sudo .venv/bin/python -m playwright install-deps chromium

# ── .env ─────────────────────────────────────────────────────────────
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
if os.environ.get("HLTV_BACKFILL_MAX_PAGE"):
    text = text.replace("HLTV_BACKFILL_MAX_PAGE=", f"HLTV_BACKFILL_MAX_PAGE={os.environ['HLTV_BACKFILL_MAX_PAGE']}")
if os.environ.get("HLTV_BACKFILL_STOP_DATE"):
    text = text.replace("HLTV_BACKFILL_STOP_DATE=2023-09-27", f"HLTV_BACKFILL_STOP_DATE={os.environ['HLTV_BACKFILL_STOP_DATE']}")
if os.environ.get("HLTV_ALERT_WEBHOOK_URL"):
    text = text.replace("HLTV_ALERT_WEBHOOK_URL=", f"HLTV_ALERT_WEBHOOK_URL={os.environ['HLTV_ALERT_WEBHOOK_URL']}")
path.write_text(text, encoding="utf-8")
PY
  else
    echo "Created .env from .env.example."
    echo "Edit .env and set HLTV_PROXY_URL before running live scraping."
  fi
fi
chmod 600 .env

# ── Tests ────────────────────────────────────────────────────────────
echo "==> Running test suite"
if ! .venv/bin/python -m pytest tests/ -x -q --tb=line 2>&1; then
  echo "WARNING: Some tests failed. Check the output above." >&2
fi

# ── Preflight ────────────────────────────────────────────────────────
echo "==> Running preflight"
if ! .venv/bin/python -m scraper.cli preflight --create-dirs; then
  echo "Preflight failed. Fix .env, then rerun:" >&2
  echo "  cd $SCRAPER_DIR && .venv/bin/python -m scraper.cli preflight --create-dirs" >&2
  exit 1
fi

# ── Live test ────────────────────────────────────────────────────────
if [[ "$RUN_LIVE_TEST" -eq 1 ]]; then
  echo "==> Running limited live test"
  .venv/bin/python -m scraper.cli test-live
fi

# ── Reparse existing data with updated parser ────────────────────────
MATCH_DIR="$SCRAPER_DIR/data/raw/hltv/matches"
if [[ -d "$MATCH_DIR" ]] && [[ "$(ls -A "$MATCH_DIR" 2>/dev/null)" ]]; then
  echo "==> Reparsing existing raw HTML with updated parser"
  .venv/bin/python -m scraper.cli reparse-raw
fi

# ── Disk usage check ────────────────────────────────────────────────
echo "==> Disk usage"
DATA_DIR="$SCRAPER_DIR/data"
if [[ -d "$DATA_DIR" ]]; then
  du -sh "$DATA_DIR"/* 2>/dev/null || true
  DISK_AVAIL=$(df -BM --output=avail "$DATA_DIR" | tail -1 | tr -d ' M')
  if [[ "$DISK_AVAIL" -lt 1024 ]]; then
    echo "WARNING: Less than 1GB disk space remaining!" >&2
  fi
fi

# ── systemd units ────────────────────────────────────────────────────
if [[ "$INSTALL_SYSTEMD" -eq 1 ]]; then
  echo "==> Installing systemd units"

  # Main scraper: discover upcoming + fetch pending every 6h
  sudo tee /etc/systemd/system/hltv-scraper.service >/dev/null <<EOF
[Unit]
Description=HLTV scraper run (discover upcoming + fetch pending)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=$SCRAPER_DIR/.venv/bin/python -m scraper.cli run
ExecStartPost=$SCRAPER_DIR/.venv/bin/python -m scraper.cli backup --out-dir $SCRAPER_DIR/backups
Nice=10
TimeoutStartSec=1800
EOF

  sudo tee /etc/systemd/system/hltv-scraper.timer >/dev/null <<'EOF'
[Unit]
Description=Run HLTV scraper every 6 hours

[Timer]
OnBootSec=10min
OnUnitActiveSec=6h
Persistent=true

[Install]
WantedBy=timers.target
EOF

  # Historical backfill: walks through old results pages hourly
  sudo tee /etc/systemd/system/hltv-backfill.service >/dev/null <<EOF
[Unit]
Description=HLTV historical backfill
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=$SCRAPER_DIR/.venv/bin/python -m scraper.cli backfill-auto --disable-timer-on-done hltv-backfill.timer
ExecStartPost=$SCRAPER_DIR/.venv/bin/python -m scraper.cli backup --out-dir $SCRAPER_DIR/backups
Nice=10
TimeoutStartSec=3600
EOF

  sudo tee /etc/systemd/system/hltv-backfill.timer >/dev/null <<'EOF'
[Unit]
Description=Continue HLTV historical backfill hourly until complete

[Timer]
OnBootSec=15min
OnUnitActiveSec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

  # Upcoming match discovery: checks /matches every 30 min for live/scheduled
  sudo tee /etc/systemd/system/hltv-upcoming.service >/dev/null <<EOF
[Unit]
Description=HLTV upcoming match discovery
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=$SCRAPER_DIR/.venv/bin/python -m scraper.cli discover-upcoming
Nice=10
TimeoutStartSec=300
EOF

  sudo tee /etc/systemd/system/hltv-upcoming.timer >/dev/null <<'EOF'
[Unit]
Description=Discover upcoming HLTV matches every 30 minutes

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
Persistent=true

[Install]
WantedBy=timers.target
EOF

  # Rankings backfill: fetches missing weekly snapshots, runs daily
  sudo tee /etc/systemd/system/hltv-rankings.service >/dev/null <<EOF
[Unit]
Description=HLTV rankings backfill
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=$SCRAPER_DIR/.venv/bin/python -m scraper.cli backfill-rankings
Nice=10
TimeoutStartSec=1800
EOF

  sudo tee /etc/systemd/system/hltv-rankings.timer >/dev/null <<'EOF'
[Unit]
Description=Backfill HLTV rankings daily

[Timer]
OnBootSec=20min
OnCalendar=*-*-* 04:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

  # Entity scraper: fetches event/team/player pages weekly
  sudo tee /etc/systemd/system/hltv-entities.service >/dev/null <<EOF
[Unit]
Description=HLTV entity pages scraper (events, teams, players)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=/bin/bash -c '$SCRAPER_DIR/.venv/bin/python -m scraper.cli scrape-events --limit 30 && $SCRAPER_DIR/.venv/bin/python -m scraper.cli scrape-teams --limit 30 && $SCRAPER_DIR/.venv/bin/python -m scraper.cli scrape-players --limit 50'
Nice=10
TimeoutStartSec=3600
EOF

  sudo tee /etc/systemd/system/hltv-entities.timer >/dev/null <<'EOF'
[Unit]
Description=Scrape HLTV entity pages weekly

[Timer]
OnBootSec=30min
OnCalendar=Mon *-*-* 05:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

  # Health check: daily validation and report
  sudo tee /etc/systemd/system/hltv-health.service >/dev/null <<EOF
[Unit]
Description=HLTV scraper daily health check and report

[Service]
Type=oneshot
WorkingDirectory=$SCRAPER_DIR
EnvironmentFile=$SCRAPER_DIR/.env
ExecStart=/bin/bash -c '$SCRAPER_DIR/.venv/bin/python -m scraper.cli health && $SCRAPER_DIR/.venv/bin/python -m scraper.cli validate-fixtures --sample 50 && $SCRAPER_DIR/.venv/bin/python -m scraper.cli report --out $SCRAPER_DIR/data/hltv_scraped/report.html && $SCRAPER_DIR/.venv/bin/python -m scraper.cli manifest --out $SCRAPER_DIR/data/hltv_scraped/manifest.json'
Nice=15
EOF

  sudo tee /etc/systemd/system/hltv-health.timer >/dev/null <<'EOF'
[Unit]
Description=HLTV scraper daily health check

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable --now hltv-scraper.timer
  sudo systemctl enable --now hltv-backfill.timer
  sudo systemctl enable --now hltv-upcoming.timer
  sudo systemctl enable --now hltv-rankings.timer
  sudo systemctl enable --now hltv-entities.timer
  sudo systemctl enable --now hltv-health.timer

  echo ""
  echo "==> Active timers:"
  sudo systemctl list-timers 'hltv-*' --no-pager
fi

# ── Log rotation ─────────────────────────────────────────────────────
echo "==> Setting up log rotation for backups"
BACKUP_DIR="$SCRAPER_DIR/backups"
mkdir -p "$BACKUP_DIR"
BACKUP_COUNT=$(find "$BACKUP_DIR" -name '*.tar.gz' 2>/dev/null | wc -l)
if [[ "$BACKUP_COUNT" -gt 14 ]]; then
  echo "   Pruning old backups (keeping last 14)"
  ls -1t "$BACKUP_DIR"/*.tar.gz 2>/dev/null | tail -n +15 | xargs rm -f --
fi

echo ""
echo "==> Install complete"
echo ""
echo "Timers running:"
echo "  hltv-scraper.timer    — discover + fetch every 6h"
echo "  hltv-backfill.timer   — historical backfill every 1h (auto-disables when done)"
echo "  hltv-upcoming.timer   — upcoming match discovery every 30min"
echo "  hltv-rankings.timer   — rankings backfill daily at 04:00"
echo "  hltv-entities.timer   — event/team/player pages weekly on Monday 05:00"
echo "  hltv-health.timer     — health check + report + manifest daily at 06:00"
echo ""
echo "Quick commands:"
echo "  cd $SCRAPER_DIR"
echo "  .venv/bin/python -m scraper.cli status --verbose"
echo "  .venv/bin/python -m scraper.cli health"
echo "  .venv/bin/python -m scraper.cli rankings-status"
echo "  bash deploy/hltv-status.sh"
echo "  journalctl -u hltv-scraper.service -n 50 --no-pager"
echo "  journalctl -u hltv-backfill.service -n 50 --no-pager"
echo "  sudo systemctl start hltv-scraper.service"
