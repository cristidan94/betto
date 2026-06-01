from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scraper.models import (
    ScrapedEvent,
    ScrapedMap,
    ScrapedMatch,
    ScrapedPlayer,
    ScrapedPlayerMapStats,
    ScrapedTeam,
    ScrapedVeto,
    match_to_fixture_json,
    write_fixture_json,
)


class ModelTests(unittest.TestCase):
    def test_match_to_fixture_json(self) -> None:
        match = ScrapedMatch(
            hltv_id="100",
            scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            best_of=1,
            status="finished",
            team_a=ScrapedTeam("1", "TeamA"),
            team_b=ScrapedTeam("2", "TeamB"),
            event=ScrapedEvent("10", "Event", stars=5),
            players=(ScrapedPlayer("99", "ace", "1"),),
            maps=(
                ScrapedMap(
                    map_index=1,
                    map_name="Mirage",
                    team_a_score=16,
                    team_b_score=12,
                    winner_hltv_id="1",
                    map_stats_id="555",
                    player_stats=(
                        ScrapedPlayerMapStats(
                            player_hltv_id="99",
                            nickname="ace",
                            team_hltv_id="1",
                            kills=25,
                            deaths=18,
                            adr=88.5,
                            rating=1.32,
                            headshot_pct=52.0,
                            assists=4,
                            first_kills=5,
                            first_deaths=2,
                            kast_pct=75.0,
                            ct_kills=14,
                            ct_deaths=9,
                            t_kills=11,
                            t_deaths=9,
                            clutches_won=1,
                            flash_assists=3,
                            trade_deaths=2,
                        ),
                    ),
                ),
            ),
            vetoes=(ScrapedVeto(1, "1", "ban", "Dust2"),),
        )

        payload = match_to_fixture_json(match)

        self.assertEqual(payload["hltv_id"], "100")
        self.assertEqual(payload["schema_version"], "hltv-fixture-v1")
        self.assertEqual(payload["source"]["name"], "hltv-scraper")
        self.assertEqual(payload["event"]["tier"], 1)
        self.assertEqual(payload["event"]["hltv_stars"], 5)
        self.assertEqual(payload["maps"][0]["map_stats_id"], "555")
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["kills"], 25)
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["first_deaths"], 2)
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["ct_kills"], 14)
        self.assertEqual(payload["maps"][0]["map_stats_id"], "555")
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["flash_assists"], 3)
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["trade_deaths"], 2)

    def test_write_fixture_json(self) -> None:
        match = ScrapedMatch(
            hltv_id="101",
            scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            best_of=1,
            status="scheduled",
            team_a=ScrapedTeam("1", "TeamA"),
            team_b=ScrapedTeam("2", "TeamB"),
            event=ScrapedEvent("10", "Event"),
            players=(),
            maps=(),
            vetoes=(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_fixture_json(match, Path(tmp))

            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
