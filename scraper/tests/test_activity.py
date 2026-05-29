from __future__ import annotations

import json
import sqlite3
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scraper.activity import collect_activity, format_activity
from scraper.config import ScraperConfig


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _days_ago_iso(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class ActivityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path("data/_test_activity")
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.db_path = self.tmp / "test.db"
        self.output_dir = self.tmp / "output"
        self.output_dir.mkdir(exist_ok=True)
        self.raw_dir = self.tmp / "raw" / "hltv"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.config = ScraperConfig(
            db_path=self.db_path,
            output_dir=self.output_dir,
            raw_dir=self.raw_dir,
        )
        self._create_tables()

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create_tables(self) -> None:
        con = sqlite3.connect(str(self.db_path))
        con.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_queue (
              match_id TEXT PRIMARY KEY,
              match_url TEXT NOT NULL,
              event_name TEXT,
              event_stars INTEGER,
              scheduled_at TEXT,
              priority_tier INTEGER NOT NULL DEFAULT 9,
              match_fetched INTEGER NOT NULL DEFAULT 0,
              stats_fetched INTEGER NOT NULL DEFAULT 0,
              maps_total INTEGER NOT NULL DEFAULT 0,
              maps_fetched INTEGER NOT NULL DEFAULT 0,
              parsed INTEGER NOT NULL DEFAULT 0,
              lifecycle_status TEXT,
              final INTEGER NOT NULL DEFAULT 0,
              next_attempt_at TEXT,
              completed_at TEXT,
              retry_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              stats_error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS request_log (
              request_id INTEGER PRIMARY KEY AUTOINCREMENT,
              requested_at TEXT NOT NULL,
              url TEXT NOT NULL,
              status INTEGER NOT NULL,
              fetcher_type TEXT NOT NULL,
              proxy_region TEXT,
              content_bytes INTEGER NOT NULL,
              elapsed_ms INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS scraper_state (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
        """)
        con.close()

    def _insert_request(self, status: int = 200, fetcher_type: str = "httpx", days_ago: int = 0) -> None:
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            "INSERT INTO request_log (requested_at, url, status, fetcher_type, proxy_region, content_bytes, elapsed_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_days_ago_iso(days_ago), "https://hltv.org/test", status, fetcher_type, "us", 1024, 500),
        )
        con.commit()
        con.close()

    def _insert_match(self, match_id: str, final: bool = False, completed_at: str | None = None, days_ago: int = 0) -> None:
        con = sqlite3.connect(str(self.db_path))
        con.execute(
            """INSERT INTO scrape_queue (match_id, match_url, event_name, final, lifecycle_status, completed_at, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (match_id, f"/matches/{match_id}", "Test Event", 1 if final else 0,
             "finished" if final else "scheduled", completed_at, _days_ago_iso(days_ago), _days_ago_iso(days_ago)),
        )
        con.commit()
        con.close()

    def test_empty_db(self) -> None:
        data = collect_activity(self.config, days=7)
        self.assertEqual(data["period_days"], 7)
        self.assertEqual(data["matches_discovered"]["count"], 0)
        self.assertEqual(data["matches_finalized"]["count"], 0)

    def test_requests_counted(self) -> None:
        self._insert_request(status=200, days_ago=0)
        self._insert_request(status=200, days_ago=0)
        self._insert_request(status=403, days_ago=0)
        data = collect_activity(self.config, days=7)
        total = sum(d["total"] for d in data["requests_by_day"])
        self.assertEqual(total, 3)

    def test_matches_discovered(self) -> None:
        self._insert_match("111", days_ago=1)
        self._insert_match("222", days_ago=2)
        self._insert_match("333", days_ago=10)
        data = collect_activity(self.config, days=7)
        self.assertEqual(data["matches_discovered"]["count"], 2)

    def test_matches_finalized(self) -> None:
        self._insert_match("444", final=True, completed_at=_days_ago_iso(1), days_ago=3)
        data = collect_activity(self.config, days=7)
        self.assertEqual(data["matches_finalized"]["count"], 1)

    def test_format_produces_text(self) -> None:
        self._insert_request(status=200, days_ago=0)
        self._insert_match("555", days_ago=0)
        data = collect_activity(self.config, days=7)
        text = format_activity(data)
        self.assertIn("HLTV Scraper Activity", text)
        self.assertIn("REQUESTS BY DAY", text)
        self.assertIn("MATCHES DISCOVERED", text)

    def test_json_output_is_valid(self) -> None:
        data = collect_activity(self.config, days=7)
        serialized = json.dumps(data, default=str)
        parsed = json.loads(serialized)
        self.assertIn("period_days", parsed)

    def test_requests_by_type(self) -> None:
        self._insert_request(fetcher_type="httpx", days_ago=0)
        self._insert_request(fetcher_type="playwright", days_ago=0)
        self._insert_request(fetcher_type="httpx", days_ago=0)
        data = collect_activity(self.config, days=7)
        self.assertEqual(data["requests_by_type"]["httpx"], 2)
        self.assertEqual(data["requests_by_type"]["playwright"], 1)


if __name__ == "__main__":
    unittest.main()
