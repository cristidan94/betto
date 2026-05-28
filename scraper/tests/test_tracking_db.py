from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scraper.tracking_db import TrackingDB


class TrackingDbTests(unittest.TestCase):
    def test_queue_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "test.db")
            db.upsert_match("123", "/matches/123/a-vs-b", event_name="IEM", event_stars=5, scheduled_at="2026-05-01")
            db.mark_match_fetched("123")
            db.mark_stats_fetched("123")
            db.set_maps_total("123", 3)
            db.increment_maps_fetched("123")
            db.mark_parsed("123")
            row = db.get_match("123")
            stats = db.queue_stats()
            db.close()

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["event_name"], "IEM")
        self.assertEqual(row["match_fetched"], 1)
        self.assertEqual(row["stats_fetched"], 1)
        self.assertEqual(row["maps_fetched"], 1)
        self.assertEqual(row["parsed"], 1)
        self.assertEqual(row["final"], 1)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["final"], 1)

    def test_pending_errors_requests_and_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "test.db")
            db.upsert_match("1", "/matches/1/a", scheduled_at="2026-05-01", priority_tier=1)
            db.upsert_match("2", "/matches/2/b", scheduled_at="2026-04-01", priority_tier=2)
            db.record_error("2", "HTTP 403")
            db.log_request("/matches/1/a", 200, "curl_cffi", "us", 52000, 310)
            db.record_block("/stats/matches/")
            db.record_block("/stats/matches/")
            db.record_block("/stats/matches/")
            pending = db.pending_matches(limit=10)
            row = db.get_match("2")
            count = db.request_count_today()
            needs_playwright = db.needs_playwright("/stats/matches/123")
            db.close()

        self.assertEqual([item["match_id"] for item in pending], ["1", "2"])
        assert row is not None
        self.assertEqual(row["retry_count"], 1)
        self.assertEqual(count, 1)
        self.assertTrue(needs_playwright)

    def test_deferred_match_is_not_pending_until_due(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "test.db")
            db.upsert_match("1", "/matches/1/a", scheduled_at="2026-05-01", priority_tier=1)
            db.defer_match("1", status="scheduled", delay_seconds=3600)
            pending = db.pending_matches(limit=10)
            row = db.get_match("1")
            stats = db.queue_stats()
            db.close()

        self.assertEqual(pending, [])
        assert row is not None
        self.assertEqual(row["parsed"], 1)
        self.assertEqual(row["final"], 0)
        self.assertEqual(row["lifecycle_status"], "scheduled")
        self.assertIsNotNone(row["next_attempt_at"])
        self.assertEqual(stats["parsed"], 1)
        self.assertEqual(stats["final"], 0)


if __name__ == "__main__":
    unittest.main()
