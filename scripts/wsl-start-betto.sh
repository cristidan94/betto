#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${BETTO_PROJECT_DIR:-$(pwd)}"
DATABASE_URL="${BETTO_DATABASE_URL:-postgresql://betto:betto@localhost:5433/betto}"
PG_VERSION="${BETTO_PG_VERSION:-16}"
PG_CLUSTER="${BETTO_PG_CLUSTER:-main}"
SKIP_MIGRATIONS="${BETTO_SKIP_MIGRATIONS:-0}"
NO_SHELL="${BETTO_NO_SHELL:-0}"

cd "$PROJECT_DIR"

echo "[betto] Project: $(pwd)"
echo "[betto] Database: $DATABASE_URL"

if ! command -v python3 >/dev/null 2>&1; then
  echo "[betto] python3 is required inside WSL." >&2
  exit 1
fi

if [ ! -f ".betto/wsl-venv/bin/activate" ]; then
  echo "[betto] Creating WSL virtualenv at .betto/wsl-venv"
  python3 -m venv .betto/wsl-venv || {
    echo "[betto] Could not create venv. Try: sudo apt install -y python3.12-venv" >&2
    exit 1
  }
fi

# shellcheck disable=SC1091
source .betto/wsl-venv/bin/activate

if ! python -c "import psycopg" >/dev/null 2>&1; then
  echo "[betto] Installing psycopg into WSL virtualenv"
  python -m pip install --upgrade pip
  python -m pip install "psycopg[binary]"
fi

if command -v pg_lsclusters >/dev/null 2>&1; then
  cluster_line="$(pg_lsclusters --no-header 2>/dev/null | awk -v version="$PG_VERSION" -v cluster="$PG_CLUSTER" '$1 == version && $2 == cluster {print}')"
  if [ -n "$cluster_line" ]; then
    cluster_port="$(printf '%s\n' "$cluster_line" | awk '{print $3}')"
    cluster_status="$(printf '%s\n' "$cluster_line" | awk '{print $4}')"
    echo "[betto] Postgres cluster $PG_VERSION/$PG_CLUSTER is $cluster_status on port $cluster_port"
    if [ "$cluster_status" != "online" ]; then
      echo "[betto] Starting Postgres cluster $PG_VERSION/$PG_CLUSTER"
      sudo pg_ctlcluster "$PG_VERSION" "$PG_CLUSTER" start
    fi
  else
    echo "[betto] Postgres cluster $PG_VERSION/$PG_CLUSTER was not found. Skipping cluster start."
  fi
else
  echo "[betto] pg_lsclusters not found. Trying sudo service postgresql start."
  sudo service postgresql start || true
fi

export BETTO_DATABASE_URL="$DATABASE_URL"

echo "[betto] Checking database"
python -m core.cli.main db-check

if [ "$SKIP_MIGRATIONS" != "1" ]; then
  echo "[betto] Applying migrations"
  python -m core.cli.main db-apply-migrations
fi

echo "[betto] Ready. BETTO_DATABASE_URL is exported in this shell."

if [ "$NO_SHELL" != "1" ]; then
  exec bash -i
fi
