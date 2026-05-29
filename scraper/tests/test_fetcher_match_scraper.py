from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.fetcher import FetchResult, HltvFetcher
from scraper.match_scraper import scrape_one_match
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


MATCH_HTML = """
<html><body>
  <div data-unix="1772539200000"></div>
  <a href="/team/4608/navi">NAVI</a>
  <a href="/team/6667/faze">FaZe</a>
  <a href="/events/7148/iem-katowice">IEM Katowice</a>
  <a href="/player/7998/s1mple">s1mple</a>
  <a href="/player/18053/broky">broky</a>
  <a href="/stats/matches/112345/navi-vs-faze">Stats</a>
  <div>Best of 1</div>
  <div>Inferno 13 - 9 <a href="/stats/matches/mapstatsid/98765/slug">map stats</a></div>
</body></html>
"""

STATS_HTML = """
<table>
  <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>25</td></tr>
  <tr><td><a href="/player/18053/broky">broky</a></td><td>20</td></tr>
</table>
"""

MAP_STATS_HTML = """
<table>
  <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>25 - 18</td><td>5</td><td>88.5</td><td>76.2%</td><td>1.32</td></tr>
</table>
"""

SCHEDULED_MATCH_HTML = """
<html><body>
  <div data-unix="1772539200000"></div>
  <a href="/team/4608/navi">NAVI</a>
  <a href="/team/6667/faze">FaZe</a>
  <a href="/events/7148/iem-katowice">IEM Katowice</a>
  <div>Best of 3</div>
</body></html>
"""


class ScriptedFetcher(HltvFetcher):
    def __init__(self, db: TrackingDB, raw_dir: Path, responses: dict[str, FetchResult]) -> None:
        super().__init__(ProxyRotator(""), RateLimiter(), db, raw_dir)
        self.responses = responses
        self.urls: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.urls.append(url)
        for key, value in self.responses.items():
            if key in url:
                return value
        return FetchResult(404, "missing", "fake", 1, 7)


class FallbackFetcher(HltvFetcher):
    def __init__(self, db: TrackingDB, raw_dir: Path) -> None:
        super().__init__(ProxyRotator(""), RateLimiter(), db, raw_dir)
        self.calls: list[str] = []

    def _fetch_curl(self, url: str) -> FetchResult:
        self.calls.append("curl")
        return FetchResult(403, "Access denied", "curl_cffi", 1, 13)

    def _fetch_playwright(self, url: str) -> FetchResult:
        self.calls.append("playwright")
        return FetchResult(200, "<html>ok</html>", "playwright", 1, 15)


class NoSleepLimiter(RateLimiter):
    def sleep(self) -> None:
        return None


class ClassifyFetchErrorTests(unittest.TestCase):
    def test_timeout_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(0, "connection timeout", "curl_cffi", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "timeout")

    def test_blocked_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(403, "Access denied", "curl_cffi", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "blocked")

    def test_not_found_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(404, "Not found", "curl_cffi", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "not_found")

    def test_rate_limited_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(429, "Too many requests", "curl_cffi", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "rate_limited")

    def test_server_error_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(502, "Bad gateway", "curl_cffi", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "server_error")

    def test_daily_cap_classified(self) -> None:
        from scraper.match_scraper import _classify_fetch_error
        result = FetchResult(0, "daily cap reached", "rate_limiter", 0, 0)
        self.assertEqual(_classify_fetch_error(result), "daily_cap")


