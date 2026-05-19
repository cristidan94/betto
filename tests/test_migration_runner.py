from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from core.db.migration_runner import apply_migrations


class FakeDb:
    def __init__(self, already_applied: set[str] | None = None) -> None:
        self.already_applied = already_applied or set()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        self.calls.append((sql, params))
        if sql == "SELECT migration_name FROM schema_migrations":
            return [(name,) for name in self.already_applied]
        if sql.startswith("INSERT INTO schema_migrations"):
            self.already_applied.add(str(params[0]))
        return None


class MigrationRunnerTests(unittest.TestCase):
    def test_apply_migrations_runs_unapplied_files_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migrations = root / "infra" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "0002_second.sql").write_text("SELECT 2;", encoding="utf-8")
            (migrations / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            db = FakeDb()

            results = apply_migrations(db, root)

            self.assertEqual([item.migration_name for item in results], ["0001_first.sql", "0002_second.sql"])
            self.assertTrue(all(item.applied for item in results))

    def test_apply_migrations_skips_already_applied_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            migrations = root / "infra" / "migrations"
            migrations.mkdir(parents=True)
            (migrations / "0001_first.sql").write_text("SELECT 1;", encoding="utf-8")
            db = FakeDb({"0001_first.sql"})

            results = apply_migrations(db, root)

            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].applied)


if __name__ == "__main__":
    unittest.main()

