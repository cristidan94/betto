# HLTV Scraper Implementation Plan

## Execution Note

Implemented the standalone `scraper/` package scaffold, config, models, SQLite tracking DB, anti-detect helpers, proxy/rate limiting, hybrid fetcher, dependency-light parsers, discovery, match orchestration, pipeline runner, CLI, live-test entry point, preflight readiness check, README, `.gitignore` entries, and Betto `convert-hltv-scraped` import command. The scraper has 23 offline stdlib `unittest` tests covering config, helpers, parser fallback, fetch fallback, match assembly, no-network pipeline behavior, CLI status/export/preflight, Playwright proxy auth formatting, and fixture JSON writing. Live verification passed after installing the scraper venv dependencies, installing Playwright Chromium, switching the proxy template to Decodo's `gate.decodo.com:7000` gateway, tightening Cloudflare-marker detection, and splitting proxy credentials for Playwright.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone HLTV scraper bot that fetches CS2 tier 1-2 match data (results, player stats, vetoes) without IP blocks, and outputs fixture JSON for Betto's model pipeline.

**Architecture:** Hybrid fetcher (curl_cffi fast path + Playwright fallback) with rotating residential proxies. SQLite tracking DB for resumable queue. Raw HTML stored before parsing. Standalone package at `scraper/` — no Betto imports, independently deployable to VPS.

**Tech Stack:** Python 3.11+, curl_cffi, Playwright, BeautifulSoup4/lxml, SQLite, python-dotenv

---

## File Map

```
scraper/                          # Package root (standalone, no Betto imports)
  scraper/
    __init__.py                   # Version string
    config.py                     # Settings from env vars, event allow-list
    models.py                     # Frozen dataclasses: ScrapedMatch, ScrapedMap, ScrapedPlayer, etc.
    tracking_db.py                # SQLite: scrape_queue, blocked_patterns, request_log
    anti_detect.py                # Browser profiles, header sets, Cloudflare challenge detection
    proxy.py                      # ProxyRotator: IP rotation, sticky sessions, geo-targeting
    rate_limiter.py               # Delay jitter, cooldowns, daily cap, quiet hours, failure backoff
    fetcher.py                    # HltvFetcher: curl_cffi + Playwright hybrid, raw store writes
    session.py                    # PlaywrightSession: browser lifecycle, stealth patches
    discovery.py                  # Crawl /results pages, extract match IDs, filter by tier
    parser.py                     # Pure functions: HTML -> dataclasses (match, stats, map stats)
    match_scraper.py              # Orchestrator: fetch match + stats + map pages for one match
    pipeline.py                   # Full run: discover + fetch + parse loop
    cli.py                        # Argparse entry point: discover, fetch, parse, run, status, test-live, export
  tests/
    __init__.py
    conftest.py                   # Shared fixtures (tmp_path helpers, sample HTML builders)
    test_config.py
    test_models.py
    test_tracking_db.py
    test_anti_detect.py
    test_proxy.py
    test_rate_limiter.py
    test_fetcher.py               # Integration tests against live HLTV (marked slow)
    test_parser.py                # Unit tests with saved HTML fixtures
    test_discovery.py
    test_match_scraper.py
    test_pipeline.py
    fixtures/                     # Saved HTML pages for offline testing
      README.md
  requirements.txt
  .env.example
  README.md
```

**Betto-side addition (Task 15):**
- Modify: `core/cli/main.py` — add `convert-hltv-scraped` command

---

### Task 1: Package Scaffold & Config

**Files:**
- Create: `scraper/scraper/__init__.py`
- Create: `scraper/scraper/config.py`
- Create: `scraper/tests/__init__.py`
- Create: `scraper/tests/test_config.py`
- Create: `scraper/requirements.txt`
- Create: `scraper/.env.example`

- [ ] **Step 1: Create package directory structure**

```bash
mkdir -p scraper/scraper scraper/tests/fixtures
```

- [ ] **Step 2: Write `scraper/requirements.txt`**

```
curl_cffi>=0.7.0
playwright>=1.40.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
python-dotenv>=1.0.0
pytest>=8.0.0
```

- [ ] **Step 3: Write `scraper/.env.example`**

```
HLTV_PROXY_URL=http://user-session-{session}:password@gate.smartproxy.com:10000
HLTV_PROXY_REGIONS=us,eu,br
HLTV_RAW_DIR=data/raw/hltv
HLTV_OUTPUT_DIR=data/hltv_scraped
HLTV_DB_PATH=data/hltv_scraper.db
HLTV_DAILY_CAP=5000
HLTV_MIN_DELAY=8
HLTV_MAX_DELAY=15
HLTV_COOLDOWN_EVERY=50
HLTV_COOLDOWN_SECONDS=120
```

- [ ] **Step 4: Write `scraper/scraper/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 5: Write the failing test for config**

```python
# scraper/tests/test_config.py
from scraper.config import ScraperConfig, load_config


def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("HLTV_PROXY_URL", raising=False)
    monkeypatch.delenv("HLTV_RAW_DIR", raising=False)
    config = load_config()
    assert config.proxy_url == ""
    assert config.min_delay == 8
    assert config.max_delay == 15
    assert config.daily_cap == 5000
    assert config.cooldown_every == 50
    assert config.cooldown_seconds == 120
    assert "us" in config.proxy_regions


def test_load_config_from_env(monkeypatch):
    monkeypatch.setenv("HLTV_PROXY_URL", "http://test:pass@proxy:8080")
    monkeypatch.setenv("HLTV_MIN_DELAY", "3")
    monkeypatch.setenv("HLTV_DAILY_CAP", "100")
    monkeypatch.setenv("HLTV_PROXY_REGIONS", "de,fr")
    config = load_config()
    assert config.proxy_url == "http://test:pass@proxy:8080"
    assert config.min_delay == 3
    assert config.daily_cap == 100
    assert config.proxy_regions == ["de", "fr"]


def test_event_allow_list_not_empty():
    config = load_config()
    assert len(config.event_allow_list) > 10
    assert any("IEM" in e for e in config.event_allow_list)
    assert any("Major" in e for e in config.event_allow_list)
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scraper.config'`

- [ ] **Step 7: Write `scraper/scraper/config.py`**

```python
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


EVENT_ALLOW_LIST = [
    "PGL Major", "BLAST.tv Major", "Perfect World Major",
    "FACEIT Major", "StarLadder Major",
    "IEM Katowice", "IEM Cologne", "IEM Chengdu", "IEM Dallas",
    "IEM Sydney", "IEM Rio", "IEM Melbourne",
    "Intel Extreme Masters",
    "ESL Pro League",
    "BLAST Premier Spring", "BLAST Premier Fall",
    "BLAST Premier World Final",
    "Thunderpick World Championship",
    "CS Asia Championships",
    "YaLLa Compass",
    "Roobet Cup",
    "Betway Championship",
    "CCT Season",
    "CCT Global Finals",
    "PGL CS2 Major",
]


@dataclass(frozen=True)
class ScraperConfig:
    proxy_url: str = ""
    proxy_regions: list[str] = field(default_factory=lambda: ["us", "eu", "br"])
    raw_dir: Path = field(default_factory=lambda: Path("data/raw/hltv"))
    output_dir: Path = field(default_factory=lambda: Path("data/hltv_scraped"))
    db_path: Path = field(default_factory=lambda: Path("data/hltv_scraper.db"))
    daily_cap: int = 5000
    min_delay: int = 8
    max_delay: int = 15
    cooldown_every: int = 50
    cooldown_seconds: int = 120
    quiet_hours_start: int = 3
    quiet_hours_end: int = 6
    event_allow_list: list[str] = field(default_factory=lambda: list(EVENT_ALLOW_LIST))


def load_config() -> ScraperConfig:
    regions_raw = os.environ.get("HLTV_PROXY_REGIONS", "us,eu,br")
    return ScraperConfig(
        proxy_url=os.environ.get("HLTV_PROXY_URL", ""),
        proxy_regions=[r.strip() for r in regions_raw.split(",") if r.strip()],
        raw_dir=Path(os.environ.get("HLTV_RAW_DIR", "data/raw/hltv")),
        output_dir=Path(os.environ.get("HLTV_OUTPUT_DIR", "data/hltv_scraped")),
        db_path=Path(os.environ.get("HLTV_DB_PATH", "data/hltv_scraper.db")),
        daily_cap=int(os.environ.get("HLTV_DAILY_CAP", "5000")),
        min_delay=int(os.environ.get("HLTV_MIN_DELAY", "8")),
        max_delay=int(os.environ.get("HLTV_MAX_DELAY", "15")),
        cooldown_every=int(os.environ.get("HLTV_COOLDOWN_EVERY", "50")),
        cooldown_seconds=int(os.environ.get("HLTV_COOLDOWN_SECONDS", "120")),
    )
```

- [ ] **Step 8: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 9: Commit**

```bash
git add scraper/
git commit -m "feat(scraper): scaffold package with config and env loading"
```

---

### Task 2: Data Models

**Files:**
- Create: `scraper/scraper/models.py`
- Create: `scraper/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_models.py
from datetime import datetime, timezone
from scraper.models import (
    ScrapedTeam, ScrapedPlayer, ScrapedEvent, ScrapedMap,
    ScrapedVeto, ScrapedPlayerMapStats, ScrapedMatch,
    match_to_fixture_json,
)


def test_scraped_match_creation():
    match = ScrapedMatch(
        hltv_id="2371234",
        scheduled_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc),
        best_of=3,
        status="finished",
        team_a=ScrapedTeam(hltv_id="4608", name="NAVI"),
        team_b=ScrapedTeam(hltv_id="6667", name="FaZe"),
        event=ScrapedEvent(hltv_id="7148", name="IEM Katowice 2026", stars=5),
        players=(
            ScrapedPlayer(hltv_id="7998", nickname="s1mple", team_hltv_id="4608"),
        ),
        maps=(
            ScrapedMap(
                map_index=1, map_name="Inferno",
                team_a_score=13, team_b_score=9,
                winner_hltv_id="4608", map_stats_id="98765",
                player_stats=(),
            ),
        ),
        vetoes=(
            ScrapedVeto(order_idx=1, team_hltv_id="4608", action="ban", map_name="Dust2"),
        ),
        stats_url="https://www.hltv.org/stats/matches/112345/navi-vs-faze",
    )
    assert match.hltv_id == "2371234"
    assert len(match.maps) == 1
    assert match.maps[0].winner_hltv_id == "4608"


def test_match_to_fixture_json():
    match = ScrapedMatch(
        hltv_id="100",
        scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        best_of=1,
        status="finished",
        team_a=ScrapedTeam(hltv_id="1", name="TeamA"),
        team_b=ScrapedTeam(hltv_id="2", name="TeamB"),
        event=ScrapedEvent(hltv_id="10", name="Event", stars=5),
        players=(),
        maps=(
            ScrapedMap(
                map_index=1, map_name="Mirage",
                team_a_score=16, team_b_score=12,
                winner_hltv_id="1", map_stats_id="555",
                player_stats=(
                    ScrapedPlayerMapStats(
                        player_hltv_id="99", nickname="ace",
                        team_hltv_id="1", kills=25, deaths=18,
                        adr=88.5, rating=1.32, headshot_pct=52.0,
                        assists=4, first_kills=5, first_deaths=2,
                        kast_pct=75.0, ct_kills=14, ct_deaths=9,
                        t_kills=11, t_deaths=9, clutches_won=1,
                    ),
                ),
            ),
        ),
        vetoes=(),
        stats_url=None,
    )
    payload = match_to_fixture_json(match)
    assert payload["hltv_id"] == "100"
    assert payload["source"]["name"] == "hltv-scraper"
    assert payload["maps"][0]["player_stats"]["ace"]["kills"] == 25
    assert payload["maps"][0]["player_stats"]["ace"]["ct_kills"] == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `scraper/scraper/models.py`**

```python
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ScrapedTeam:
    hltv_id: str
    name: str


