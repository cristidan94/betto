#!/usr/bin/env bash
set -euo pipefail

# Pull latest code from git and sync to the scraper working directory.
#
# VPS layout:
#   /opt/betto/repo     — sparse git checkout (source of truth)
#   /opt/betto/scraper  — working directory with .venv, .env, data/
#
# Usage:
#   bash deploy/update-vps.sh
#   bash deploy/update-vps.sh --restart        # also restart services after sync
#   bash deploy/update-vps.sh --skip-tests     # skip test suite
#   bash deploy/update-vps.sh --repo-dir /path --scraper-dir /path

REPO_DIR="/opt/betto/repo"
SCRAPER_DIR="/opt/betto/scraper"
BRANCH="master"
RESTART=0
RUN_TESTS=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)    REPO_DIR="${2:-}"; shift 2 ;;
    --scraper-dir) SCRAPER_DIR="${2:-}"; shift 2 ;;
    --branch)      BRANCH="${2:-}"; shift 2 ;;
    --restart)     RESTART=1; shift ;;
    --skip-tests)  RUN_TESTS=0; shift ;;
    -h|--help)
      echo "Usage: bash deploy/update-vps.sh [--restart] [--skip-tests] [--branch BRANCH]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

echo "==> Pulling latest from origin/$BRANCH"
cd "$REPO_DIR"
git fetch origin "$BRANCH"
git pull --ff-only origin "$BRANCH"
COMMIT=$(git log -1 --format='%h %s')
echo "   HEAD: $COMMIT"

echo ""
echo "==> Syncing scraper files to $SCRAPER_DIR"
rsync -av --delete \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='backups/' \
  --exclude='__pycache__/' \
  --exclude='.pytest_cache/' \
  "$REPO_DIR/scraper/" "$SCRAPER_DIR/"

echo ""
echo "==> Updating Python dependencies"
cd "$SCRAPER_DIR"
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt -q

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo ""
  echo "==> Running tests"
  if .venv/bin/python -m pytest tests/ -x -q --tb=line 2>&1; then
    echo "   All tests passed"
  else
    echo ""
    echo "WARNING: Some tests failed. Check output above." >&2
    read -p "Continue anyway? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
      echo "Aborted." >&2
      exit 1
    fi
  fi
fi

echo ""
echo "==> Running preflight"
.venv/bin/python -m scraper.cli preflight --create-dirs

if [[ "$RESTART" -eq 1 ]]; then
  echo ""
  echo "==> Restarting scraper services"
  bash "$SCRAPER_DIR/deploy/restart-vps.sh"
fi

echo ""
echo "==> Update complete ($COMMIT)"
echo "   Run 'bash deploy/restart-vps.sh' to restart services"
echo "   Run 'bash deploy/hltv-status.sh' for full dashboard"
