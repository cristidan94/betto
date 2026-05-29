from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.fetcher import FetchResult, HltvFetcher
from scraper.proxy import ProxyRotator
from scraper.rankings import (
    parse_ranking_page,
    rankings_status,
    scrape_rankings,
    scrape_rankings_range,
)
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


RANKING_HTML = """
<html><body>
<div class="ranked-team">
  <span class="position">#1</span>
  <a href="/team/4608/navi"><span class="name">Natus Vincere</span></a>
  <span class="points">(1000 points)</span>
</div>
<div class="ranked-team">
  <span class="position">#2</span>
  <a href="/team/6667/faze"><span class="name">FaZe</span></a>
  <span class="points">(890 points)</span>
</div>
<div class="ranked-team">
  <span class="position">#3</span>
  <a href="/team/5995/g2"><span class="name">G2</span></a>
  <span class="points">(750 points)</span>
</div>
</body></html>
"""

RANKING_HTML_FALLBACK = """
<html><body>
#1 <a href="/team/4608/navi">NAVI</a> 1000 points
#2 <a href="/team/6667/faze">FaZe</a> 890 points
</body></html>
"""


class ScriptedFetcher(HltvFetcher):
    def __init__(self, db: TrackingDB, raw_dir: Path, responses: dict[str, FetchResult]) -> None:
        super().__init__(ProxyRotator(""), RateLimiter(), db, raw_dir)
        self.responses = responses

    def fetch(self, url: str) -> FetchResult:
        for key, value in self.responses.items():
            if key in url:
                return value
        return FetchResult(404, "missing", "fake", 1, 7)


class NoSleepLimiter(RateLimiter):
    def sleep(self) -> None:
        return None


class ParseRankingTests(unittest.TestCase):
    def test_parse_ranking_page_bs4(self) -> None:
        teams = parse_ranking_page(RANKING_HTML)
        self.assertEqual(len(teams), 3)
        self.assertEqual(teams[0]["rank"], 1)
        self.assertEqual(teams[0]["name"], "Natus Vincere")
        self.assertEqual(teams[0]["team_hltv_id"], "4608")
        self.assertEqual(teams[0]["points"], 1000)
        self.assertEqual(teams[1]["rank"], 2)
        self.assertEqual(teams[1]["name"], "FaZe")
        self.assertEqual(teams[2]["team_hltv_id"], "5995")

    def test_parse_ranking_fallback(self) -> None:
        teams = parse_ranking_page(RANKING_HTML_FALLBACK)
        self.assertGreaterEqual(len(teams), 2)
        self.assertEqual(teams[0]["team_hltv_id"], "4608")
        self.assertEqual(teams[1]["team_hltv_id"], "6667")


class ScrapeRankingsTests(unittest.TestCase):
    def test_scrape_rankings_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {"ranking/teams": FetchResult(200, RANKING_HTML, "fake", 1, len(RANKING_HTML))})
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            result = scrape_rankings(fetcher, NoSleepLimiter(), config, date(2026, 5, 26))
            json_path = root / "raw" / "rankings" / "2026-05-26.json"
            exists = json_path.exists()
            data = json.loads(json_path.read_text(encoding="utf-8")) if exists else None
            db.close()

        self.assertEqual(result["status"], "ok")
        self.assertTrue(exists)
        self.assertEqual(data["date"], "2026-05-26")
        self.assertEqual(len(data["teams"]), 3)

    def test_scrape_rankings_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {"ranking/teams": FetchResult(200, RANKING_HTML, "fake", 1, len(RANKING_HTML))})
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")
            out_dir = root / "raw" / "rankings"
            out_dir.mkdir(parents=True)
            (out_dir / "2026-05-26.json").write_text("{}", encoding="utf-8")

            result = scrape_rankings(fetcher, NoSleepLimiter(), config, date(2026, 5, 26))
            db.close()

        self.assertEqual(result["status"], "skipped")

    def test_scrape_rankings_range(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {"ranking/teams": FetchResult(200, RANKING_HTML, "fake", 1, len(RANKING_HTML))})
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            results = scrape_rankings_range(fetcher, NoSleepLimiter(), config, date(2026, 5, 12), date(2026, 5, 26))
            db.close()

        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["status"] == "ok" for r in results))


class RankingsStatusTests(unittest.TestCase):
    def test_rankings_status_reports_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            status = rankings_status(config, date(2026, 5, 12))

        self.assertEqual(status["start_date"], "2026-05-12")
        self.assertGreater(status["expected"], 0)
        self.assertEqual(status["existing"], 0)
        self.assertEqual(status["missing"], status["expected"])

    def test_rankings_status_counts_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")
            out_dir = root / "raw" / "rankings"
            out_dir.mkdir(parents=True)
            (out_dir / "2026-05-12.json").write_text("{}", encoding="utf-8")
            (out_dir / "2026-05-19.json").write_text("{}", encoding="utf-8")

            status = rankings_status(config, date(2026, 5, 12))

        self.assertEqual(status["existing"], 2)
        self.assertGreater(status["coverage_pct"], 0)


if __name__ == "__main__":
    unittest.main()
