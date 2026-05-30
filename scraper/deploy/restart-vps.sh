#!/usr/bin/env bash
set -euo pipefail

# Restart all HLTV scraper systemd services and show status.
#
# Usage:
#   bash deploy/restart-vps.sh              # restart timers + kick off a scraper run
#   bash deploy/restart-vps.sh --no-run     # restart timers only, don't start a run

SCRAPER_DIR="/opt/betto/scraper"
START_RUN=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --scraper-dir) SCRAPER_DIR="${2:-}"; shift 2 ;;
    --no-run)      START_RUN=0; shift ;;
    -h|--help)
      echo "Usage: bash deploy/restart-vps.sh [--no-run] [--scraper-dir /path]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

PY="$SCRAPER_DIR/.venv/bin/python"
CLI="$PY -m scraper.cli"

echo "==> Restarting all scraper timers"
for timer in hltv-scraper hltv-backfill hltv-upcoming hltv-rankings hltv-entities hltv-health; do
  if sudo systemctl restart "$timer.timer" 2>/dev/null; then
    echo "   OK  $timer.timer"
  else
    echo "   --  $timer.timer (not found)"
  fi
done

if [[ "$START_RUN" -eq 1 ]]; then
  echo ""
  echo "==> Kicking off a scraper run now"
  sudo systemctl start hltv-scraper.service &
  RUN_PID=$!
  echo "   Started in background (journalctl -u hltv-scraper -f to watch)"
fi

echo ""
echo "==> Timer schedule"
sudo systemctl list-timers 'hltv-*' --no-pager 2>/dev/null || true

echo ""
echo "==> Quick status"
cd "$SCRAPER_DIR"
$CLI activity --days 1 2>/dev/null || $CLI status

echo ""
echo "==> Services restarted"
echo "   Dashboard:  bash deploy/hltv-status.sh"
echo "   Logs:       journalctl -u hltv-scraper -f"
echo "   Activity:   $CLI activity"
