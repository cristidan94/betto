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
                    1,
                    "Mirage",
                    16,
                    12,
                    "1",
                    "555",
                    (
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
                        ),
                    ),
                ),
            ),
            vetoes=(ScrapedVeto(1, "1", "ban", "Dust2"),),
        )

        payload = match_to_fixture_json(match)

        self.assertEqual(payload["hltv_id"], "100")
        self.assertEqual(payload["source"]["name"], "hltv-scraper")
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["kills"], 25)
        self.assertEqual(payload["maps"][0]["player_stats"]["ace"]["ct_kills"], 14)

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
