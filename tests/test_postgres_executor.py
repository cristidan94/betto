from __future__ import annotations

import unittest

from core.db.postgres import PostgresExecutor


class PostgresExecutorTests(unittest.TestCase):
    def test_execute_requires_context_manager(self) -> None:
        executor = PostgresExecutor("postgresql://example")

        with self.assertRaises(RuntimeError):
            executor.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()