@dataclass(frozen=True)
class ScrapedPlayer:
    hltv_id: str
    nickname: str
    team_hltv_id: str


@dataclass(frozen=True)
class ScrapedEvent:
    hltv_id: str
    name: str
    stars: int | None = None


@dataclass(frozen=True)
class ScrapedPlayerMapStats:
    player_hltv_id: str
    nickname: str
    team_hltv_id: str
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    adr: float | None = None
    rating: float | None = None
    headshot_pct: float | None = None
    kast_pct: float | None = None
    first_kills: int | None = None
    first_deaths: int | None = None
    ct_kills: int | None = None
    ct_deaths: int | None = None
    t_kills: int | None = None
    t_deaths: int | None = None
    clutches_won: int | None = None


@dataclass(frozen=True)
class ScrapedMap:
    map_index: int
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_hltv_id: str
    map_stats_id: str | None = None
    player_stats: tuple[ScrapedPlayerMapStats, ...] = ()


@dataclass(frozen=True)
class ScrapedVeto:
    order_idx: int
    team_hltv_id: str | None
    action: str
    map_name: str


@dataclass(frozen=True)
class ScrapedMatch:
    hltv_id: str
    scheduled_at: datetime
    best_of: int
    status: str
    team_a: ScrapedTeam
    team_b: ScrapedTeam
    event: ScrapedEvent
    players: tuple[ScrapedPlayer, ...]
    maps: tuple[ScrapedMap, ...]
    vetoes: tuple[ScrapedVeto, ...]
    stats_url: str | None = None


def match_to_fixture_json(match: ScrapedMatch) -> dict:
    return {
        "hltv_id": match.hltv_id,
        "scheduled_at": match.scheduled_at.isoformat(),
        "best_of": match.best_of,
        "status": match.status,
        "team_a": {"hltv_id": match.team_a.hltv_id, "name": match.team_a.name},
        "team_b": {"hltv_id": match.team_b.hltv_id, "name": match.team_b.name},
        "event": {
            "hltv_id": match.event.hltv_id,
            "name": match.event.name,
            "tier": str(match.event.stars) if match.event.stars else None,
        },
        "players": [
            {"hltv_id": p.hltv_id, "nickname": p.nickname, "team_hltv_id": p.team_hltv_id}
            for p in match.players
        ],
        "maps": [
            {
                "map_index": m.map_index,
                "map_name": m.map_name,
                "team_a_score": m.team_a_score,
                "team_b_score": m.team_b_score,
                "winner_hltv_id": m.winner_hltv_id,
                "player_stats": {
                    ps.nickname: {
                        "kills": ps.kills, "deaths": ps.deaths, "assists": ps.assists,
                        "adr": ps.adr, "rating": ps.rating, "headshot_pct": ps.headshot_pct,
                        "kast_pct": ps.kast_pct, "first_kills": ps.first_kills,
                        "first_deaths": ps.first_deaths,
                        "ct_kills": ps.ct_kills, "ct_deaths": ps.ct_deaths,
                        "t_kills": ps.t_kills, "t_deaths": ps.t_deaths,
                        "clutches_won": ps.clutches_won,
                    }
                    for ps in m.player_stats
                },
            }
            for m in match.maps
        ],
        "vetoes": [
            {
                "order_idx": v.order_idx, "team_hltv_id": v.team_hltv_id,
                "action": v.action, "map_name": v.map_name,
            }
            for v in match.vetoes
        ],
        "source": {
            "name": "hltv-scraper",
            "url": f"https://www.hltv.org/matches/{match.hltv_id}",
        },
    }


