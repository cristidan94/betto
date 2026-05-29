#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash deploy/update-vps.sh [--project-dir /opt/betto] [--branch master] [--no-start] [--no-logs]

Run from /opt/betto/scraper on the VPS after the scraper is already installed.
The script pulls the latest code, updates dependencies, reparses existing data
with the new parser, runs tests, and restarts services.
EOF
}

PROJECT_DIR="/opt/betto"
BRANCH="master"
START_SERVICE=1
SHOW_LOGS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-dir)
      PROJECT_DIR="${2:-}"
      shift 2
      ;;
    --branch)
      BRANCH="${2:-}"
      shift 2
      ;;
    --no-start)
      START_SERVICE=0
      shift
      ;;
    --no-logs)
      SHOW_LOGS=0
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

SCRAPER_DIR="$PROJECT_DIR/scraper"

if [[ ! -f "$SCRAPER_DIR/.env" ]]; then
  echo "Missing $SCRAPER_DIR/.env. Run install-vps.sh first." >&2
  exit 1
fi

echo "==> Pulling latest code"
cd "$PROJECT_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> Updating Python dependencies"
cd "$SCRAPER_DIR"
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

echo "==> Running tests"
if .venv/bin/python -m pytest tests/ -x -q --tb=line 2>&1; then
  echo "   All tests passed"
else
  echo "WARNING: Some tests failed. Check the output above." >&2
  echo "Continuing anyway — the old code is already replaced by git pull." >&2
fi

echo "==> Running preflight"
.venv/bin/python -m scraper.cli preflight --create-dirs

echo "==> Reparsing existing raw HTML with updated parser"
MATCH_DIR="$SCRAPER_DIR/data/raw/hltv/matches"
if [[ -d "$MATCH_DIR" ]] && [[ "$(ls -A "$MATCH_DIR" 2>/dev/null)" ]]; then
  .venv/bin/python -m scraper.cli reparse-raw
else
  echo "   No raw HTML to reparse yet"
fi

echo "==> Updating systemd units"
bash deploy/install-vps.sh --project-dir "$PROJECT_DIR" --no-systemd 2>/dev/null || true
# Regenerate systemd from install script (the units section)
# Easier to just re-run install with systemd
bash deploy/install-vps.sh --project-dir "$PROJECT_DIR" 2>&1 | grep -E '^\s*(==>|hltv-)' || true

if [[ "$START_SERVICE" -eq 1 ]]; then
  echo "==> Starting scraper services"
  sudo systemctl start hltv-scraper.service || true
fi

echo ""
echo "==> Current status"
.venv/bin/python -m scraper.cli status --verbose
echo ""
.venv/bin/python -m scraper.cli health
echo ""
.venv/bin/python -m scraper.cli rankings-status

if [[ "$SHOW_LOGS" -eq 1 ]]; then
  echo ""
  echo "==> Recent service logs"
  journalctl -u hltv-scraper.service -n 30 --no-pager 2>/dev/null || true
  journalctl -u hltv-backfill.service -n 30 --no-pager 2>/dev/null || true
fi

echo ""
echo "==> Update complete"
echo "   Run 'bash deploy/hltv-status.sh' for a full dashboard"
