from __future__ import annotations

import unittest

from sports.cs.normalization.records import CsParsedMap, CsParsedPlayerMapStats, CsParsedVeto
from sports.cs.repository import CsRepository


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))


class CsRepositoryTests(unittest.TestCase):
    def test_upsert_map_result_includes_rich_fields(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        parsed_map = CsParsedMap(
            map_index=1,
            map_name="Dust2",
            team_a_score=13,
            team_b_score=6,
            winner_hltv_id="13644",
            map_stats_id="230451",
            overtime=False,
            team_a_first_half=7,
            team_a_second_half=6,
            team_b_first_half=5,
            team_b_second_half=1,
        )

        repo.upsert_map_result("unit-1", parsed_map)

        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("map_stats_id", sql)
        self.assertIn("overtime", sql)
        self.assertIn("team_a_first_half", sql)
        self.assertEqual(params, ("unit-1", "Dust2", 13, 6, "230451", False, 7, 6, 5, 1))

    def test_upsert_map_result_basic_still_works(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)

        repo.upsert_map_result("unit-1", CsParsedMap(1, "Mirage", 13, 9, "4608"))

        sql, params = db.calls[0]
        self.assertIn("INSERT INTO cs_map_results", sql)
        self.assertEqual(params, ("unit-1", "Mirage", 13, 9, None, None, None, None, None, None))

    def test_upsert_veto_action(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)

        repo.upsert_veto_action("contest-1", CsParsedVeto(1, "4608", "ban", "Nuke"))

        self.assertEqual(len(db.calls), 1)
        self.assertIn("INSERT INTO cs_veto_actions", db.calls[0][0])
        self.assertEqual(db.calls[0][1], ("contest-1", 1, "cs:participant:hltv:4608", "ban", "Nuke"))

    def test_upsert_map_lineup(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)

        repo.upsert_map_lineup("unit-1", "cs:participant:hltv:13644", "cs:participant:hltv:16555")

        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("INSERT INTO cs_map_lineups", sql)
        self.assertEqual(params, ("unit-1", "cs:participant:hltv:13644", "cs:participant:hltv:16555"))

    def test_upsert_player_map_stats(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        stats = CsParsedPlayerMapStats(
            player_hltv_id="16555",
            team_hltv_id="13644",
            kills=19,
            deaths=10,
            assists=None,
            adr=94.6,
            rating=1.77,
            kast_pct=84.2,
            headshot_pct=None,
            first_kills=None,
            first_deaths=2,
            clutches_won=None,
            ct_kills=9,
            ct_deaths=3,
            t_kills=10,
            t_deaths=7,
            flash_assists=None,
            trade_deaths=None,
        )

        repo.upsert_player_map_stats("unit-1", stats)

        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("INSERT INTO cs_player_map_stats", sql)
        self.assertEqual(params[0], "unit-1")
        self.assertEqual(params[1], "cs:participant:hltv:16555")
        self.assertEqual(params[2], "cs:participant:hltv:13644")
        self.assertEqual(params[3], 19)
        self.assertEqual(params[4], 10)
        self.assertIsNone(params[5])
        self.assertAlmostEqual(params[6], 94.6)
        self.assertEqual(params[13], 9)
        self.assertEqual(params[11], 2)
        self.assertEqual(params[16], 7)
        self.assertIsNone(params[17])
        self.assertIsNone(params[18])

    def test_upsert_player_map_stats_all_nulls(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        stats = CsParsedPlayerMapStats(player_hltv_id="1", team_hltv_id="2")

        repo.upsert_player_map_stats("unit-1", stats)

        params = db.calls[0][1]
        self.assertEqual(params[0], "unit-1")
        self.assertIsNone(params[3])


if __name__ == "__main__":
    unittest.main()
