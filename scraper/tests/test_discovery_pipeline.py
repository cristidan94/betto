from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scraper.cli import main
from scraper.backfill import run_backfill
from scraper.config import ScraperConfig
from scraper.discovery import _priority, discover_matches
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

    def test_priority_uses_event_tier_overrides_before_stars(self) -> None:
        self.assertEqual(_priority("CCT Season 3", 5, {"CCT": 2}), 2)
        self.assertEqual(_priority("IEM Cologne", 4, {"IEM Cologne": 1}), 1)
        self.assertEqual(_priority("Unknown Cup", 5, {"CCT": 2}), 1)

    def test_discovery_skips_matches_before_stop_date(self) -> None:
        html = """
        <div class="event-name">IEM Cologne</div>
        <a href="/matches/2371234/navi-vs-faze"><span data-unix="1695686400000"></span>NAVI vs FaZe</a>
        """
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "queue.db")
            config = ScraperConfig(db_path=Path(tmp) / "queue.db", event_allow_list=["IEM"], backfill_stop_date="2023-09-27")
            discovered = discover_matches(FakeFetcher(html), db, config, max_pages=1)  # type: ignore[arg-type]
            row = db.get_match("2371234")
            db.close()

        self.assertEqual(discovered, 0)
        self.assertIsNone(row)

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
        def fake_discover(fetcher, db: TrackingDB, config: ScraperConfig, max_pages: int, **kwargs) -> int:
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

    def test_backfill_cli_passes_page_and_match_limits(self) -> None:
        with patch("scraper.cli.run_pipeline", return_value={"discovered": 0, "fetched": 0}) as run:
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["backfill", "--pages", "25", "--matches", "40"])

        payload = json.loads(buffer.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(payload, {"discovered": 0, "fetched": 0})
        self.assertEqual(run.call_args.kwargs["max_discovery_pages"], 25)
        self.assertEqual(run.call_args.kwargs["max_matches"], 40)

    def test_backfill_auto_persists_cursor_and_discovers_without_network(self) -> None:
        def fake_page(fetcher, db: TrackingDB, config: ScraperConfig, page: int, **kwargs) -> dict:
            if page >= 2:
                return {"ok": True, "page": page, "entries": 0, "allowed": 0, "discovered": 0}
            db.upsert_match(str(page), f"/matches/{page}/a-vs-b", event_name="IEM Cologne", priority_tier=1)
            return {"ok": True, "page": page, "entries": 1, "allowed": 1, "discovered": 1}

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
            with patch("scraper.backfill.discover_page", side_effect=fake_page), patch(
                "scraper.backfill.scrape_one_match", return_value=True
            ):
                result = run_backfill(config, pages_per_run=3, max_matches=0, empty_pages_to_stop=5)
                db = TrackingDB(config.db_path)
                next_page = db.get_int_state("backfill_next_page")
                done = db.get_state("backfill_done", "0")
                db.close()

        self.assertEqual(result["discovered"], 2)
        self.assertEqual(result["pages_scanned"], 3)
        self.assertEqual(next_page, 3)
        self.assertEqual(done, "0")

    def test_backfill_auto_marks_done_after_empty_pages(self) -> None:
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
            with patch(
                "scraper.backfill.discover_page",
                return_value={"ok": True, "page": 0, "entries": 0, "allowed": 0, "discovered": 0},
            ):
                result = run_backfill(config, pages_per_run=2, max_matches=0, empty_pages_to_stop=2)
                db = TrackingDB(config.db_path)
                done = db.get_state("backfill_done", "0")
                db.close()

        self.assertTrue(result["done"])
        self.assertEqual(done, "1")

    def test_backfill_auto_respects_max_page_and_sends_single_done_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = ScraperConfig(
                raw_dir=Path(tmp) / "raw",
                output_dir=Path(tmp) / "out",
                db_path=Path(tmp) / "queue.db",
                min_delay=0,
                max_delay=0,
                quiet_hours_start=0,
                quiet_hours_end=0,
                backfill_max_page=0,
                alert_webhook_url="https://example.invalid/webhook",
            )
            with patch(
                "scraper.backfill.discover_page",
                return_value={"ok": True, "page": 0, "entries": 0, "allowed": 0, "discovered": 0},
            ), patch("scraper.backfill.send_webhook", return_value={"sent": True, "status": 200}) as alert:
                first = run_backfill(config, pages_per_run=2, max_matches=0, empty_pages_to_stop=99)
                second = run_backfill(config, pages_per_run=2, max_matches=0, empty_pages_to_stop=99)

        self.assertTrue(first["done"])
        self.assertTrue(second["done"])
        self.assertEqual(alert.call_count, 1)

    def test_backfill_auto_stops_at_stop_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = ScraperConfig(
                raw_dir=Path(tmp) / "raw",
                output_dir=Path(tmp) / "out",
                db_path=Path(tmp) / "queue.db",
                min_delay=0,
                max_delay=0,
                quiet_hours_start=0,
                quiet_hours_end=0,
                backfill_stop_date="2023-09-27",
            )
            with patch(
                "scraper.backfill.discover_page",
                return_value={"ok": True, "page": 0, "entries": 1, "allowed": 0, "discovered": 0, "oldest_scheduled_at": "2023-09-27T00:00:00+00:00"},
            ):
                result = run_backfill(config, pages_per_run=3, max_matches=0, empty_pages_to_stop=99)

        self.assertTrue(result["done"])
        self.assertEqual(result["pages_scanned"], 1)


if __name__ == "__main__":
    unittest.main()
