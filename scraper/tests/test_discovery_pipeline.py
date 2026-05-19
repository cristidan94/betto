from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scraper.config import ScraperConfig
from scraper.discovery import discover_matches
from scraper.fetcher import FetchResult
from scraper.match_scraper import _assemble_match
from scraper.pipeline import run_pipeline
from scraper.tracking_db import TrackingDB


class FakeFetcher:
    def __init__(self, html: str) -> None:
        self.html = html

    def fetch(self, url: str) -> FetchResult:
        return FetchResult(200, self.html, "fake", 1, len(self.html))


class DiscoveryPipelineTests(unittest.TestCase):
    def test_discovery_queues_allowed_matches(self) -> None:
        html = """
        <div class="event-name">IEM Cologne</div>
        <a href="/matches/2371234/navi-vs-faze">NAVI vs FaZe</a>
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "queue.db")
            config = ScraperConfig(db_path=Path(tmp) / "queue.db", event_allow_list=["IEM"])
            discovered = discover_matches(FakeFetcher(html), db, config, max_pages=1)  # type: ignore[arg-type]
            row = db.get_match("2371234")
            db.close()

        self.assertEqual(discovered, 1)
        self.assertIsNotNone(row)

    def test_assemble_match_builds_scraped_model(self) -> None:
        match = _assemble_match(
            {
                "hltv_id": "2371234",
                "scheduled_at": "2026-03-03T12:00:00+00:00",
                "best_of": 1,
                "status": "finished",
                "team_a": {"hltv_id": "4608", "name": "NAVI"},
                "team_b": {"hltv_id": "6667", "name": "FaZe"},
                "event": {"hltv_id": "7148", "name": "IEM", "stars": None},
                "players": [{"hltv_id": "7998", "nickname": "s1mple", "team_hltv_id": "4608"}],
                "maps": [
                    {
                        "map_index": 1,
                        "map_name": "Inferno",
                        "team_a_score": 13,
                        "team_b_score": 9,
                        "winner_hltv_id": "4608",
                        "map_stats_id": "98765",
                    }
                ],
                "vetoes": [{"order_idx": 1, "team_hltv_id": "4608", "action": "ban", "map_name": "Dust2"}],
                "stats_url": None,
            },
            [],
            {"98765": [{"player_hltv_id": "7998", "nickname": "s1mple", "team_hltv_id": "4608"}]},
        )

        self.assertEqual(match.hltv_id, "2371234")
        self.assertEqual(match.maps[0].player_stats[0].nickname, "s1mple")

    def test_run_pipeline_skips_quiet_hours_before_network_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = ScraperConfig(
                raw_dir=Path(tmp) / "raw",
                output_dir=Path(tmp) / "out",
                db_path=Path(tmp) / "queue.db",
                quiet_hours_start=0,
                quiet_hours_end=24,
            )
            with patch("scraper.pipeline.discover_matches") as discover:
                result = run_pipeline(config)

        self.assertEqual(result, {"skipped": True, "reason": "quiet_hours"})
        discover.assert_not_called()

    def test_run_pipeline_discovers_and_fetches_pending_without_network(self) -> None:
        def fake_discover(fetcher, db: TrackingDB, config: ScraperConfig, max_pages: int) -> int:
            db.upsert_match("2371234", "/matches/2371234/navi-vs-faze", event_name="IEM Cologne", priority_tier=1)
            return 1

        def fake_scrape(match_id, match_url, fetcher, db: TrackingDB, limiter, config: ScraperConfig) -> bool:
            db.mark_parsed(match_id)
            return True

        with tempfile.TemporaryDirectory() as tmp:
            config = ScraperConfig(
                raw_dir=Path(tmp) / "raw",
                output_dir=Path(tmp) / "out",
                db_path=Path(tmp) / "queue.db",
                min_delay=0,
                max_delay=0,
                quiet_hours_start=0,
                quiet_hours_end=0,
            )
            with patch("scraper.pipeline.discover_matches", side_effect=fake_discover), patch(
                "scraper.pipeline.scrape_one_match", side_effect=fake_scrape
            ):
                result = run_pipeline(config, max_discovery_pages=1, max_matches=5)

        self.assertEqual(result["discovered"], 1)
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["queue"]["parsed"], 1)


if __name__ == "__main__":
    unittest.main()
