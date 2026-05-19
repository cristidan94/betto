from __future__ import annotations

from pathlib import Path


def list_migrations(root: Path) -> list[Path]:
    migrations_dir = root / "infra" / "migrations"
    if not migrations_dir.exists():
        return []
    return sorted(migrations_dir.glob("*.sql"))

