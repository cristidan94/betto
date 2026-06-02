#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${BETTO_PROJECT_DIR:-$(pwd)}"
DATABASE_URL="${BETTO_DATABASE_URL:-postgresql://betto:betto@localhost:5433/betto}"
PG_VERSION="${BETTO_PG_VERSION:-16}"
PG_CLUSTER="${BETTO_PG_CLUSTER:-main}"
APPLY_MIGRATIONS="${BETTO_APPLY_MIGRATIONS:-0}"
ALLOW_SUDO="${BETTO_ALLOW_SUDO:-0}"
USER_COMMAND="${1:-python -m core.cli.main db-check}"

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

if ! python -c "import psycopg, fastapi, uvicorn, pydantic" >/dev/null 2>&1; then
  echo "[betto] Installing Betto Python runtime dependencies into WSL virtualenv"
  python -m pip install --upgrade pip
  python -m pip install -e .
fi

if command -v pg_lsclusters >/dev/null 2>&1; then
  cluster_line="$(pg_lsclusters --no-header 2>/dev/null | awk -v version="$PG_VERSION" -v cluster="$PG_CLUSTER" '$1 == version && $2 == cluster {print}')"
  if [ -n "$cluster_line" ]; then
    cluster_port="$(printf '%s\n' "$cluster_line" | awk '{print $3}')"
    cluster_status="$(printf '%s\n' "$cluster_line" | awk '{print $4}')"
    echo "[betto] Postgres cluster $PG_VERSION/$PG_CLUSTER is $cluster_status on port $cluster_port"
    if [ "$cluster_status" != "online" ]; then
      if [ "$ALLOW_SUDO" = "1" ]; then
        echo "[betto] Starting Postgres cluster $PG_VERSION/$PG_CLUSTER"
        sudo pg_ctlcluster "$PG_VERSION" "$PG_CLUSTER" start
      else
        echo "[betto] Postgres is not online. Start it once in WSL or rerun with AllowSudo from an interactive terminal." >&2
        exit 1
      fi
    fi
  else
    echo "[betto] Postgres cluster $PG_VERSION/$PG_CLUSTER was not found." >&2
    exit 1
  fi
else
  echo "[betto] pg_lsclusters not found; cannot verify WSL Postgres cluster." >&2
  exit 1
fi

export BETTO_DATABASE_URL="$DATABASE_URL"

echo "[betto] Checking database"
python -m core.cli.main db-check

if [ "$APPLY_MIGRATIONS" = "1" ]; then
  echo "[betto] Applying migrations"
  python -m core.cli.main db-apply-migrations
fi

echo "[betto] Running: $USER_COMMAND"
bash -lc "$USER_COMMAND"
