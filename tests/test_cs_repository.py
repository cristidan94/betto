from __future__ import annotations

import unittest

from sports.cs.normalization.records import CsParsedMap, CsParsedVeto
from sports.cs.repository import CsRepository


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))


class CsRepositoryTests(unittest.TestCase):
    def test_upserts_map_result_and_veto_action(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)

        repo.upsert_map_result("unit-1", CsParsedMap(1, "Mirage", 13, 9, "4608"))
        repo.upsert_veto_action("contest-1", CsParsedVeto(1, "4608", "ban", "Nuke"))

        self.assertEqual(len(db.calls), 2)
        self.assertIn("INSERT INTO cs_map_results", db.calls[0][0])
        self.assertEqual(db.calls[0][1], ("unit-1", "Mirage", 13, 9))
        self.assertIn("INSERT INTO cs_veto_actions", db.calls[1][0])
        self.assertEqual(db.calls[1][1], ("contest-1", 1, "cs:participant:hltv:4608", "ban", "Nuke"))


if __name__ == "__main__":
    unittest.main()

