from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.entity_scraper import scrape_events, scrape_players, scrape_teams
from scraper.fetcher import FetchResult, HltvFetcher
from scraper.parser import parse_event_page, parse_player_page, parse_team_page
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


EVENT_HTML = """
<html><body>
  <h1 class="event-hub-title">IEM Katowice 2026</h1>
  <div class="flag-align"><span class="text-ellipsis">Katowice, Poland</span></div>
  <div class="event-world-ranking"><img class="flag" alt="Poland" /></div>
  <div>LAN</div>
  <div class="prizepool">$1,000,000</div>
  <div class="teamsNumber">24</div>
  <div class="format-value">Group stage into playoffs</div>
  <div data-unix="1740000000000">Start</div>
  <div data-unix="1740500000000">End</div>
  <a href="/team/4608/navi">NAVI</a>
  <a href="/team/6667/faze">FaZe</a>
</body></html>
"""

TEAM_HTML = """
<html><body>
  <h1 class="profile-team-name">NAVI</h1>
  <div class="team-country"><img class="flag" alt="Ukraine" /></div>
  <div class="profile-team-stat"><span class="right">#3</span></div>
  <div class="profile-team-coach"><a href="/player/8000/b1ad3">b1ad3</a></div>
  <div class="players-table">
    <a href="/player/7998/s1mple">s1mple</a>
    <a href="/player/18053/jl">jL</a>
    <a href="/player/16069/im">iM</a>
    <a href="/player/20127/npl">npl</a>
    <a href="/player/13249/aleksib">Aleksib</a>
  </div>
  <div>Mirage 42 / 60 Inferno 30 / 50</div>
  <a href="/matches/2371234/navi-vs-faze">2 - 1 <span class="team-name">FaZe</span> <span class="event-name">IEM</span></a>
  <a href="/matches/2371235/navi-vs-g2">0 - 2 <span class="team-name">G2</span></a>
</body></html>
"""

