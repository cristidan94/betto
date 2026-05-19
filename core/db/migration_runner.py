from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.db.migrations import list_migrations
from core.db.repository import DbExecutor


@dataclass(frozen=True)
class MigrationResult:
    migration_name: str
    applied: bool


def ensure_migration_table(db: DbExecutor) -> None:
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          migration_name TEXT PRIMARY KEY,
          applied_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        (),
    )


def applied_migrations(db: DbExecutor) -> set[str]:
    rows: list[tuple[Any, ...]] = db.execute("SELECT migration_name FROM schema_migrations", ()) or []
    return {str(row[0]) for row in rows}


def apply_migrations(db: DbExecutor, root: Path) -> list[MigrationResult]:
    ensure_migration_table(db)
    already_applied = applied_migrations(db)
    results: list[MigrationResult] = []
    for migration in list_migrations(root):
        name = migration.name
        if name in already_applied:
            results.append(MigrationResult(name, applied=False))
            continue
        db.execute(migration.read_text(encoding="utf-8"), ())
        db.execute("INSERT INTO schema_migrations (migration_name) VALUES (%s)", (name,))
        results.append(MigrationResult(name, applied=True))
    return results
