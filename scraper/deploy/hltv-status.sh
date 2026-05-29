#!/usr/bin/env bash
set -euo pipefail

# One-command dashboard for the HLTV scraper on the VPS.
# Usage: bash deploy/hltv-status.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRAPER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRAPER_DIR"

PY=".venv/bin/python"
CLI="$PY -m scraper.cli"

divider() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

divider "QUEUE STATUS"
$CLI status --verbose 2>/dev/null || $CLI status

divider "HEALTH CHECK"
$CLI health || echo "  Health check returned warnings (see above)"

divider "RANKINGS COVERAGE"
$CLI rankings-status

divider "STATS ERRORS"
$CLI stats-errors --limit 50

divider "QUALITY REPORT"
$CLI quality-report --sample 10

divider "FAILED MATCHES"
$CLI failed --limit 10

divider "DISK USAGE"
DATA_DIR="$SCRAPER_DIR/data"
if [[ -d "$DATA_DIR" ]]; then
  du -sh "$DATA_DIR"/* 2>/dev/null || echo "  No data yet"
  echo ""
  df -h "$DATA_DIR" | tail -1 | awk '{print "  Disk: " $3 " used / " $2 " total (" $5 " used) — " $4 " available"}'
else
  echo "  No data directory yet"
fi

BACKUP_DIR="$SCRAPER_DIR/backups"
if [[ -d "$BACKUP_DIR" ]]; then
  BACKUP_COUNT=$(find "$BACKUP_DIR" -name '*.tar.gz' 2>/dev/null | wc -l)
  LATEST_BACKUP=$(ls -1t "$BACKUP_DIR"/*.tar.gz 2>/dev/null | head -1 || echo "none")
  echo "  Backups: $BACKUP_COUNT files, latest: $(basename "${LATEST_BACKUP:-none}")"
fi

divider "SYSTEMD TIMERS"
sudo systemctl list-timers 'hltv-*' --no-pager 2>/dev/null || systemctl list-timers 'hltv-*' --no-pager 2>/dev/null || echo "  No hltv timers found"

divider "RECENT LOGS (last 20 lines per service)"
for svc in hltv-scraper hltv-backfill hltv-upcoming hltv-rankings hltv-entities hltv-health; do
  lines=$(journalctl -u "$svc.service" -n 5 --no-pager 2>/dev/null | grep -v '^\-\-' || true)
  if [[ -n "$lines" ]]; then
    echo "  [$svc]"
    echo "$lines" | sed 's/^/    /'
    echo ""
  fi
done

echo ""
echo "Done. For the full HTML report: $CLI report --out data/hltv_scraped/report.html"