PLAYER_HTML = """
<html><body>
  <h1 class="playerNickname">s1mple</h1>
  <div class="playerRealname"><img class="flag" alt="Ukraine" /> Oleksandr Kostyliev</div>
  <div class="playerAge"><span class="listRight">28 years</span></div>
  <div class="playerTeam"><a href="/team/4608/navi">NAVI</a></div>
  <div>Rating 2.0 1.25 DPR 0.62 KAST 73.5 Impact 1.31 ADR 82.4 KPR 0.85 HS 42.3% Maps played 1500</div>
  <div>Mirage 25 / 40 Inferno 20 / 30</div>
  <div><a href="/stats/matches/mapstatsid/98765/slug">Inferno 25 - 18 1.32</a></div>
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


class ParseEventPageTests(unittest.TestCase):
    def test_parse_event_page_extracts_fields(self) -> None:
        data = parse_event_page(EVENT_HTML, "7148")
        self.assertEqual(data["hltv_id"], "7148")
        self.assertEqual(data["name"], "IEM Katowice 2026")
        self.assertEqual(data["location"], "Katowice, Poland")
        self.assertEqual(data["country"], "Poland")
        self.assertTrue(data["lan"])
        self.assertEqual(data["prize_pool"], "$1,000,000")
        self.assertEqual(data["team_count"], 24)
        self.assertIsNotNone(data["dates"]["start"])
        self.assertEqual(len(data["teams"]), 2)

    def test_parse_event_page_minimal_html(self) -> None:
        data = parse_event_page("<html><body></body></html>", "999")
        self.assertEqual(data["hltv_id"], "999")
        self.assertIsNotNone(data["name"])


class ParseTeamPageTests(unittest.TestCase):
    def test_parse_team_page_extracts_fields(self) -> None:
        data = parse_team_page(TEAM_HTML, "4608")
        self.assertEqual(data["hltv_id"], "4608")
        self.assertEqual(data["name"], "NAVI")
        self.assertEqual(data["country"], "Ukraine")
        self.assertEqual(data["world_ranking"], 3)
        self.assertIsNotNone(data["coach"])
        self.assertEqual(data["coach"]["nickname"], "b1ad3")
        self.assertEqual(len(data["roster"]), 5)
        self.assertTrue(len(data["map_stats"]) >= 1)
        self.assertIsInstance(data["recent_results"], list)
        self.assertTrue(len(data["recent_results"]) >= 2)
        self.assertEqual(data["recent_results"][0]["match_id"], "2371234")

    def test_parse_team_page_minimal_html(self) -> None:
        data = parse_team_page("<html><body></body></html>", "999")
        self.assertEqual(data["hltv_id"], "999")


class ParsePlayerPageTests(unittest.TestCase):
    def test_parse_player_page_extracts_fields(self) -> None:
        data = parse_player_page(PLAYER_HTML, "7998")
        self.assertEqual(data["hltv_id"], "7998")
        self.assertEqual(data["nickname"], "s1mple")
        self.assertEqual(data["country"], "Ukraine")
        self.assertEqual(data["age"], 28)
        self.assertIsNotNone(data["team"])
        self.assertEqual(data["team"]["name"], "NAVI")
        self.assertEqual(data["rating"], 1.25)
        self.assertEqual(data["adr"], 82.4)
        self.assertEqual(data["maps_played"], 1500)
        self.assertIsInstance(data["per_map_stats"], list)
        self.assertTrue(len(data["per_map_stats"]) >= 2)
        self.assertIsInstance(data["recent_form"], list)
        self.assertTrue(len(data["recent_form"]) >= 1)
        self.assertEqual(data["recent_form"][0]["map_stats_id"], "98765")

    def test_parse_player_page_minimal_html(self) -> None:
        data = parse_player_page("<html><body></body></html>", "999")
        self.assertEqual(data["hltv_id"], "999")


class ScrapeEventsTests(unittest.TestCase):
    def test_scrape_events_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {
                "/events/7148": FetchResult(200, EVENT_HTML, "fake", 1, len(EVENT_HTML)),
            })
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            result = scrape_events(fetcher, db, NoSleepLimiter(), config, event_ids=["7148"])
            json_path = root / "raw" / "events" / "7148.json"
            raw_path = root / "raw" / "events" / "7148" / "event.html"

            self.assertEqual(result["scraped"], 1)
            self.assertTrue(json_path.exists())
            self.assertTrue(raw_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "IEM Katowice 2026")
            fetcher.close()
            db.close()

    def test_scrape_events_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {})
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")
            (root / "raw" / "events").mkdir(parents=True)
            (root / "raw" / "events" / "7148.json").write_text("{}", encoding="utf-8")

            result = scrape_events(fetcher, db, NoSleepLimiter(), config, event_ids=["7148"])

            self.assertEqual(result["skipped"], 1)
            self.assertEqual(result["scraped"], 0)
            fetcher.close()
            db.close()


class ScrapeTeamsTests(unittest.TestCase):
    def test_scrape_teams_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {
                "/team/4608": FetchResult(200, TEAM_HTML, "fake", 1, len(TEAM_HTML)),
            })
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            result = scrape_teams(fetcher, db, NoSleepLimiter(), config, team_ids=["4608"])
            json_path = root / "raw" / "teams" / "4608.json"

            self.assertEqual(result["scraped"], 1)
            self.assertTrue(json_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "NAVI")
            fetcher.close()
            db.close()


class ScrapePlayersTests(unittest.TestCase):
    def test_scrape_players_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = TrackingDB(root / "queue.db")
            fetcher = ScriptedFetcher(db, root / "raw", {
                "/player/7998": FetchResult(200, PLAYER_HTML, "fake", 1, len(PLAYER_HTML)),
            })
            config = ScraperConfig(raw_dir=root / "raw", output_dir=root / "out", db_path=root / "queue.db")

            result = scrape_players(fetcher, db, NoSleepLimiter(), config, player_ids=["7998"])
            json_path = root / "raw" / "players" / "7998.json"

            self.assertEqual(result["scraped"], 1)
            self.assertTrue(json_path.exists())
            data = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(data["nickname"], "s1mple")
            fetcher.close()
            db.close()


class CollectIdsFromFixturesTests(unittest.TestCase):
    def test_collect_event_ids_from_fixtures(self) -> None:
        from scraper.entity_scraper import _collect_event_ids
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            fixture = {"event": {"hltv_id": "7148", "name": "IEM"}}
            (root / "100.json").write_text(json.dumps(fixture), encoding="utf-8")
            ids = _collect_event_ids(root)
        self.assertEqual(ids, ["7148"])

    def test_collect_team_ids_from_fixtures(self) -> None:
        from scraper.entity_scraper import _collect_team_ids
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = {"team_a": {"hltv_id": "4608"}, "team_b": {"hltv_id": "6667"}}
            (root / "100.json").write_text(json.dumps(fixture), encoding="utf-8")
            ids = _collect_team_ids(root)
        self.assertIn("4608", ids)
        self.assertIn("6667", ids)

    def test_collect_player_ids_from_fixtures(self) -> None:
        from scraper.entity_scraper import _collect_player_ids
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = {"players": [{"hltv_id": "7998"}, {"hltv_id": "18053"}]}
            (root / "100.json").write_text(json.dumps(fixture), encoding="utf-8")
            ids = _collect_player_ids(root)
        self.assertIn("7998", ids)
        self.assertIn("18053", ids)


if __name__ == "__main__":
    unittest.main()