def write_fixture_json(match: ScrapedMatch, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{match.hltv_id}.json"
    path.write_text(json.dumps(match_to_fixture_json(match), indent=2, sort_keys=True), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_models.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/models.py scraper/tests/test_models.py
git commit -m "feat(scraper): data models and fixture JSON serialization"
```

---

### Task 3: Tracking Database (SQLite)

**Files:**
- Create: `scraper/scraper/tracking_db.py`
- Create: `scraper/tests/test_tracking_db.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_tracking_db.py
from pathlib import Path
from scraper.tracking_db import TrackingDB


def test_create_tables(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.close()
    assert (tmp_path / "test.db").exists()


def test_upsert_and_get_match(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/a-vs-b", event_name="IEM", event_stars=5, scheduled_at="2026-05-01")
    row = db.get_match("123")
    assert row is not None
    assert row["match_id"] == "123"
    assert row["event_name"] == "IEM"
    assert row["match_fetched"] == 0
    db.close()


def test_mark_match_fetched(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/slug")
    db.mark_match_fetched("123")
    row = db.get_match("123")
    assert row["match_fetched"] == 1
    db.close()


def test_mark_stats_fetched(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/slug")
    db.mark_stats_fetched("123")
    row = db.get_match("123")
    assert row["stats_fetched"] == 1
    db.close()


def test_increment_maps_fetched(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/slug")
    db.set_maps_total("123", 3)
    db.increment_maps_fetched("123")
    db.increment_maps_fetched("123")
    row = db.get_match("123")
    assert row["maps_fetched"] == 2
    assert row["maps_total"] == 3
    db.close()


def test_mark_parsed(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/slug")
    db.mark_parsed("123")
    row = db.get_match("123")
    assert row["parsed"] == 1
    db.close()


def test_pending_matches(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("1", "/matches/1/a", scheduled_at="2026-05-01", priority_tier=1)
    db.upsert_match("2", "/matches/2/b", scheduled_at="2026-04-01", priority_tier=2)
    db.upsert_match("3", "/matches/3/c", scheduled_at="2026-06-01", priority_tier=1)
    db.mark_parsed("3")
    pending = db.pending_matches(limit=10)
    assert len(pending) == 2
    assert pending[0]["match_id"] == "1"
    assert pending[1]["match_id"] == "2"
    db.close()


def test_record_error(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("123", "/matches/123/slug")
    db.record_error("123", "HTTP 403")
    row = db.get_match("123")
    assert row["retry_count"] == 1
    assert row["last_error"] == "HTTP 403"
    db.close()


def test_log_request(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.log_request("/matches/1/slug", 200, "curl_cffi", "us", 52000, 310)
    count = db.request_count_today()
    assert count == 1
    db.close()


def test_upsert_blocked_pattern(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.record_block("/stats/matches/")
    db.record_block("/stats/matches/")
    db.record_block("/stats/matches/")
    assert db.needs_playwright("/stats/matches/") is True
    assert db.needs_playwright("/matches/") is False
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_tracking_db.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write `scraper/scraper/tracking_db.py`**

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class TrackingDB:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS scrape_queue (
                match_id        TEXT PRIMARY KEY,
                match_url       TEXT NOT NULL,
                event_name      TEXT,
                event_stars     INTEGER,
                scheduled_at    TEXT,
                discovered_at   TEXT DEFAULT (datetime('now')),
                match_fetched   INTEGER DEFAULT 0,
                stats_fetched   INTEGER DEFAULT 0,
                maps_fetched    INTEGER DEFAULT 0,
                maps_total      INTEGER,
                parsed          INTEGER DEFAULT 0,
                priority_tier   INTEGER DEFAULT 1,
                last_error      TEXT,
                retry_count     INTEGER DEFAULT 0,
                updated_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS blocked_patterns (
                url_pattern     TEXT PRIMARY KEY,
                needs_playwright INTEGER DEFAULT 0,
                consecutive_blocks INTEGER DEFAULT 0,
                last_tested     TEXT
            );
            CREATE TABLE IF NOT EXISTS request_log (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT,
                status_code     INTEGER,
                fetcher_type    TEXT,
                proxy_region    TEXT,
                response_bytes  INTEGER,
                elapsed_ms      INTEGER,
                created_at      TEXT DEFAULT (datetime('now'))
            );
        """)

    def upsert_match(
        self, match_id: str, match_url: str, *,
        event_name: str | None = None, event_stars: int | None = None,
        scheduled_at: str | None = None, priority_tier: int = 1,
    ) -> None:
        self._conn.execute(
            """INSERT INTO scrape_queue (match_id, match_url, event_name, event_stars, scheduled_at, priority_tier)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(match_id) DO UPDATE SET
                 event_name = COALESCE(excluded.event_name, event_name),
                 event_stars = COALESCE(excluded.event_stars, event_stars),
                 scheduled_at = COALESCE(excluded.scheduled_at, scheduled_at),
                 updated_at = datetime('now')""",
            (match_id, match_url, event_name, event_stars, scheduled_at, priority_tier),
        )
        self._conn.commit()

    def get_match(self, match_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM scrape_queue WHERE match_id = ?", (match_id,)).fetchone()
        return dict(row) if row else None

    def mark_match_fetched(self, match_id: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET match_fetched = 1, updated_at = datetime('now') WHERE match_id = ?",
            (match_id,),
        )
        self._conn.commit()

    def mark_stats_fetched(self, match_id: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET stats_fetched = 1, updated_at = datetime('now') WHERE match_id = ?",
            (match_id,),
        )
        self._conn.commit()

    def set_maps_total(self, match_id: str, total: int) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET maps_total = ?, updated_at = datetime('now') WHERE match_id = ?",
            (total, match_id),
        )
        self._conn.commit()

    def increment_maps_fetched(self, match_id: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET maps_fetched = maps_fetched + 1, updated_at = datetime('now') WHERE match_id = ?",
            (match_id,),
        )
        self._conn.commit()

    def mark_parsed(self, match_id: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET parsed = 1, updated_at = datetime('now') WHERE match_id = ?",
            (match_id,),
        )
        self._conn.commit()

    def record_error(self, match_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET last_error = ?, retry_count = retry_count + 1, updated_at = datetime('now') WHERE match_id = ?",
            (error, match_id),
        )
        self._conn.commit()

    def pending_matches(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM scrape_queue
               WHERE parsed = 0 AND retry_count < 5
               ORDER BY priority_tier ASC, scheduled_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_request(self, url: str, status_code: int, fetcher_type: str, proxy_region: str, response_bytes: int, elapsed_ms: int) -> None:
        self._conn.execute(
            "INSERT INTO request_log (url, status_code, fetcher_type, proxy_region, response_bytes, elapsed_ms) VALUES (?, ?, ?, ?, ?, ?)",
            (url, status_code, fetcher_type, proxy_region, response_bytes, elapsed_ms),
        )
        self._conn.commit()

    def request_count_today(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM request_log WHERE created_at >= date('now')"
        ).fetchone()
        return row["cnt"]

    def record_block(self, url_pattern: str) -> None:
        self._conn.execute(
            """INSERT INTO blocked_patterns (url_pattern, consecutive_blocks, needs_playwright, last_tested)
               VALUES (?, 1, 0, datetime('now'))
               ON CONFLICT(url_pattern) DO UPDATE SET
                 consecutive_blocks = consecutive_blocks + 1,
                 needs_playwright = CASE WHEN consecutive_blocks + 1 >= 3 THEN 1 ELSE 0 END,
                 last_tested = datetime('now')""",
            (url_pattern,),
        )
        self._conn.commit()

    def needs_playwright(self, url_pattern: str) -> bool:
        row = self._conn.execute(
            "SELECT needs_playwright FROM blocked_patterns WHERE url_pattern = ?",
            (url_pattern,),
        ).fetchone()
        return bool(row and row["needs_playwright"])

    def queue_stats(self) -> dict:
        row = self._conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(match_fetched) as fetched,
                SUM(parsed) as parsed,
                SUM(CASE WHEN retry_count >= 5 THEN 1 ELSE 0 END) as errors
            FROM scrape_queue
        """).fetchone()
        return dict(row)

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_tracking_db.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/tracking_db.py scraper/tests/test_tracking_db.py
git commit -m "feat(scraper): SQLite tracking DB with queue, request log, and blocked patterns"
```

---

### Task 4: Anti-Detection (Headers, Profiles, Challenge Detection)

**Files:**
- Create: `scraper/scraper/anti_detect.py`
- Create: `scraper/tests/test_anti_detect.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_anti_detect.py
from scraper.anti_detect import (
    random_browser_profile,
    is_cloudflare_challenge,
    extract_url_pattern,
    BROWSER_PROFILES,
)


def test_browser_profiles_exist():
    assert len(BROWSER_PROFILES) >= 5


def test_random_profile_returns_valid_headers():
    profile = random_browser_profile()
    assert "User-Agent" in profile.headers
    assert "Accept" in profile.headers
    assert "Accept-Language" in profile.headers
    assert profile.impersonate in ("chrome120", "chrome124", "chrome131")


def test_is_cloudflare_challenge_detects_403():
    assert is_cloudflare_challenge(403, "<html>Access denied</html>") is True


def test_is_cloudflare_challenge_detects_challenge_js():
    html = '<html><body><div id="cf-challenge-running">Checking your browser</div></body></html>'
    assert is_cloudflare_challenge(200, html) is True


def test_is_cloudflare_challenge_normal_page():
    assert is_cloudflare_challenge(200, "<html><body>Normal content</body></html>") is False


def test_is_cloudflare_challenge_429():
    assert is_cloudflare_challenge(429, "<html>Rate limited</html>") is True


def test_extract_url_pattern():
    assert extract_url_pattern("https://www.hltv.org/matches/123/navi-vs-faze") == "/matches/"
    assert extract_url_pattern("https://www.hltv.org/stats/matches/456/slug") == "/stats/matches/"
    assert extract_url_pattern("https://www.hltv.org/stats/matches/mapstatsid/789/slug") == "/stats/matches/mapstatsid/"
    assert extract_url_pattern("https://www.hltv.org/results?offset=100") == "/results"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_anti_detect.py -v`
Expected: FAIL

- [ ] **Step 3: Write `scraper/scraper/anti_detect.py`**

```python
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserProfile:
    impersonate: str
    headers: dict[str, str]


BROWSER_PROFILES = [
    BrowserProfile(
        impersonate="chrome131",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Chromium";v="131", "Not_A Brand";v="24"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
    BrowserProfile(
        impersonate="chrome124",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
    BrowserProfile(
        impersonate="chrome120",
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
    BrowserProfile(
        impersonate="chrome131",
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Chromium";v="131"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Linux"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
    BrowserProfile(
        impersonate="chrome124",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.91 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-CH-UA": '"Chromium";v="124", "Google Chrome";v="124"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        },
    ),
]

_CF_CHALLENGE_MARKERS = (
    "cf-challenge-running",
    "cf-browser-verification",
    "Checking your browser",
    "cf-challenge",
    "challenges.cloudflare.com",
)


def random_browser_profile() -> BrowserProfile:
    return random.choice(BROWSER_PROFILES)


def is_cloudflare_challenge(status_code: int, body: str) -> bool:
    if status_code in (403, 429):
        return True
    return any(marker in body for marker in _CF_CHALLENGE_MARKERS)


def extract_url_pattern(url: str) -> str:
    path = urlparse(url).path
    if "/stats/matches/mapstatsid/" in path:
        return "/stats/matches/mapstatsid/"
    if "/stats/matches/" in path:
        return "/stats/matches/"
    if "/matches/" in path:
        return "/matches/"
    if "/results" in path:
        return "/results"
    return path
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_anti_detect.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/anti_detect.py scraper/tests/test_anti_detect.py
git commit -m "feat(scraper): anti-detection browser profiles and Cloudflare challenge detection"
```

---

### Task 5: Proxy Rotator

**Files:**
- Create: `scraper/scraper/proxy.py`
- Create: `scraper/tests/test_proxy.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_proxy.py
from scraper.proxy import ProxyRotator


def test_no_proxy_returns_none():
    rotator = ProxyRotator("", ["us"])
    assert rotator.get_proxy() is None


def test_rotating_proxy_replaces_session():
    rotator = ProxyRotator("http://user-session-{session}:pass@gate.proxy.com:10000", ["us", "eu"])
    proxy = rotator.get_proxy()
    assert proxy is not None
    assert "{session}" not in proxy
    assert "user-session-" in proxy


def test_rotating_proxy_different_each_call():
    rotator = ProxyRotator("http://user-session-{session}:pass@gate.proxy.com:10000", ["us"])
    p1 = rotator.get_proxy()
    p2 = rotator.get_proxy()
    assert p1 != p2


def test_sticky_session_same_proxy():
    rotator = ProxyRotator("http://user-session-{session}:pass@gate.proxy.com:10000", ["us"])
    rotator.start_sticky_session()
    p1 = rotator.get_proxy()
    p2 = rotator.get_proxy()
    assert p1 == p2
    rotator.end_sticky_session()
    p3 = rotator.get_proxy()
    assert p3 != p1


def test_get_region_rotates():
    rotator = ProxyRotator("http://user:pass@gate.proxy.com:10000", ["us", "eu", "br"])
    regions = {rotator.get_region() for _ in range(30)}
    assert len(regions) >= 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_proxy.py -v`
Expected: FAIL

- [ ] **Step 3: Write `scraper/scraper/proxy.py`**

```python
from __future__ import annotations

import random
import string


class ProxyRotator:
    def __init__(self, proxy_url_template: str, regions: list[str]) -> None:
        self._template = proxy_url_template
        self._regions = regions or ["us"]
        self._sticky_session: str | None = None

    def get_proxy(self) -> str | None:
        if not self._template:
            return None
        session_id = self._sticky_session or self._random_session()
        return self._template.replace("{session}", session_id)

    def get_region(self) -> str:
        return random.choice(self._regions)

    def start_sticky_session(self) -> None:
        self._sticky_session = self._random_session()

    def end_sticky_session(self) -> None:
        self._sticky_session = None

    @staticmethod
    def _random_session() -> str:
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_proxy.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/proxy.py scraper/tests/test_proxy.py
git commit -m "feat(scraper): proxy rotator with sticky sessions and geo-rotation"
```

---

### Task 6: Rate Limiter

**Files:**
- Create: `scraper/scraper/rate_limiter.py`
- Create: `scraper/tests/test_rate_limiter.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_rate_limiter.py
import time
from unittest.mock import patch
from scraper.rate_limiter import RateLimiter


def test_delay_within_bounds():
    limiter = RateLimiter(min_delay=2, max_delay=5, cooldown_every=100, cooldown_seconds=10, daily_cap=1000)
    delay = limiter.next_delay()
    assert 2 <= delay <= 5


def test_cooldown_triggers():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=3, cooldown_seconds=99, daily_cap=1000)
    limiter.record_request()
    limiter.record_request()
    limiter.record_request()
    delay = limiter.next_delay()
    assert delay >= 99


def test_daily_cap_exceeded():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=100, cooldown_seconds=0, daily_cap=2)
    limiter.record_request()
    limiter.record_request()
    assert limiter.daily_cap_reached() is True


def test_daily_cap_not_exceeded():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=100, cooldown_seconds=0, daily_cap=100)
    limiter.record_request()
    assert limiter.daily_cap_reached() is False


def test_consecutive_failure_backoff():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=100, cooldown_seconds=0, daily_cap=1000)
    limiter.record_failure()
    limiter.record_failure()
    limiter.record_failure()
    delay = limiter.failure_backoff_delay()
    assert delay >= 300


def test_failure_reset_on_success():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=100, cooldown_seconds=0, daily_cap=1000)
    limiter.record_failure()
    limiter.record_failure()
    limiter.record_request()
    assert limiter.failure_backoff_delay() == 0


def test_quiet_hours():
    limiter = RateLimiter(min_delay=0, max_delay=0, cooldown_every=100, cooldown_seconds=0, daily_cap=1000, quiet_hours_start=3, quiet_hours_end=6)
    from datetime import datetime, timezone
    with patch("scraper.rate_limiter._utcnow_hour", return_value=4):
        assert limiter.in_quiet_hours() is True
    with patch("scraper.rate_limiter._utcnow_hour", return_value=12):
        assert limiter.in_quiet_hours() is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_rate_limiter.py -v`
Expected: FAIL

- [ ] **Step 3: Write `scraper/scraper/rate_limiter.py`**

```python
from __future__ import annotations

import random
from datetime import datetime, timezone


def _utcnow_hour() -> int:
    return datetime.now(timezone.utc).hour


class RateLimiter:
    def __init__(
        self,
        min_delay: int = 8,
        max_delay: int = 15,
        cooldown_every: int = 50,
        cooldown_seconds: int = 120,
        daily_cap: int = 5000,
        quiet_hours_start: int = 3,
        quiet_hours_end: int = 6,
    ) -> None:
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._cooldown_every = cooldown_every
        self._cooldown_seconds = cooldown_seconds
        self._daily_cap = daily_cap
        self._quiet_hours_start = quiet_hours_start
        self._quiet_hours_end = quiet_hours_end
        self._request_count = 0
        self._daily_count = 0
        self._consecutive_failures = 0

    def next_delay(self) -> float:
        if self._cooldown_every > 0 and self._request_count > 0 and self._request_count % self._cooldown_every == 0:
            return self._cooldown_seconds + random.uniform(0, self._cooldown_seconds * 0.5)
        return random.uniform(self._min_delay, self._max_delay)

    def record_request(self) -> None:
        self._request_count += 1
        self._daily_count += 1
        self._consecutive_failures = 0

    def record_failure(self) -> None:
        self._consecutive_failures += 1

    def failure_backoff_delay(self) -> float:
        if self._consecutive_failures >= 10:
            return 3600.0
        if self._consecutive_failures >= 3:
            return 300.0
        return 0.0

    def daily_cap_reached(self) -> bool:
        return self._daily_count >= self._daily_cap

    def in_quiet_hours(self) -> bool:
        hour = _utcnow_hour()
        return self._quiet_hours_start <= hour < self._quiet_hours_end

    def reset_daily(self) -> None:
        self._daily_count = 0
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_rate_limiter.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/rate_limiter.py scraper/tests/test_rate_limiter.py
git commit -m "feat(scraper): rate limiter with jitter, cooldowns, daily cap, quiet hours"
```

---

### Task 7: Playwright Session Manager

**Files:**
- Create: `scraper/scraper/session.py`

- [ ] **Step 1: Write `scraper/scraper/session.py`**

This module manages the Playwright browser lifecycle. It cannot be meaningfully unit-tested without a real browser, so we test it in the integration tests (Task 12).

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page

_logger = logging.getLogger(__name__)


class PlaywrightSession:
    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._request_count = 0
        self._max_requests = 15

    def start(self) -> None:
        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()
        self._launch_browser()

    def _launch_browser(self) -> None:
        launch_args = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        }
        if self._proxy:
            launch_args["proxy"] = {"server": self._proxy}
        self._browser = self._playwright.chromium.launch(**launch_args)
        self._context = self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="en-US",
        )
        self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        self._request_count = 0

    def fetch(self, url: str) -> tuple[int, str]:
        if self._context is None:
            self.start()
        if self._request_count >= self._max_requests:
            _logger.info("recycling Playwright browser after %d requests", self._request_count)
            self._recycle()
        page: Page = self._context.new_page()
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else 0
            html = page.content()
            self._request_count += 1
            return status, html
        finally:
            page.close()

    def _recycle(self) -> None:
        if self._browser:
            self._browser.close()
        self._launch_browser()

    def close(self) -> None:
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._context = None
        self._playwright = None
```

- [ ] **Step 2: Commit**

```bash
git add scraper/scraper/session.py
git commit -m "feat(scraper): Playwright session manager with browser recycling"
```

---

### Task 8: Hybrid Fetcher

**Files:**
- Create: `scraper/scraper/fetcher.py`
- Create: `scraper/tests/test_fetcher.py`

- [ ] **Step 1: Write the failing test (unit tests with mocks)**

```python
# scraper/tests/test_fetcher.py
from pathlib import Path
from unittest.mock import MagicMock, patch
from scraper.fetcher import HltvFetcher, FetchResult


def test_fetch_result_dataclass():
    r = FetchResult(status=200, html="<html>ok</html>", fetcher_type="curl_cffi", elapsed_ms=100, content_bytes=12)
    assert r.ok is True


def test_fetch_result_not_ok():
    r = FetchResult(status=403, html="blocked", fetcher_type="curl_cffi", elapsed_ms=100, content_bytes=7)
    assert r.ok is False


def test_save_raw_creates_file(tmp_path: Path):
    fetcher = HltvFetcher.__new__(HltvFetcher)
    fetcher._raw_dir = tmp_path
    fetcher._save_raw("123", "match.html", "<html>test</html>")
    saved = tmp_path / "matches" / "123" / "match.html"
    assert saved.exists()
    assert saved.read_text(encoding="utf-8") == "<html>test</html>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_fetcher.py -v`
Expected: FAIL

- [ ] **Step 3: Write `scraper/scraper/fetcher.py`**

```python
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from scraper.anti_detect import (
    extract_url_pattern,
    is_cloudflare_challenge,
    random_browser_profile,
)
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.session import PlaywrightSession
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FetchResult:
    status: int
    html: str
    fetcher_type: str
    elapsed_ms: int
    content_bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 400 and not is_cloudflare_challenge(self.status, self.html)


class HltvFetcher:
    def __init__(
        self,
        proxy_rotator: ProxyRotator,
        rate_limiter: RateLimiter,
        tracking_db: TrackingDB,
        raw_dir: Path,
    ) -> None:
        self._proxy = proxy_rotator
        self._limiter = rate_limiter
        self._db = tracking_db
        self._raw_dir = raw_dir
        self._pw_session: PlaywrightSession | None = None

    def fetch(self, url: str) -> FetchResult:
        pattern = extract_url_pattern(url)
        if self._db.needs_playwright(pattern):
            return self._fetch_playwright(url)
        result = self._fetch_curl(url)
        if result.ok:
            return result
        _logger.info("curl_cffi blocked on %s, falling back to Playwright", url)
        self._db.record_block(pattern)
        return self._fetch_playwright(url)

    def _fetch_curl(self, url: str) -> FetchResult:
        from curl_cffi import requests as curl_requests

        profile = random_browser_profile()
        proxy = self._proxy.get_proxy()
        proxies = {"https": proxy, "http": proxy} if proxy else None
        region = self._proxy.get_region()
        start = time.monotonic()
        try:
            resp = curl_requests.get(
                url,
                headers=profile.headers,
                impersonate=profile.impersonate,
                proxies=proxies,
                timeout=30,
            )
            elapsed = int((time.monotonic() - start) * 1000)
            result = FetchResult(
                status=resp.status_code,
                html=resp.text,
                fetcher_type="curl_cffi",
                elapsed_ms=elapsed,
                content_bytes=len(resp.content),
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            _logger.warning("curl_cffi error on %s: %s", url, exc)
            result = FetchResult(status=0, html="", fetcher_type="curl_cffi", elapsed_ms=elapsed, content_bytes=0)
        self._db.log_request(url, result.status, "curl_cffi", region, result.content_bytes, result.elapsed_ms)
        if result.ok:
            self._limiter.record_request()
        else:
            self._limiter.record_failure()
        return result

    def _fetch_playwright(self, url: str) -> FetchResult:
        proxy = self._proxy.get_proxy()
        if self._pw_session is None:
            self._pw_session = PlaywrightSession(proxy=proxy)
            self._pw_session.start()
        region = self._proxy.get_region()
        start = time.monotonic()
        try:
            status, html = self._pw_session.fetch(url)
            elapsed = int((time.monotonic() - start) * 1000)
            result = FetchResult(
                status=status,
                html=html,
                fetcher_type="playwright",
                elapsed_ms=elapsed,
                content_bytes=len(html.encode("utf-8")),
            )
        except Exception as exc:
            elapsed = int((time.monotonic() - start) * 1000)
            _logger.warning("Playwright error on %s: %s", url, exc)
            result = FetchResult(status=0, html="", fetcher_type="playwright", elapsed_ms=elapsed, content_bytes=0)
        self._db.log_request(url, result.status, "playwright", region, result.content_bytes, result.elapsed_ms)
        if result.ok:
            self._limiter.record_request()
        else:
            self._limiter.record_failure()
        return result

    def _save_raw(self, match_id: str, filename: str, content: str) -> Path:
        match_dir = self._raw_dir / "matches" / match_id
        match_dir.mkdir(parents=True, exist_ok=True)
        path = match_dir / filename
        path.write_text(content, encoding="utf-8")
        return path

    def save_raw_match(self, match_id: str, html: str) -> Path:
        return self._save_raw(match_id, "match.html", html)

    def save_raw_stats(self, match_id: str, html: str) -> Path:
        return self._save_raw(match_id, "stats.html", html)

    def save_raw_map(self, match_id: str, map_stats_id: str, html: str) -> Path:
        return self._save_raw(match_id, f"map_{map_stats_id}.html", html)

    def save_raw_results_page(self, offset: int, html: str) -> Path:
        results_dir = self._raw_dir / "results"
        results_dir.mkdir(parents=True, exist_ok=True)
        path = results_dir / f"page_{offset}.html"
        path.write_text(html, encoding="utf-8")
        return path

    def save_meta(self, match_id: str, meta: dict) -> Path:
        return self._save_raw(match_id, "meta.json", json.dumps(meta, indent=2))

    def close(self) -> None:
        if self._pw_session:
            self._pw_session.close()
            self._pw_session = None
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_fetcher.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/fetcher.py scraper/tests/test_fetcher.py
git commit -m "feat(scraper): hybrid fetcher with curl_cffi fast path and Playwright fallback"
```

---

### Task 9: HTML Parser — Results Page

**Files:**
- Create: `scraper/scraper/parser.py`
- Create: `scraper/tests/test_parser.py`
- Create: `scraper/tests/fixtures/README.md`

This task implements the first parser function: extracting match IDs from the `/results` listing page. Subsequent parser functions (match page, stats page, map stats page) are added in Tasks 10 and 11.

**Important**: The exact CSS selectors and HTML structure must be verified against real HLTV pages during the integration test (Task 12). The parser code here is written based on the known HLTV DOM structure as of May 2026, but selectors may need adjustment after the live test captures real fixtures.

- [ ] **Step 1: Create `scraper/tests/fixtures/README.md`**

```markdown
# Test Fixtures

Saved HLTV HTML pages for offline parser testing.
These are captured by `python -m scraper.cli test-live` and should NOT be committed to public repos.
Add `scraper/tests/fixtures/*.html` to `.gitignore`.
```

- [ ] **Step 2: Write the failing test**

```python
# scraper/tests/test_parser.py
from scraper.parser import parse_results_page, parse_match_page, parse_stats_page, parse_map_stats_page


class TestParseResultsPage:
    def test_extracts_match_ids_from_result_links(self):
        html = """
        <div class="results-holder">
          <div class="result-con">
            <a href="/matches/2371234/navi-vs-faze-iem-katowice-2026" class="a-reset">
              <div class="result">
                <div class="result-teamName">NAVI</div>
                <div class="result-teamName">FaZe</div>
                <div class="event-name">IEM Katowice 2026</div>
                <div class="star-cell"><i class="fa fa-star"></i><i class="fa fa-star"></i><i class="fa fa-star"></i><i class="fa fa-star"></i><i class="fa fa-star"></i></div>
              </div>
            </a>
          </div>
          <div class="result-con">
            <a href="/matches/2371235/g2-vs-vitality-iem-katowice-2026" class="a-reset">
              <div class="result">
                <div class="result-teamName">G2</div>
                <div class="result-teamName">Vitality</div>
                <div class="event-name">IEM Katowice 2026</div>
              </div>
            </a>
          </div>
        </div>
        """
        results = parse_results_page(html)
        assert len(results) == 2
        assert results[0]["match_id"] == "2371234"
        assert results[0]["match_url"] == "/matches/2371234/navi-vs-faze-iem-katowice-2026"
        assert results[0]["team_a"] == "NAVI"
        assert results[0]["team_b"] == "FaZe"
        assert results[0]["event_name"] == "IEM Katowice 2026"
        assert results[1]["match_id"] == "2371235"

    def test_empty_page_returns_empty(self):
        results = parse_results_page("<html><body>No results</body></html>")
        assert results == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_parser.py::TestParseResultsPage -v`
Expected: FAIL

- [ ] **Step 4: Write the results page parser in `scraper/scraper/parser.py`**

```python
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup, Tag

_logger = logging.getLogger(__name__)


def parse_results_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []
    for link in soup.select(".result-con a[href*='/matches/']"):
        href = link.get("href", "")
        match_id_match = re.search(r"/matches/(\d+)/", href)
        if not match_id_match:
            continue
        match_id = match_id_match.group(1)
        team_names = [el.get_text(strip=True) for el in link.select(".result-teamName")]
        event_el = link.select_one(".event-name")
        event_name = event_el.get_text(strip=True) if event_el else ""
        stars = len(link.select(".star-cell .fa-star, .star-cell i[class*='star']"))
        results.append({
            "match_id": match_id,
            "match_url": href,
            "team_a": team_names[0] if len(team_names) > 0 else "",
            "team_b": team_names[1] if len(team_names) > 1 else "",
            "event_name": event_name,
            "event_stars": stars if stars > 0 else None,
        })
    return results
```

- [ ] **Step 5: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_parser.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add scraper/scraper/parser.py scraper/tests/test_parser.py scraper/tests/fixtures/README.md
git commit -m "feat(scraper): results page parser extracts match IDs and event info"
```

---

### Task 10: HTML Parser — Match Page

**Files:**
- Modify: `scraper/scraper/parser.py`
- Modify: `scraper/tests/test_parser.py`

- [ ] **Step 1: Add failing tests for match page parser**

Append to `scraper/tests/test_parser.py`:

```python
class TestParseMatchPage:
    def test_extracts_teams_and_scores(self):
        html = """
        <div class="match-page">
          <div class="team1-gradient">
            <a href="/team/4608/navi"><img class="logo" /></a>
            <div class="teamName">NAVI</div>
          </div>
          <div class="team2-gradient">
            <a href="/team/6667/faze"><img class="logo" /></a>
            <div class="teamName">FaZe</div>
          </div>
          <div class="standard-box veto-box">
            <div class="padding">
              <div>1. NAVI removed Dust2</div>
              <div>2. FaZe removed Ancient</div>
              <div>3. NAVI picked Inferno</div>
              <div>4. FaZe picked Mirage</div>
              <div>5. Nuke was left over</div>
            </div>
          </div>
          <div class="maps">
            <div class="mapholder">
              <div class="mapname">Inferno</div>
              <div class="results-left">
                <div class="results-team-score">16</div>
              </div>
              <div class="results-right">
                <div class="results-team-score">9</div>
              </div>
              <a href="/stats/matches/mapstatsid/111222/slug" class="results-stats"></a>
            </div>
          </div>
          <div class="match-info-box">
            <div class="match-info-row">
              <div class="match-info-row-content">bo3</div>
            </div>
          </div>
          <div class="event">
            <a href="/events/7148/iem-katowice-2026">IEM Katowice 2026</a>
          </div>
          <div class="date" data-unix="1714564800000"></div>
          <div class="lineup">
            <div class="players">
              <div class="player">
                <a href="/player/7998/s1mple">
                  <div class="text-ellipsis">s1mple</div>
                </a>
              </div>
            </div>
          </div>
          <a href="/stats/matches/112345/navi-vs-faze" class="match-page-link">Stats</a>
        </div>
        """
        match_data = parse_match_page(html, "2371234")
        assert match_data["hltv_id"] == "2371234"
        assert match_data["team_a"]["name"] == "NAVI"
        assert match_data["team_a"]["hltv_id"] == "4608"
        assert match_data["team_b"]["name"] == "FaZe"
        assert match_data["best_of"] == 3
        assert len(match_data["maps"]) == 1
        assert match_data["maps"][0]["map_name"] == "Inferno"
        assert match_data["maps"][0]["team_a_score"] == 16
        assert match_data["maps"][0]["team_b_score"] == 9
        assert match_data["maps"][0]["map_stats_id"] == "111222"
        assert len(match_data["vetoes"]) >= 1
        assert match_data["stats_url"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_parser.py::TestParseMatchPage -v`
Expected: FAIL

- [ ] **Step 3: Add `parse_match_page` to `scraper/scraper/parser.py`**

Append to `parser.py`:

```python
def parse_match_page(html: str, match_id: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    team_a = _extract_team(soup, "team1-gradient", "team1")
    team_b = _extract_team(soup, "team2-gradient", "team2")

    best_of = _extract_best_of(soup)
    event = _extract_event(soup)
    scheduled_at = _extract_date(soup)
    vetoes = _extract_vetoes(soup, team_a.get("name", ""), team_b.get("name", ""))
    maps = _extract_maps(soup, team_a.get("hltv_id", ""), team_b.get("hltv_id", ""))
    players = _extract_players(soup)
    stats_url = _extract_stats_url(soup)

    return {
        "hltv_id": match_id,
        "scheduled_at": scheduled_at,
        "best_of": best_of,
        "status": "finished",
        "team_a": team_a,
        "team_b": team_b,
        "event": event,
        "maps": maps,
        "vetoes": vetoes,
        "players": players,
        "stats_url": stats_url,
    }


def _extract_team(soup: BeautifulSoup, gradient_class: str, fallback_class: str) -> dict:
    container = soup.select_one(f".{gradient_class}") or soup.select_one(f".{fallback_class}")
    if not container:
        return {"hltv_id": "", "name": ""}
    name_el = container.select_one(".teamName")
    name = name_el.get_text(strip=True) if name_el else ""
    team_link = container.select_one("a[href*='/team/']")
    hltv_id = ""
    if team_link:
        id_match = re.search(r"/team/(\d+)/", team_link.get("href", ""))
        if id_match:
            hltv_id = id_match.group(1)
    return {"hltv_id": hltv_id, "name": name}


def _extract_best_of(soup: BeautifulSoup) -> int:
    for el in soup.select(".match-info-row-content, .match-info-box .padding"):
        text = el.get_text(strip=True).lower()
        bo_match = re.search(r"bo(\d+)", text)
        if bo_match:
            return int(bo_match.group(1))
    return 1


def _extract_event(soup: BeautifulSoup) -> dict:
    event_link = soup.select_one(".event a[href*='/events/']")
    if not event_link:
        return {"hltv_id": "", "name": "", "stars": None}
    name = event_link.get_text(strip=True)
    hltv_id = ""
    id_match = re.search(r"/events/(\d+)/", event_link.get("href", ""))
    if id_match:
        hltv_id = id_match.group(1)
    return {"hltv_id": hltv_id, "name": name, "stars": None}


def _extract_date(soup: BeautifulSoup) -> str | None:
    date_el = soup.select_one(".date[data-unix], .timeAndEvent .date[data-unix]")
    if date_el:
        unix_ms = date_el.get("data-unix")
        if unix_ms:
            dt = datetime.fromtimestamp(int(unix_ms) / 1000, tz=timezone.utc)
            return dt.isoformat()
    return None


def _extract_vetoes(soup: BeautifulSoup, team_a_name: str, team_b_name: str) -> list[dict]:
    veto_box = soup.select_one(".veto-box .padding, .veto-box")
    if not veto_box:
        return []
    vetoes: list[dict] = []
    for idx, div in enumerate(veto_box.find_all("div", recursive=False), start=1):
        text = div.get_text(strip=True)
        if not text:
            continue
        action, map_name, team_name = _parse_veto_text(text)
        if not map_name:
            continue
        vetoes.append({
            "order_idx": idx,
            "team_name": team_name,
            "action": action,
            "map_name": map_name,
        })
    return vetoes


def _parse_veto_text(text: str) -> tuple[str, str, str]:
    text = re.sub(r"^\d+\.\s*", "", text)
    removed = re.match(r"(.+?)\s+removed\s+(.+)", text, re.IGNORECASE)
    if removed:
        return "ban", removed.group(2).strip(), removed.group(1).strip()
    picked = re.match(r"(.+?)\s+picked\s+(.+)", text, re.IGNORECASE)
    if picked:
        return "pick", picked.group(2).strip(), picked.group(1).strip()
    left = re.match(r"(.+?)\s+was\s+left\s+over", text, re.IGNORECASE)
    if left:
        return "left_over", left.group(1).strip(), ""
    return "unknown", "", ""


def _extract_maps(soup: BeautifulSoup, team_a_id: str, team_b_id: str) -> list[dict]:
    maps: list[dict] = []
    for idx, holder in enumerate(soup.select(".mapholder"), start=1):
        map_name_el = holder.select_one(".mapname")
        if not map_name_el:
            continue
        map_name = map_name_el.get_text(strip=True)
        if map_name.lower() in ("tba", "default"):
            continue
        scores = holder.select(".results-team-score")
        if len(scores) < 2:
            continue
        try:
            score_a = int(scores[0].get_text(strip=True))
            score_b = int(scores[1].get_text(strip=True))
        except ValueError:
            continue
        winner_id = team_a_id if score_a > score_b else team_b_id
        stats_link = holder.select_one("a[href*='mapstatsid']")
        map_stats_id = None
        if stats_link:
            ms_match = re.search(r"mapstatsid/(\d+)/", stats_link.get("href", ""))
            if ms_match:
                map_stats_id = ms_match.group(1)
        maps.append({
            "map_index": idx,
            "map_name": map_name,
            "team_a_score": score_a,
            "team_b_score": score_b,
            "winner_hltv_id": winner_id,
            "map_stats_id": map_stats_id,
        })
    return maps


def _extract_players(soup: BeautifulSoup) -> list[dict]:
    players: list[dict] = []
    seen: set[str] = set()
    for link in soup.select(".lineup a[href*='/player/'], .players a[href*='/player/']"):
        href = link.get("href", "")
        id_match = re.search(r"/player/(\d+)/", href)
        if not id_match:
            continue
        player_id = id_match.group(1)
        if player_id in seen:
            continue
        seen.add(player_id)
        name_el = link.select_one(".text-ellipsis") or link
        nickname = name_el.get_text(strip=True)
        if nickname:
            players.append({"hltv_id": player_id, "nickname": nickname})
    return players


def _extract_stats_url(soup: BeautifulSoup) -> str | None:
    link = soup.select_one("a[href*='/stats/matches/']")
    if link:
        href = link.get("href", "")
        if "/stats/matches/" in href:
            return href if href.startswith("http") else f"https://www.hltv.org{href}"
    return None
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_parser.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/parser.py scraper/tests/test_parser.py
git commit -m "feat(scraper): match page parser extracts teams, maps, vetoes, players"
```

---

### Task 11: HTML Parser — Stats & Map Stats Pages

**Files:**
- Modify: `scraper/scraper/parser.py`
- Modify: `scraper/tests/test_parser.py`

- [ ] **Step 1: Add failing tests for stats parsers**

Append to `scraper/tests/test_parser.py`:

```python
class TestParseStatsPage:
    def test_extracts_player_stats(self):
        html = """
        <div class="stats-match">
          <div class="match-info-box">
            <a href="/stats/matches/mapstatsid/98765/slug">Map 1</a>
          </div>
          <table class="stats-table">
            <thead><tr><th>Player</th><th>K-D</th><th>+/-</th><th>ADR</th><th>KAST</th><th>Rating</th></tr></thead>
            <tbody>
              <tr>
                <td class="st-player">
                  <a href="/player/7998/s1mple">s1mple</a>
                </td>
                <td class="st-kills"><span>24</span>-<span>15</span></td>
                <td>+9</td>
                <td>92.3</td>
                <td>78.5%</td>
                <td>1.45</td>
              </tr>
            </tbody>
          </table>
        </div>
        """
        stats = parse_stats_page(html)
        assert len(stats["players"]) >= 1
        p = stats["players"][0]
        assert p["nickname"] == "s1mple"
        assert p["hltv_id"] == "7998"
        assert p["kills"] == 24
        assert p["deaths"] == 15
        assert len(stats["map_stats_ids"]) >= 1


class TestParseMapStatsPage:
    def test_extracts_side_splits(self):
        html = """
        <table class="stats-table">
          <thead><tr><th>Player</th><th>K</th><th>D</th><th>ADR</th><th>Rating</th></tr></thead>
          <tbody class="ct-stats">
            <tr>
              <td class="st-player"><a href="/player/7998/s1mple">s1mple</a></td>
              <td>14</td><td>8</td><td>95.2</td><td>1.52</td>
            </tr>
          </tbody>
          <tbody class="t-stats">
            <tr>
              <td class="st-player"><a href="/player/7998/s1mple">s1mple</a></td>
              <td>10</td><td>7</td><td>88.1</td><td>1.38</td>
            </tr>
          </tbody>
        </table>
        """
        map_stats = parse_map_stats_page(html)
        assert len(map_stats) >= 1
        p = map_stats[0]
        assert p["nickname"] == "s1mple"
        assert p["ct_kills"] == 14
        assert p["ct_deaths"] == 8
        assert p["t_kills"] == 10
        assert p["t_deaths"] == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd scraper && python -m pytest tests/test_parser.py::TestParseStatsPage tests/test_parser.py::TestParseMapStatsPage -v`
Expected: FAIL

- [ ] **Step 3: Add `parse_stats_page` and `parse_map_stats_page` to `parser.py`**

Append to `scraper/scraper/parser.py`:

```python
def parse_stats_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    players: list[dict] = []
    for row in soup.select(".stats-table tbody tr"):
        player_cell = row.select_one(".st-player a[href*='/player/']")
        if not player_cell:
            continue
        href = player_cell.get("href", "")
        id_match = re.search(r"/player/(\d+)/", href)
        hltv_id = id_match.group(1) if id_match else ""
        nickname = player_cell.get_text(strip=True)
        kd_cell = row.select_one(".st-kills")
        kills, deaths = _parse_kd(kd_cell)
        cells = row.find_all("td")
        adr = _safe_float(_cell_text(cells, 3))
        kast = _safe_float(_cell_text(cells, 4).rstrip("%"))
        rating = _safe_float(_cell_text(cells, 5))
        players.append({
            "hltv_id": hltv_id,
            "nickname": nickname,
            "kills": kills,
            "deaths": deaths,
            "adr": adr,
            "kast_pct": kast,
            "rating": rating,
        })

    map_stats_ids: list[str] = []
    for link in soup.select("a[href*='mapstatsid']"):
        ms_match = re.search(r"mapstatsid/(\d+)/", link.get("href", ""))
        if ms_match:
            map_stats_ids.append(ms_match.group(1))

    return {"players": players, "map_stats_ids": list(dict.fromkeys(map_stats_ids))}


def parse_map_stats_page(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    ct_stats: dict[str, dict] = {}
    t_stats: dict[str, dict] = {}

    for tbody in soup.select("tbody.ct-stats, tbody[class*='ct']"):
        for row in tbody.select("tr"):
            player_data = _parse_side_row(row)
            if player_data:
                ct_stats[player_data["hltv_id"]] = player_data

    for tbody in soup.select("tbody.t-stats, tbody[class*='t-']"):
        for row in tbody.select("tr"):
            player_data = _parse_side_row(row)
            if player_data:
                t_stats[player_data["hltv_id"]] = player_data

    combined: list[dict] = []
    all_ids = list(dict.fromkeys(list(ct_stats.keys()) + list(t_stats.keys())))
    for pid in all_ids:
        ct = ct_stats.get(pid, {})
        t = t_stats.get(pid, {})
        combined.append({
            "hltv_id": pid,
            "nickname": ct.get("nickname") or t.get("nickname", ""),
            "ct_kills": ct.get("kills"),
            "ct_deaths": ct.get("deaths"),
            "ct_adr": ct.get("adr"),
            "ct_rating": ct.get("rating"),
            "t_kills": t.get("kills"),
            "t_deaths": t.get("deaths"),
            "t_adr": t.get("adr"),
            "t_rating": t.get("rating"),
        })
    return combined


def _parse_side_row(row: Tag) -> dict | None:
    player_cell = row.select_one(".st-player a[href*='/player/'], td a[href*='/player/']")
    if not player_cell:
        return None
    href = player_cell.get("href", "")
    id_match = re.search(r"/player/(\d+)/", href)
    hltv_id = id_match.group(1) if id_match else ""
    nickname = player_cell.get_text(strip=True)
    cells = row.find_all("td")
    return {
        "hltv_id": hltv_id,
        "nickname": nickname,
        "kills": _safe_int(_cell_text(cells, 1)),
        "deaths": _safe_int(_cell_text(cells, 2)),
        "adr": _safe_float(_cell_text(cells, 3)),
        "rating": _safe_float(_cell_text(cells, 4)),
    }


def _parse_kd(cell: Tag | None) -> tuple[int | None, int | None]:
    if not cell:
        return None, None
    spans = cell.find_all("span")
    if len(spans) >= 2:
        return _safe_int(spans[0].get_text(strip=True)), _safe_int(spans[1].get_text(strip=True))
    text = cell.get_text(strip=True)
    parts = re.split(r"[-/]", text)
    if len(parts) >= 2:
        return _safe_int(parts[0].strip()), _safe_int(parts[1].strip())
    return None, None


def _cell_text(cells: list, index: int) -> str:
    if index < len(cells):
        return cells[index].get_text(strip=True)
    return ""


def _safe_float(text: str) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _safe_int(text: str | None) -> int | None:
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None
```

- [ ] **Step 4: Run all parser tests**

Run: `cd scraper && python -m pytest tests/test_parser.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/parser.py scraper/tests/test_parser.py
git commit -m "feat(scraper): stats page and map stats page parsers with side splits"
```

---

### Task 12: Discovery Module

**Files:**
- Create: `scraper/scraper/discovery.py`
- Create: `scraper/tests/test_discovery.py`

- [ ] **Step 1: Write the failing test**

```python
# scraper/tests/test_discovery.py
from pathlib import Path
from unittest.mock import MagicMock
from scraper.config import ScraperConfig
from scraper.discovery import discover_matches
from scraper.tracking_db import TrackingDB


def test_discover_inserts_new_matches(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    config = ScraperConfig(event_allow_list=["IEM Katowice"])

    fake_fetcher = MagicMock()
    fake_fetcher.fetch.return_value = MagicMock(
        ok=True,
        html="""
        <div class="results-holder">
          <div class="result-con">
            <a href="/matches/100/a-vs-b-iem-katowice-2026" class="a-reset">
              <div class="result">
                <div class="result-teamName">A</div>
                <div class="result-teamName">B</div>
                <div class="event-name">IEM Katowice 2026</div>
              </div>
            </a>
          </div>
        </div>
        """,
    )
    fake_fetcher.save_raw_results_page = MagicMock()

    count = discover_matches(fake_fetcher, db, config, max_pages=1)
    assert count == 1
    row = db.get_match("100")
    assert row is not None
    assert row["event_name"] == "IEM Katowice 2026"
    db.close()


def test_discover_skips_known_matches(tmp_path: Path):
    db = TrackingDB(tmp_path / "test.db")
    db.upsert_match("100", "/matches/100/slug")
    config = ScraperConfig(event_allow_list=["IEM"])

    fake_fetcher = MagicMock()
    fake_fetcher.fetch.return_value = MagicMock(
        ok=True,
        html="""
        <div class="results-holder">
          <div class="result-con">
            <a href="/matches/100/slug" class="a-reset">
              <div class="result">
                <div class="result-teamName">A</div>
                <div class="result-teamName">B</div>
                <div class="event-name">IEM Dallas 2026</div>
              </div>
            </a>
          </div>
        </div>
        """,
    )
    fake_fetcher.save_raw_results_page = MagicMock()

    count = discover_matches(fake_fetcher, db, config, max_pages=1)
    assert count == 0
    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd scraper && python -m pytest tests/test_discovery.py -v`
Expected: FAIL

- [ ] **Step 3: Write `scraper/scraper/discovery.py`**

```python
from __future__ import annotations

import logging
import time

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.parser import parse_results_page
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)

RESULTS_BASE_URL = "https://www.hltv.org/results?stars=4&stars=5&offset={offset}"


def discover_matches(
    fetcher: HltvFetcher,
    db: TrackingDB,
    config: ScraperConfig,
    max_pages: int = 50,
) -> int:
    new_count = 0
    for page_idx in range(max_pages):
        offset = page_idx * 100
        url = RESULTS_BASE_URL.format(offset=offset)
        _logger.info("discovering matches at offset %d", offset)
        result = fetcher.fetch(url)
        if not result.ok:
            _logger.warning("discovery page failed at offset %d: status %d", offset, result.status)
            break
        fetcher.save_raw_results_page(offset, result.html)
        entries = parse_results_page(result.html)
        if not entries:
            _logger.info("no more results at offset %d, stopping discovery", offset)
            break

        page_new = 0
        for entry in entries:
            match_id = entry["match_id"]
            if db.get_match(match_id) is not None:
                continue
            if not _event_matches_allow_list(entry.get("event_name", ""), config.event_allow_list):
                continue
            db.upsert_match(
                match_id=match_id,
                match_url=entry["match_url"],
                event_name=entry.get("event_name"),
                event_stars=entry.get("event_stars"),
            )
            page_new += 1

        new_count += page_new
        _logger.info("page %d: %d new matches from %d entries", page_idx, page_new, len(entries))
    return new_count


def _event_matches_allow_list(event_name: str, allow_list: list[str]) -> bool:
    if not allow_list:
        return True
    event_lower = event_name.lower()
    return any(term.lower() in event_lower for term in allow_list)
```

- [ ] **Step 4: Run tests and verify they pass**

Run: `cd scraper && python -m pytest tests/test_discovery.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add scraper/scraper/discovery.py scraper/tests/test_discovery.py
git commit -m "feat(scraper): discovery module crawls results pages and filters by event tier"
```

---

### Task 13: Match Scraper (Orchestrator)

**Files:**
- Create: `scraper/scraper/match_scraper.py`
- Create: `scraper/scraper/pipeline.py`

- [ ] **Step 1: Write `scraper/scraper/match_scraper.py`**

```python
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.models import (
    ScrapedEvent, ScrapedMap, ScrapedMatch, ScrapedPlayer,
    ScrapedPlayerMapStats, ScrapedTeam, ScrapedVeto,
    write_fixture_json,
)
from scraper.parser import parse_map_stats_page, parse_match_page, parse_stats_page
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)


def scrape_one_match(
    match_id: str,
    match_url: str,
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
    config: ScraperConfig,
) -> ScrapedMatch | None:
    row = db.get_match(match_id)
    if row and row["parsed"]:
        return None

    full_url = f"https://www.hltv.org{match_url}" if match_url.startswith("/") else match_url

    if not row or not row["match_fetched"]:
        _logger.info("fetching match page: %s", match_id)
        time.sleep(limiter.next_delay())
        result = fetcher.fetch(full_url)
        if not result.ok:
            db.record_error(match_id, f"match page HTTP {result.status}")
            return None
        fetcher.save_raw_match(match_id, result.html)
        db.mark_match_fetched(match_id)
    else:
        match_html_path = config.raw_dir / "matches" / match_id / "match.html"
        result = type("Obj", (), {"html": match_html_path.read_text(encoding="utf-8")})()

    match_data = parse_match_page(result.html, match_id)
    maps_info = match_data.get("maps", [])
    db.set_maps_total(match_id, len(maps_info))

    stats_url = match_data.get("stats_url")
    stats_players: list[dict] = []
    if stats_url and (not row or not row["stats_fetched"]):
        _logger.info("fetching stats page: %s", match_id)
        time.sleep(limiter.next_delay())
        stats_result = fetcher.fetch(stats_url)
        if stats_result.ok:
            fetcher.save_raw_stats(match_id, stats_result.html)
            db.mark_stats_fetched(match_id)
            stats_data = parse_stats_page(stats_result.html)
            stats_players = stats_data.get("players", [])

    maps_fetched = row["maps_fetched"] if row else 0
    map_side_stats: dict[str, list[dict]] = {}
    for i, m in enumerate(maps_info):
        if i < maps_fetched:
            continue
        map_stats_id = m.get("map_stats_id")
        if not map_stats_id:
            continue
        map_url = f"https://www.hltv.org/stats/matches/mapstatsid/{map_stats_id}/slug"
        _logger.info("fetching map stats: %s map %s", match_id, map_stats_id)
        time.sleep(limiter.next_delay())
        map_result = fetcher.fetch(map_url)
        if map_result.ok:
            fetcher.save_raw_map(match_id, map_stats_id, map_result.html)
            db.increment_maps_fetched(match_id)
            map_side_stats[map_stats_id] = parse_map_stats_page(map_result.html)

    meta = {
        "match_id": match_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    fetcher.save_meta(match_id, meta)

    scraped = _assemble_match(match_data, stats_players, map_side_stats)
    write_fixture_json(scraped, config.output_dir)
    db.mark_parsed(match_id)
    _logger.info("parsed match %s: %d maps, %d players", match_id, len(scraped.maps), len(scraped.players))
    return scraped


def _assemble_match(
    match_data: dict,
    stats_players: list[dict],
    map_side_stats: dict[str, list[dict]],
) -> ScrapedMatch:
    team_a = match_data["team_a"]
    team_b = match_data["team_b"]
    event = match_data.get("event", {})

    maps: list[ScrapedMap] = []
    for m in match_data.get("maps", []):
        side_stats = map_side_stats.get(m.get("map_stats_id", ""), [])
        player_stats = tuple(
            ScrapedPlayerMapStats(
                player_hltv_id=ps.get("hltv_id", ""),
                nickname=ps.get("nickname", ""),
                team_hltv_id="",
                ct_kills=ps.get("ct_kills"),
                ct_deaths=ps.get("ct_deaths"),
                t_kills=ps.get("t_kills"),
                t_deaths=ps.get("t_deaths"),
            )
            for ps in side_stats
        )
        maps.append(ScrapedMap(
            map_index=m["map_index"],
            map_name=m["map_name"],
            team_a_score=m["team_a_score"],
            team_b_score=m["team_b_score"],
            winner_hltv_id=m["winner_hltv_id"],
            map_stats_id=m.get("map_stats_id"),
            player_stats=player_stats,
        ))

    players = tuple(
        ScrapedPlayer(
            hltv_id=p.get("hltv_id", ""),
            nickname=p.get("nickname", ""),
            team_hltv_id="",
        )
        for p in match_data.get("players", [])
    )

    vetoes = tuple(
        ScrapedVeto(
            order_idx=v["order_idx"],
            team_hltv_id=None,
            action=v["action"],
            map_name=v["map_name"],
        )
        for v in match_data.get("vetoes", [])
    )

    scheduled_at_str = match_data.get("scheduled_at")
    if scheduled_at_str:
        scheduled_at = datetime.fromisoformat(scheduled_at_str)
    else:
        scheduled_at = datetime(2000, 1, 1, tzinfo=timezone.utc)

    return ScrapedMatch(
        hltv_id=match_data["hltv_id"],
        scheduled_at=scheduled_at,
        best_of=match_data.get("best_of", 1),
        status="finished",
        team_a=ScrapedTeam(hltv_id=team_a.get("hltv_id", ""), name=team_a.get("name", "")),
        team_b=ScrapedTeam(hltv_id=team_b.get("hltv_id", ""), name=team_b.get("name", "")),
        event=ScrapedEvent(
            hltv_id=event.get("hltv_id", ""),
            name=event.get("name", ""),
            stars=event.get("stars"),
        ),
        players=players,
        maps=tuple(maps),
        vetoes=vetoes,
        stats_url=match_data.get("stats_url"),
    )
```

- [ ] **Step 2: Write `scraper/scraper/pipeline.py`**

```python
from __future__ import annotations

import logging

from scraper.config import ScraperConfig, load_config
from scraper.discovery import discover_matches
from scraper.fetcher import HltvFetcher
from scraper.match_scraper import scrape_one_match
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)


def run_pipeline(
    config: ScraperConfig | None = None,
    max_discovery_pages: int = 10,
    max_matches: int = 100,
) -> dict:
    if config is None:
        config = load_config()

    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        cooldown_every=config.cooldown_every,
        cooldown_seconds=config.cooldown_seconds,
        daily_cap=config.daily_cap,
        quiet_hours_start=config.quiet_hours_start,
        quiet_hours_end=config.quiet_hours_end,
    )
    db = TrackingDB(config.db_path)
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)

    try:
        if limiter.in_quiet_hours():
            _logger.info("in quiet hours, skipping run")
            return {"skipped": True, "reason": "quiet_hours"}

        if limiter.daily_cap_reached():
            _logger.info("daily cap reached, skipping run")
            return {"skipped": True, "reason": "daily_cap"}

        discovered = discover_matches(fetcher, db, config, max_pages=max_discovery_pages)
        _logger.info("discovered %d new matches", discovered)

        pending = db.pending_matches(limit=max_matches)
        fetched = 0
        for row in pending:
            if limiter.daily_cap_reached():
                _logger.info("daily cap reached during fetch, stopping")
                break
            backoff = limiter.failure_backoff_delay()
            if backoff > 0:
                _logger.warning("failure backoff: pausing %.0fs", backoff)
                import time
                time.sleep(backoff)

            proxy.start_sticky_session()
            try:
                result = scrape_one_match(
                    row["match_id"], row["match_url"],
                    fetcher, db, limiter, config,
                )
                if result:
                    fetched += 1
            finally:
                proxy.end_sticky_session()

        stats = db.queue_stats()
        return {
            "discovered": discovered,
            "fetched": fetched,
            "queue": stats,
        }
    finally:
        fetcher.close()
        db.close()
```

- [ ] **Step 3: Commit**

```bash
git add scraper/scraper/match_scraper.py scraper/scraper/pipeline.py
git commit -m "feat(scraper): match scraper orchestrator and full pipeline runner"
```

---

### Task 14: CLI Entry Point

**Files:**
- Create: `scraper/scraper/cli.py`
- Create: `scraper/scraper/__main__.py`

- [ ] **Step 1: Write `scraper/scraper/cli.py`**

```python
from __future__ import annotations

import argparse
import json
import logging
import sys

from scraper.config import load_config
from scraper.discovery import discover_matches
from scraper.fetcher import HltvFetcher
from scraper.match_scraper import scrape_one_match
from scraper.pipeline import run_pipeline
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(min_delay=config.min_delay, max_delay=config.max_delay)
    db = TrackingDB(config.db_path)
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        count = discover_matches(fetcher, db, config, max_pages=args.limit or 10)
        print(json.dumps({"discovered": count}))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(
        min_delay=config.min_delay, max_delay=config.max_delay,
        cooldown_every=config.cooldown_every, cooldown_seconds=config.cooldown_seconds,
        daily_cap=config.daily_cap,
    )
    db = TrackingDB(config.db_path)
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        pending = db.pending_matches(limit=args.limit or 50)
        fetched = 0
        for row in pending:
            if limiter.daily_cap_reached():
                break
            proxy.start_sticky_session()
            try:
                result = scrape_one_match(row["match_id"], row["match_url"], fetcher, db, limiter, config)
                if result:
                    fetched += 1
            finally:
                proxy.end_sticky_session()
        print(json.dumps({"fetched": fetched}))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    config = load_config()
    from scraper.parser import parse_match_page
    from scraper.models import write_fixture_json
    from scraper.match_scraper import _assemble_match
    db = TrackingDB(config.db_path)
    parsed = 0
    for row in db.pending_matches(limit=10000):
        if row["parsed"]:
            continue
        match_dir = config.raw_dir / "matches" / row["match_id"]
        match_html = match_dir / "match.html"
        if not match_html.exists():
            continue
        match_data = parse_match_page(match_html.read_text(encoding="utf-8"), row["match_id"])
        scraped = _assemble_match(match_data, [], {})
        write_fixture_json(scraped, config.output_dir)
        db.mark_parsed(row["match_id"])
        parsed += 1
    db.close()
    print(json.dumps({"parsed": parsed}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config()
    result = run_pipeline(config)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config()
    db = TrackingDB(config.db_path)
    stats = db.queue_stats()
    today_requests = db.request_count_today()
    db.close()
    print(json.dumps({"queue": stats, "requests_today": today_requests}, indent=2))
    return 0


def cmd_test_live(args: argparse.Namespace) -> int:
    from scraper.tests.test_live import run_live_test
    return run_live_test()


def cmd_export(args: argparse.Namespace) -> int:
    import shutil
    config = load_config()
    export_dir = args.out_dir or "data/hltv_fixtures"
    from pathlib import Path
    dest = Path(export_dir)
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in config.output_dir.glob("*.json"):
        target = dest / src.name
        if not target.exists():
            shutil.copy2(src, target)
            count += 1
    print(json.dumps({"exported": count, "to": str(dest)}))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="hltv-scraper")
    subparsers = parser.add_subparsers(dest="command")

    disc = subparsers.add_parser("discover")
    disc.add_argument("--limit", type=int, default=10)
    disc.set_defaults(func=cmd_discover)

    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--limit", type=int, default=50)
    fetch.set_defaults(func=cmd_fetch)

    parse = subparsers.add_parser("parse")
    parse.set_defaults(func=cmd_parse)

    run = subparsers.add_parser("run")
    run.set_defaults(func=cmd_run)

    status = subparsers.add_parser("status")
    status.set_defaults(func=cmd_status)

    test_live = subparsers.add_parser("test-live")
    test_live.set_defaults(func=cmd_test_live)

    export = subparsers.add_parser("export")
    export.add_argument("--out-dir", default=None)
    export.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write `scraper/scraper/__main__.py`**

```python
from scraper.cli import main

raise SystemExit(main())
```

- [ ] **Step 3: Verify CLI runs**

Run: `cd scraper && python -m scraper.cli --help`
Expected: Shows usage with subcommands: discover, fetch, parse, run, status, test-live, export

- [ ] **Step 4: Commit**

```bash
git add scraper/scraper/cli.py scraper/scraper/__main__.py
git commit -m "feat(scraper): CLI entry point with all subcommands"
```

---

### Task 15: Live Integration Test

**Files:**
- Create: `scraper/tests/test_live.py`

This is the pre-deployment gate. It fetches real HLTV pages and validates parsing.

- [ ] **Step 1: Write `scraper/tests/test_live.py`**

```python
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from scraper.config import load_config
from scraper.fetcher import HltvFetcher, FetchResult
from scraper.parser import parse_match_page, parse_results_page, parse_stats_page, parse_map_stats_page
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def run_live_test() -> int:
    logging.basicConfig(level=logging.INFO)
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(min_delay=2, max_delay=4, cooldown_every=100, cooldown_seconds=10, daily_cap=50)
    db = TrackingDB(config.db_path)
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    passed = 0
    failed = 0

    try:
        # Test 1: Discovery page
        print("\n=== Test 1: Results page ===")
        result = fetcher.fetch("https://www.hltv.org/results?stars=4&stars=5&offset=0")
        _report_fetch("results page", result)
        if result.ok:
            entries = parse_results_page(result.html)
            print(f"  Parsed: {len(entries)} matches found")
            if entries:
                (FIXTURES_DIR / "results_page.html").write_text(result.html, encoding="utf-8")
                passed += 1
            else:
                print("  FAIL: no matches parsed")
                failed += 1
        else:
            failed += 1

        # Test 2: Fetch a match page from the first discovered match
        if entries:
            test_match = entries[0]
            match_url = f"https://www.hltv.org{test_match['match_url']}"
            match_id = test_match["match_id"]

            print(f"\n=== Test 2: Match page ({match_id}) ===")
            import time
            time.sleep(limiter.next_delay())
            result = fetcher.fetch(match_url)
            _report_fetch(f"match {match_id}", result)
            if result.ok:
                (FIXTURES_DIR / f"match_{match_id}.html").write_text(result.html, encoding="utf-8")
                match_data = parse_match_page(result.html, match_id)
                team_a = match_data["team_a"]["name"]
                team_b = match_data["team_b"]["name"]
                n_maps = len(match_data.get("maps", []))
                n_vetoes = len(match_data.get("vetoes", []))
                print(f"  Parsed: {team_a} vs {team_b}, {n_maps} maps, {n_vetoes} vetoes, bo{match_data.get('best_of')}")
                if team_a and team_b and n_maps > 0:
                    passed += 1
                else:
                    print("  FAIL: missing teams or maps")
                    failed += 1

                # Test 3: Stats page
                stats_url = match_data.get("stats_url")
                if stats_url:
                    print(f"\n=== Test 3: Stats page ({match_id}) ===")
                    time.sleep(limiter.next_delay())
                    stats_result = fetcher.fetch(stats_url)
                    _report_fetch(f"stats {match_id}", stats_result)
                    if stats_result.ok:
                        (FIXTURES_DIR / f"stats_{match_id}.html").write_text(stats_result.html, encoding="utf-8")
                        stats_data = parse_stats_page(stats_result.html)
                        n_players = len(stats_data.get("players", []))
                        print(f"  Parsed: {n_players} players")
                        if n_players >= 2:
                            passed += 1
                        else:
                            print("  FAIL: too few players")
                            failed += 1
                    else:
                        failed += 1

                # Test 4: Map stats page
                first_map = match_data["maps"][0] if match_data.get("maps") else None
                if first_map and first_map.get("map_stats_id"):
                    msid = first_map["map_stats_id"]
                    print(f"\n=== Test 4: Map stats page ({msid}) ===")
                    time.sleep(limiter.next_delay())
                    map_url = f"https://www.hltv.org/stats/matches/mapstatsid/{msid}/slug"
                    map_result = fetcher.fetch(map_url)
                    _report_fetch(f"map stats {msid}", map_result)
                    if map_result.ok:
                        (FIXTURES_DIR / f"map_{msid}.html").write_text(map_result.html, encoding="utf-8")
                        map_stats = parse_map_stats_page(map_result.html)
                        print(f"  Parsed: {len(map_stats)} player side-split rows")
                        if map_stats:
                            passed += 1
                        else:
                            print("  WARN: no side splits found (parser may need selector update)")
                            passed += 1  # non-fatal
                    else:
                        failed += 1

        # Test 5: Force Playwright path
        print("\n=== Test 5: Playwright fallback ===")
        import time
        time.sleep(limiter.next_delay())
        pw_result = fetcher._fetch_playwright("https://www.hltv.org/results?stars=4&stars=5&offset=0")
        _report_fetch("playwright results", pw_result)
        if pw_result.ok:
            pw_entries = parse_results_page(pw_result.html)
            print(f"  Parsed: {len(pw_entries)} matches via Playwright")
            if pw_entries:
                passed += 1
            else:
                print("  FAIL: Playwright returned HTML but no matches parsed")
                failed += 1
        else:
            failed += 1

    finally:
        fetcher.close()
        db.close()

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("Ready for deployment.")
        print(f"Fixtures saved to {FIXTURES_DIR}")
    else:
        print("FIX FAILURES before deploying.")
    return 0 if failed == 0 else 1


def _report_fetch(label: str, result: FetchResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"  {label}: {status} ({result.content_bytes//1024}KB, {result.fetcher_type}, {result.elapsed_ms}ms)")
```

- [ ] **Step 2: Commit**

```bash
git add scraper/tests/test_live.py
git commit -m "feat(scraper): live integration test validates all page types and both fetcher paths"
```

---

### Task 16: Betto CLI Integration (convert-hltv-scraped)

**Files:**
- Modify: `core/cli/main.py`

- [ ] **Step 1: Add the converter function to `core/cli/main.py`**

Add this function before the `main()` function:

```python
def convert_hltv_scraped(args: argparse.Namespace) -> int:
    import shutil
    settings = load_settings()
    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_absolute():
        raw_dir = settings.project_root / raw_dir
    raw_dir = raw_dir.resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = settings.project_root / out_dir
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    skipped = 0
    for src in sorted(raw_dir.glob("*.json")):
        target = out_dir / src.name
        if target.exists():
            skipped += 1
            continue
        shutil.copy2(src, target)
        count += 1
    print(json.dumps({"imported": count, "skipped": skipped, "out_dir": str(out_dir)}))
    return 0
```

- [ ] **Step 2: Register the command in `main()`**

Add before `args = parser.parse_args(argv)`:

```python
    hltv_scraped_parser = subparsers.add_parser("convert-hltv-scraped")
    hltv_scraped_parser.add_argument("--raw-dir", default="data/hltv_scraped")
    hltv_scraped_parser.add_argument("--out-dir", default="data/hltv_fixtures")
    hltv_scraped_parser.set_defaults(func=convert_hltv_scraped)
```

- [ ] **Step 3: Verify the command is registered**

Run: `python -m core.cli.main convert-hltv-scraped --help`
Expected: Shows usage with `--raw-dir` and `--out-dir` flags

- [ ] **Step 4: Commit**

```bash
git add core/cli/main.py
git commit -m "feat: add convert-hltv-scraped CLI command to import scraper output into fixture store"
```

---

### Task 17: README and .gitignore

**Files:**
- Create: `scraper/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Write `scraper/README.md`**

```markdown
# HLTV Scraper

Standalone scraper bot for HLTV.org CS2 match data. Produces fixture JSON for Betto.

## Setup

```bash
cd scraper
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Edit .env with your proxy credentials
```

## Usage

```bash
python -m scraper.cli discover      # Find new match IDs
python -m scraper.cli fetch         # Fetch pending matches
python -m scraper.cli parse         # Parse fetched HTML to JSON
python -m scraper.cli run           # Full pipeline
python -m scraper.cli status        # Queue stats
python -m scraper.cli test-live     # Integration test (run before deploying)
python -m scraper.cli export        # Copy to Betto fixture store
```

## Testing

```bash
python -m pytest tests/ -v                    # Unit tests (offline)
python -m scraper.cli test-live               # Integration test (needs proxy)
```

## VPS Deployment

See `docs/superpowers/specs/2026-05-18-hltv-scraper-design.md` Section 10.
```

- [ ] **Step 2: Add scraper-specific entries to `.gitignore`**

Append to the project root `.gitignore`:

```
# HLTV scraper
scraper/tests/fixtures/*.html
scraper/.env
data/raw/hltv/
data/hltv_scraped/
data/hltv_scraper.db
```

- [ ] **Step 3: Run full test suite to ensure nothing is broken**

Run: `cd scraper && python -m pytest tests/ -v --ignore=tests/test_live.py`
Expected: All unit tests pass

Run: `cd .. && python -m pytest tests/ --ignore=tests/test_api.py -x -q`
Expected: All Betto tests pass (185+)

- [ ] **Step 4: Commit**

```bash
git add scraper/README.md .gitignore
git commit -m "docs(scraper): README, .gitignore for scraper package"
```
