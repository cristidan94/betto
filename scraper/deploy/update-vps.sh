#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash deploy/update-vps.sh [--project-dir /opt/betto] [--branch master] [--no-start] [--no-logs]

Run from /opt/betto/scraper on the VPS after the scraper is already cloned from Git.
The script pulls the latest code, runs the installer, optionally starts one scrape,
and tails the service logs.
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

if [[ ! -d "$SCRAPER_DIR/.git" ]]; then
  echo "Expected a Git clone at $SCRAPER_DIR" >&2
  echo "Clone the scraper first, then rerun this script." >&2
  exit 1
fi

if [[ ! -f "$SCRAPER_DIR/.env" ]]; then
  echo "Missing $SCRAPER_DIR/.env. Refusing to deploy without proxy credentials." >&2
  exit 1
fi

echo "==> Pulling latest code"
cd "$SCRAPER_DIR"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

echo "==> Installing/updating scraper"
bash deploy/install-vps.sh --project-dir "$PROJECT_DIR"

if [[ "$START_SERVICE" -eq 1 ]]; then
  echo "==> Starting one scraper run"
  sudo systemctl start hltv-scraper.service
fi

echo "==> Scraper status"
.venv/bin/python -m scraper.cli status

if [[ "$SHOW_LOGS" -eq 1 ]]; then
  echo "==> Recent service logs"
  journalctl -u hltv-scraper.service -n 100 --no-pager
fi

echo "==> Done"