class FetcherMatchScraperTests(unittest.TestCase):
    def test_fetch_falls_back_to_playwright_after_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "queue.db")
            fetcher = FallbackFetcher(db, Path(tmp) / "raw")

            result = fetcher.fetch("https://www.hltv.org/matches/2371234/navi-vs-faze")
            fetcher.fetch("https://www.hltv.org/matches/2371234/navi-vs-faze")
            fetcher.fetch("https://www.hltv.org/matches/2371234/navi-vs-faze")
            row_count = db.request_count_today()
            needs_playwright = db.needs_playwright("/matches/2371234")
            db.close()

        self.assertTrue(result.ok)
        self.assertEqual(fetcher.calls, ["curl", "playwright", "curl", "playwright", "curl", "playwright"])
        self.assertEqual(row_count, 0)
        self.assertTrue(needs_playwright)

    def test_fetch_respects_daily_cap_before_network_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = TrackingDB(Path(tmp) / "queue.db")
            fetcher = FallbackFetcher(db, Path(tmp) / "raw")
            fetcher._limiter = RateLimiter(daily_cap=0)

            result = fetcher.fetch("https://www.hltv.org/matches/2371234/navi-vs-faze")
            row_count = db.request_count_today()
            db.close()

        self.assertFalse(result.ok)
        self.assertEqual(result.fetcher_type, "rate_limiter")
        self.assertEqual(fetcher.calls, [])
        self.assertEqual(row_count, 0)

    def test_scrape_one_match_writes_raw_and_fixture_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            db.upsert_match("2371234", "/matches/2371234/navi-vs-faze")
            fetcher = ScriptedFetcher(
                db,
                root / "raw",
                {
                    "/matches/2371234": FetchResult(200, MATCH_HTML, "fake", 1, len(MATCH_HTML)),
                    "/stats/matches/112345": FetchResult(200, STATS_HTML, "fake", 1, len(STATS_HTML)),
                    "mapstatsid/98765": FetchResult(200, MAP_STATS_HTML, "fake", 1, len(MAP_STATS_HTML)),
                },
            )
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            scraped = scrape_one_match("2371234", "/matches/2371234/navi-vs-faze", fetcher, db, NoSleepLimiter(), config)
            row = db.get_match("2371234")
            fixture_path = root / "out" / "2371234.json"
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
            match_raw_exists = (root / "raw" / "matches" / "2371234" / "match.html").exists()
            stats_raw_exists = (root / "raw" / "matches" / "2371234" / "stats.html").exists()
            map_raw_exists = (root / "raw" / "matches" / "2371234" / "map_98765.html").exists()
            db.close()

        self.assertIsNotNone(scraped)
        self.assertTrue(match_raw_exists)
        self.assertTrue(stats_raw_exists)
        self.assertTrue(map_raw_exists)
        assert row is not None
        self.assertEqual(row["match_fetched"], 1)
        self.assertEqual(row["stats_fetched"], 1)
        self.assertEqual(row["maps_fetched"], 1)
        self.assertEqual(row["parsed"], 1)
        self.assertEqual(row["final"], 1)
        self.assertEqual(payload["event"]["tier"], 1)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["kills"], 25)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["deaths"], 18)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["assists"], 5)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["adr"], 88.5)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["kast_pct"], 76.2)
        self.assertEqual(payload["maps"][0]["player_stats"]["s1mple"]["rating"], 1.32)

    def test_stats_error_recorded_when_stats_fetch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            db.upsert_match("2371236", "/matches/2371236/navi-vs-faze")
            fetcher = ScriptedFetcher(
                db,
                root / "raw",
                {
                    "/matches/2371236": FetchResult(200, MATCH_HTML, "fake", 1, len(MATCH_HTML)),
                    "/stats/matches/112345": FetchResult(403, "blocked", "fake", 1, 7),
                    "mapstatsid/98765": FetchResult(403, "blocked", "fake", 1, 7),
                },
            )
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            scrape_one_match("2371236", "/matches/2371236/navi-vs-faze", fetcher, db, NoSleepLimiter(), config)
            row = db.get_match("2371236")
            db.close()

        assert row is not None
        self.assertIsNotNone(row["stats_error"])
        self.assertIn("blocked", row["stats_error"])

    def test_scheduled_match_is_written_but_deferred_for_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            db.upsert_match("2371235", "/matches/2371235/navi-vs-faze")
            fetcher = ScriptedFetcher(
                db,
                root / "raw",
                {"/matches/2371235": FetchResult(200, SCHEDULED_MATCH_HTML, "fake", 1, len(SCHEDULED_MATCH_HTML))},
            )
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            scraped = scrape_one_match("2371235", "/matches/2371235/navi-vs-faze", fetcher, db, NoSleepLimiter(), config)
            row = db.get_match("2371235")
            pending = db.pending_matches(limit=10)
            fixture_path = root / "out" / "2371235.json"
            fixture_exists = fixture_path.exists()
            db.close()

        self.assertIsNotNone(scraped)
        assert scraped is not None
        self.assertEqual(scraped.status, "scheduled")
        self.assertTrue(fixture_exists)
        assert row is not None
        self.assertEqual(row["parsed"], 1)
        self.assertEqual(row["final"], 0)
        self.assertEqual(row["lifecycle_status"], "scheduled")
        self.assertIsNotNone(row["next_attempt_at"])
        self.assertEqual(pending, [])


if __name__ == "__main__":
    unittest.main()
