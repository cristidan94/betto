# HLTV Scraper Ingestion Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect VPS HLTV scraper output to the Betto platform with full-fidelity data ingestion — no rich fields dropped. Incremental import support so future scraper runs only process new matches.

**Architecture:** Extend the existing parse → normalize → upsert pipeline to capture all scraper fields (player stats, half scores, head-to-head, overtime, CT/T splits, match_stage). Add a new bulk CLI command with incremental skip. Schema migration adds columns to existing tables.

**Tech Stack:** Python 3.12, PostgreSQL 16, FastAPI, unittest

---

### Task 1: Schema Migration

**Files:**
- Create: `infra/migrations/0006_hltv_scraper_rich_data.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Extend CS tables for full-fidelity HLTV scraper data.

ALTER TABLE cs_map_results
  ADD COLUMN IF NOT EXISTS map_stats_id      TEXT,
  ADD COLUMN IF NOT EXISTS overtime          BOOLEAN,
  ADD COLUMN IF NOT EXISTS team_a_first_half INT,
  ADD COLUMN IF NOT EXISTS team_a_second_half INT,
  ADD COLUMN IF NOT EXISTS team_b_first_half INT,
  ADD COLUMN IF NOT EXISTS team_b_second_half INT;

ALTER TABLE cs_player_map_stats
  ADD COLUMN IF NOT EXISTS ct_kills       INT,
  ADD COLUMN IF NOT EXISTS ct_deaths      INT,
  ADD COLUMN IF NOT EXISTS t_kills        INT,
  ADD COLUMN IF NOT EXISTS t_deaths       INT,
  ADD COLUMN IF NOT EXISTS flash_assists  INT,
  ADD COLUMN IF NOT EXISTS trade_deaths   INT;

ALTER TABLE contests
  ADD COLUMN IF NOT EXISTS match_stage   TEXT,
  ADD COLUMN IF NOT EXISTS head_to_head  JSONB;
```

- [ ] **Step 2: Verify migration is discovered**

Run: `python -m core.cli migrations --root .`
Expected: list includes `0006_hltv_scraper_rich_data.sql`

- [ ] **Step 3: Commit**

```bash
git add infra/migrations/0006_hltv_scraper_rich_data.sql
git commit -m "feat: add migration 0006 for HLTV scraper rich data columns"
```

---

### Task 2: Extend Parsed Records

**Files:**
- Modify: `sports/cs/normalization/records.py`
- Test: `tests/test_hltv_fixture_normalization.py`

- [ ] **Step 1: Write the failing test for new record fields**

Add to `tests/test_hltv_fixture_normalization.py`:

```python
from sports.cs.normalization.records import CsParsedMap, CsParsedMatch, CsParsedPlayerMapStats


class RecordDefaultsTests(unittest.TestCase):
    def test_parsed_map_has_rich_fields_with_defaults(self) -> None:
        basic = CsParsedMap(1, "Mirage", 13, 9, "4608")
        self.assertIsNone(basic.map_stats_id)
        self.assertIsNone(basic.overtime)
        self.assertIsNone(basic.team_a_first_half)
        self.assertIsNone(basic.team_b_first_half)
        self.assertEqual(basic.player_stats, ())

    def test_parsed_map_accepts_rich_fields(self) -> None:
        rich = CsParsedMap(
            map_index=1, map_name="Dust2", team_a_score=13, team_b_score=6,
            winner_hltv_id="13644", map_stats_id="230451", overtime=False,
            team_a_first_half=7, team_a_second_half=6,
            team_b_first_half=5, team_b_second_half=1,
            player_stats=(
                CsParsedPlayerMapStats(player_hltv_id="16555", team_hltv_id="13644", kills=19, deaths=10),
            ),
        )
        self.assertEqual(rich.map_stats_id, "230451")
        self.assertFalse(rich.overtime)
        self.assertEqual(rich.team_a_first_half, 7)
        self.assertEqual(rich.team_b_second_half, 1)
        self.assertEqual(len(rich.player_stats), 1)
        self.assertEqual(rich.player_stats[0].kills, 19)
        self.assertIsNone(rich.player_stats[0].assists)

    def test_parsed_match_has_rich_fields_with_defaults(self) -> None:
        from sports.cs.normalization.records import CsParsedEvent, CsParsedTeam
        from datetime import datetime, timezone
        match = CsParsedMatch(
            hltv_id="1", scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            best_of=1, status="finished",
            team_a=CsParsedTeam("1", "A"), team_b=CsParsedTeam("2", "B"),
            event=CsParsedEvent("1", "Test"), players=(), maps=(), vetoes=(),
        )
        self.assertIsNone(match.match_stage)
        self.assertIsNone(match.head_to_head)

    def test_parsed_player_map_stats_all_nullable(self) -> None:
        stats = CsParsedPlayerMapStats(player_hltv_id="16555", team_hltv_id="13644")
        self.assertIsNone(stats.kills)
        self.assertIsNone(stats.ct_kills)
        self.assertIsNone(stats.flash_assists)
        self.assertIsNone(stats.trade_deaths)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hltv_fixture_normalization.RecordDefaultsTests -v`
Expected: ImportError or TypeError (CsParsedPlayerMapStats doesn't exist, CsParsedMap doesn't accept new fields)

- [ ] **Step 3: Add CsParsedPlayerMapStats and extend CsParsedMap / CsParsedMatch**

In `sports/cs/normalization/records.py`, add after the `CsParsedVeto` class:

```python
@dataclass(frozen=True)
class CsParsedPlayerMapStats:
    player_hltv_id: str
    team_hltv_id: str
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    adr: float | None = None
    rating: float | None = None
    kast_pct: float | None = None
    headshot_pct: float | None = None
    first_kills: int | None = None
    clutches_won: int | None = None
    ct_kills: int | None = None
    ct_deaths: int | None = None
    t_kills: int | None = None
    t_deaths: int | None = None
    flash_assists: int | None = None
    trade_deaths: int | None = None
```

Extend `CsParsedMap` — add fields after `winner_hltv_id`:

```python
@dataclass(frozen=True)
class CsParsedMap:
    map_index: int
    map_name: str
    team_a_score: int
    team_b_score: int
    winner_hltv_id: str
    map_stats_id: str | None = None
    overtime: bool | None = None
    team_a_first_half: int | None = None
    team_a_second_half: int | None = None
    team_b_first_half: int | None = None
    team_b_second_half: int | None = None
    player_stats: tuple[CsParsedPlayerMapStats, ...] = ()
```

Extend `CsParsedMatch` — add fields after `vetoes`:

```python
@dataclass(frozen=True)
class CsParsedMatch:
    hltv_id: str
    scheduled_at: datetime
    best_of: int
    status: str
    team_a: CsParsedTeam
    team_b: CsParsedTeam
    event: CsParsedEvent
    players: tuple[CsParsedPlayer, ...]
    maps: tuple[CsParsedMap, ...]
    vetoes: tuple[CsParsedVeto, ...]
    match_stage: str | None = None
    head_to_head: dict[str, int] | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_hltv_fixture_normalization.RecordDefaultsTests -v`
Expected: 4 tests PASS

- [ ] **Step 5: Run all existing normalization tests to verify no regressions**

Run: `python -m unittest tests.test_hltv_fixture_normalization -v`
Expected: all existing tests still PASS (new fields have defaults)

- [ ] **Step 6: Commit**

```bash
git add sports/cs/normalization/records.py tests/test_hltv_fixture_normalization.py
git commit -m "feat: add CsParsedPlayerMapStats and rich fields to CsParsedMap/CsParsedMatch"
```

---

### Task 3: Extend HLTV Parser

**Files:**
- Modify: `sports/cs/normalization/hltv_fixture.py`
- Test: `tests/test_hltv_fixture_normalization.py`

- [ ] **Step 1: Write failing test for rich map parsing**

Add to `tests/test_hltv_fixture_normalization.py` — a new fixture dict and test class:

```python
RICH_FIXTURE = {
    "hltv_id": "2394722",
    "schema_version": "hltv-fixture-v1",
    "source": {"name": "hltv-scraper", "url": "https://example.com", "stats_url": "https://example.com/stats"},
    "status": "finished",
    "best_of": 3,
    "match_stage": "Round of 16",
    "scheduled_at": "2026-05-29T17:00:00+00:00",
    "event": {"hltv_id": "9171", "name": "Thunderpick World Championship", "tier": 2, "hltv_stars": 0},
    "team_a": {"hltv_id": "13644", "name": "TDK"},
    "team_b": {"hltv_id": "13403", "name": "TNC"},
    "head_to_head": {"team_a_wins": 3, "team_b_wins": 2},
    "players": [
        {"hltv_id": "16555", "nickname": "Ax1Le", "team_hltv_id": "13644"},
        {"hltv_id": "20312", "nickname": "deko", "team_hltv_id": "13403"},
    ],
    "vetoes": [
        {"order_idx": 1, "action": "ban", "map_name": "Nuke", "team_hltv_id": "13644"},
        {"order_idx": 2, "action": "pick", "map_name": "Dust2", "team_hltv_id": "13403"},
        {"order_idx": 3, "action": "decider", "map_name": "Mirage", "team_hltv_id": None},
    ],
    "maps": [{
        "map_index": 1, "map_name": "Dust2", "map_stats_id": "230451",
        "overtime": False, "winner_hltv_id": "13644",
        "team_a_score": 13, "team_a_first_half": 7, "team_a_second_half": 6,
        "team_b_score": 6, "team_b_first_half": 5, "team_b_second_half": 1,
        "player_stats": {
            "ax1le": {
                "kills": 19, "deaths": 10, "adr": 94.6, "rating": 1.77, "kast_pct": 84.2,
                "ct_kills": 9, "ct_deaths": 3, "t_kills": 10, "t_deaths": 7,
                "assists": None, "headshot_pct": None, "first_kills": None, "clutches_won": None,
                "flash_assists": None, "trade_deaths": None,
            },
            "deko": {
                "kills": 8, "deaths": 15, "adr": 55.3, "rating": 0.72, "kast_pct": 63.2,
                "ct_kills": 4, "ct_deaths": 8, "t_kills": 4, "t_deaths": 7,
                "assists": 3, "headshot_pct": 50.0, "first_kills": 1, "clutches_won": 0,
                "flash_assists": 2, "trade_deaths": 1,
            },
        },
    }],
}


class RichParserTests(unittest.TestCase):
    def test_parse_extracts_match_stage_and_head_to_head(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        self.assertEqual(parsed.match_stage, "Round of 16")
        self.assertEqual(parsed.head_to_head, {"team_a_wins": 3, "team_b_wins": 2})

    def test_parse_extracts_map_rich_fields(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        m = parsed.maps[0]
        self.assertEqual(m.map_stats_id, "230451")
        self.assertFalse(m.overtime)
        self.assertEqual(m.team_a_first_half, 7)
        self.assertEqual(m.team_a_second_half, 6)
        self.assertEqual(m.team_b_first_half, 5)
        self.assertEqual(m.team_b_second_half, 1)

    def test_parse_extracts_player_stats_with_id_resolution(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        stats = parsed.maps[0].player_stats
        self.assertEqual(len(stats), 2)
        ax1le = next(s for s in stats if s.player_hltv_id == "16555")
        self.assertEqual(ax1le.team_hltv_id, "13644")
        self.assertEqual(ax1le.kills, 19)
        self.assertEqual(ax1le.ct_kills, 9)
        self.assertIsNone(ax1le.assists)

        deko = next(s for s in stats if s.player_hltv_id == "20312")
        self.assertEqual(deko.assists, 3)
        self.assertEqual(deko.flash_assists, 2)
        self.assertEqual(deko.trade_deaths, 1)

    def test_parse_handles_missing_player_stats(self) -> None:
        fixture = {**RICH_FIXTURE, "maps": [{
            "map_index": 1, "map_name": "Dust2", "team_a_score": 13,
            "team_b_score": 6, "winner_hltv_id": "13644",
        }]}
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(parsed.maps[0].player_stats, ())
        self.assertIsNone(parsed.maps[0].map_stats_id)

    def test_parse_skips_unresolvable_player_stats(self) -> None:
        fixture_with_unknown = {**RICH_FIXTURE, "maps": [{
            **RICH_FIXTURE["maps"][0],
            "player_stats": {"unknown_player": {"kills": 5, "deaths": 3}},
        }]}
        parsed = parse_hltv_payload(fixture_with_unknown)
        self.assertEqual(len(parsed.maps[0].player_stats), 0)

    def test_null_veto_team_hltv_id_for_decider(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        decider = parsed.vetoes[2]
        self.assertIsNone(decider.team_hltv_id)
        self.assertEqual(decider.action, "decider")

    def test_plain_fixture_still_works(self) -> None:
        parsed = parse_hltv_payload(FIXTURE)
        self.assertIsNone(parsed.match_stage)
        self.assertIsNone(parsed.head_to_head)
        self.assertEqual(parsed.maps[0].player_stats, ())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_hltv_fixture_normalization.RichParserTests -v`
Expected: FAIL — parser doesn't extract match_stage, player_stats, etc.

- [ ] **Step 3: Implement parser extensions**

In `sports/cs/normalization/hltv_fixture.py`:

Add import at top:

```python
from sports.cs.normalization.records import (
    CsParsedEvent,
    CsParsedMap,
    CsParsedMatch,
    CsParsedPlayer,
    CsParsedPlayerMapStats,
    CsParsedTeam,
    CsParsedVeto,
)
```

Replace the `_parse_map` function:

```python
def _parse_map(payload: dict[str, Any], players: tuple[CsParsedPlayer, ...]) -> CsParsedMap:
    raw_stats = payload.get("player_stats") or {}
    player_stats = _parse_player_map_stats(raw_stats, players)
    return CsParsedMap(
        map_index=int(payload["map_index"]),
        map_name=normalize_map_name(str(payload["map_name"])),
        team_a_score=int(payload["team_a_score"]),
        team_b_score=int(payload["team_b_score"]),
        winner_hltv_id=str(payload["winner_hltv_id"]),
        map_stats_id=_optional_str(payload.get("map_stats_id")),
        overtime=payload.get("overtime"),
        team_a_first_half=_optional_int(payload.get("team_a_first_half")),
        team_a_second_half=_optional_int(payload.get("team_a_second_half")),
        team_b_first_half=_optional_int(payload.get("team_b_first_half")),
        team_b_second_half=_optional_int(payload.get("team_b_second_half")),
        player_stats=player_stats,
    )
```

Add new helper functions:

```python
def _parse_player_map_stats(
    raw_stats: dict[str, Any],
    players: tuple[CsParsedPlayer, ...],
) -> tuple[CsParsedPlayerMapStats, ...]:
    if not raw_stats:
        return ()
    lookup: dict[str, CsParsedPlayer] = {p.nickname.lower(): p for p in players}
    result: list[CsParsedPlayerMapStats] = []
    for nickname_key, stats in raw_stats.items():
        player = lookup.get(nickname_key.lower())
        if player is None:
            continue
        result.append(CsParsedPlayerMapStats(
            player_hltv_id=player.hltv_id,
            team_hltv_id=player.team_hltv_id,
            kills=_optional_int(stats.get("kills")),
            deaths=_optional_int(stats.get("deaths")),
            assists=_optional_int(stats.get("assists")),
            adr=_optional_float(stats.get("adr")),
            rating=_optional_float(stats.get("rating")),
            kast_pct=_optional_float(stats.get("kast_pct")),
            headshot_pct=_optional_float(stats.get("headshot_pct")),
            first_kills=_optional_int(stats.get("first_kills")),
            clutches_won=_optional_int(stats.get("clutches_won")),
            ct_kills=_optional_int(stats.get("ct_kills")),
            ct_deaths=_optional_int(stats.get("ct_deaths")),
            t_kills=_optional_int(stats.get("t_kills")),
            t_deaths=_optional_int(stats.get("t_deaths")),
            flash_assists=_optional_int(stats.get("flash_assists")),
            trade_deaths=_optional_int(stats.get("trade_deaths")),
        ))
    return tuple(result)


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None
```

Update `parse_hltv_payload` to pass `players` to `_parse_map` and extract new match-level fields:

```python
def parse_hltv_payload(payload: dict[str, Any]) -> CsParsedMatch:
    team_a = _parse_team(payload["team_a"])
    team_b = _parse_team(payload["team_b"])
    event = payload["event"]
    scheduled_at = _parse_datetime(payload["scheduled_at"])
    players = tuple(_parse_player(row) for row in payload.get("players", []))
    maps = tuple(_parse_map(row, players) for row in payload.get("maps", []))
    vetoes = tuple(_parse_veto(row) for row in payload.get("vetoes", []))
    head_to_head_raw = payload.get("head_to_head")
    return CsParsedMatch(
        hltv_id=str(payload["hltv_id"]),
        scheduled_at=scheduled_at,
        best_of=int(payload["best_of"]),
        status=str(payload.get("status", "scheduled")),
        team_a=team_a,
        team_b=team_b,
        event=CsParsedEvent(
            hltv_id=str(event["hltv_id"]),
            name=str(event["name"]),
            tier=event.get("tier"),
        ),
        players=players,
        maps=maps,
        vetoes=vetoes,
        match_stage=_optional_str(payload.get("match_stage")),
        head_to_head=dict(head_to_head_raw) if head_to_head_raw else None,
    )
```

Note: `_parse_map` signature changed from `(payload)` to `(payload, players)`. This is safe because it's a private function only called from `parse_hltv_payload`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_hltv_fixture_normalization -v`
Expected: all tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add sports/cs/normalization/hltv_fixture.py tests/test_hltv_fixture_normalization.py
git commit -m "feat: extend HLTV parser for player stats, half scores, head-to-head"
```

---

### Task 4: Extend Contest Entity and Core Repository

**Files:**
- Modify: `core/entities/models.py`
- Modify: `core/db/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write failing test for contest with match_stage and head_to_head**

Check the existing test structure first. In `tests/test_repository.py`, find the `FakeDb` and add a test. If `FakeDb` is already defined there, use it. Otherwise add one similar to `tests/test_cs_repository.py`.

Add this test:

```python
class ContestUpsertTests(unittest.TestCase):
    def test_upsert_contest_includes_match_stage_and_head_to_head(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        contest = Contest(
            contest_id="cs:contest:hltv:2394722",
            game_id="counter_strike",
            competition_id="cs:competition:hltv:9171",
            starts_at=datetime(2026, 5, 29, 17, 0, tzinfo=timezone.utc),
            participant_a_id="cs:participant:hltv:13644",
            participant_b_id="cs:participant:hltv:13403",
            format="bo3",
            status="finished",
            match_stage="Round of 16",
            head_to_head={"team_a_wins": 3, "team_b_wins": 2},
        )
        repo.upsert_contest(contest)
        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("match_stage", sql)
        self.assertIn("head_to_head", sql)
        self.assertIn("Round of 16", params)

    def test_upsert_contest_defaults_to_none(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        contest = Contest(
            contest_id="c1", game_id="cs", competition_id=None,
            starts_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            participant_a_id="a", participant_b_id="b",
            format="bo1", status="finished",
        )
        repo.upsert_contest(contest)
        sql, params = db.calls[0]
        self.assertIn("match_stage", sql)
```

Import `Contest` from `core.entities` and `datetime`/`timezone` if not already imported.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_repository.ContestUpsertTests -v`
Expected: FAIL — Contest doesn't accept `match_stage` / `head_to_head`

- [ ] **Step 3: Add fields to Contest dataclass**

In `core/entities/models.py`, update the `Contest` class:

```python
@dataclass(frozen=True)
class Contest:
    contest_id: str
    game_id: str
    competition_id: str | None
    starts_at: datetime
    participant_a_id: str
    participant_b_id: str
    format: str
    status: str
    match_stage: str | None = None
    head_to_head: dict[str, int] | None = None
```

- [ ] **Step 4: Update upsert_contest in PostgresRepository**

In `core/db/repository.py`, replace the `upsert_contest` method:

```python
def upsert_contest(self, contest: Contest) -> None:
    self.db.execute(
        """
        INSERT INTO contests (contest_id, game_id, competition_id, starts_at, participant_a_id, participant_b_id, format, status, match_stage, head_to_head)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
        ON CONFLICT (contest_id) DO UPDATE SET
          starts_at = EXCLUDED.starts_at,
          format = EXCLUDED.format,
          status = EXCLUDED.status,
          match_stage = EXCLUDED.match_stage,
          head_to_head = EXCLUDED.head_to_head
        """,
        (
            contest.contest_id,
            contest.game_id,
            contest.competition_id,
            contest.starts_at,
            contest.participant_a_id,
            contest.participant_b_id,
            contest.format,
            contest.status,
            contest.match_stage,
            json.dumps(contest.head_to_head) if contest.head_to_head is not None else None,
        ),
    )
```

Note: `json` is already imported at the top of `repository.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_repository.ContestUpsertTests -v`
Expected: PASS

Also run existing repo tests:
Run: `python -m unittest tests.test_repository -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add core/entities/models.py core/db/repository.py tests/test_repository.py
git commit -m "feat: add match_stage and head_to_head to Contest entity and upsert"
```

---

### Task 5: Extend CS Repository

**Files:**
- Modify: `sports/cs/repository.py`
- Test: `tests/test_cs_repository.py`

- [ ] **Step 1: Write failing tests for updated upsert_map_result and new methods**

Replace the contents of `tests/test_cs_repository.py`:

```python
from __future__ import annotations

import unittest

from sports.cs.normalization.records import CsParsedMap, CsParsedPlayerMapStats, CsParsedVeto
from sports.cs.repository import CsRepository


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))


class CsRepositoryTests(unittest.TestCase):
    def test_upsert_map_result_includes_rich_fields(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        parsed_map = CsParsedMap(
            map_index=1, map_name="Dust2", team_a_score=13, team_b_score=6,
            winner_hltv_id="13644", map_stats_id="230451", overtime=False,
            team_a_first_half=7, team_a_second_half=6,
            team_b_first_half=5, team_b_second_half=1,
        )
        repo.upsert_map_result("unit-1", parsed_map)
        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("map_stats_id", sql)
        self.assertIn("overtime", sql)
        self.assertIn("team_a_first_half", sql)
        self.assertEqual(params, (
            "unit-1", "Dust2", 13, 6, "230451", False, 7, 6, 5, 1,
        ))

    def test_upsert_map_result_basic_still_works(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        parsed_map = CsParsedMap(1, "Mirage", 13, 9, "4608")
        repo.upsert_map_result("unit-1", parsed_map)
        sql, params = db.calls[0]
        self.assertEqual(params, ("unit-1", "Mirage", 13, 9, None, None, None, None, None, None))

    def test_upsert_veto_action(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        repo.upsert_veto_action("contest-1", CsParsedVeto(1, "4608", "ban", "Nuke"))
        self.assertEqual(len(db.calls), 1)
        self.assertIn("INSERT INTO cs_veto_actions", db.calls[0][0])
        self.assertEqual(db.calls[0][1], ("contest-1", 1, "cs:participant:hltv:4608", "ban", "Nuke"))

    def test_upsert_map_lineup(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        repo.upsert_map_lineup("unit-1", "cs:participant:hltv:13644", "cs:participant:hltv:16555")
        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("INSERT INTO cs_map_lineups", sql)
        self.assertEqual(params, ("unit-1", "cs:participant:hltv:13644", "cs:participant:hltv:16555"))

    def test_upsert_player_map_stats(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        stats = CsParsedPlayerMapStats(
            player_hltv_id="16555", team_hltv_id="13644",
            kills=19, deaths=10, assists=None, adr=94.6, rating=1.77,
            kast_pct=84.2, headshot_pct=None, first_kills=None, clutches_won=None,
            ct_kills=9, ct_deaths=3, t_kills=10, t_deaths=7,
            flash_assists=None, trade_deaths=None,
        )
        repo.upsert_player_map_stats("unit-1", stats)
        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("INSERT INTO cs_player_map_stats", sql)
        self.assertEqual(params[0], "unit-1")
        self.assertEqual(params[1], "cs:participant:hltv:16555")
        self.assertEqual(params[2], "cs:participant:hltv:13644")
        self.assertEqual(params[3], 19)   # kills
        self.assertEqual(params[4], 10)   # deaths
        self.assertIsNone(params[5])      # assists
        self.assertAlmostEqual(params[6], 94.6)  # adr
        self.assertEqual(params[13], 9)   # ct_kills
        self.assertEqual(params[16], 7)   # t_deaths
        self.assertIsNone(params[17])     # flash_assists
        self.assertIsNone(params[18])     # trade_deaths

    def test_upsert_player_map_stats_all_nulls(self) -> None:
        db = FakeDb()
        repo = CsRepository(db)
        stats = CsParsedPlayerMapStats(player_hltv_id="1", team_hltv_id="2")
        repo.upsert_player_map_stats("unit-1", stats)
        sql, params = db.calls[0]
        self.assertEqual(params[0], "unit-1")
        self.assertEqual(params[3], None)  # kills


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_cs_repository -v`
Expected: FAIL — params mismatch for upsert_map_result, missing upsert_map_lineup and upsert_player_map_stats

- [ ] **Step 3: Implement repository changes**

Replace the contents of `sports/cs/repository.py`:

```python
from __future__ import annotations

from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMap, CsParsedPlayerMapStats, CsParsedVeto


class CsRepository:
    """Counter-Strike table persistence."""

    def __init__(self, db) -> None:
        self.db = db

    def upsert_map_result(self, unit_id: str, parsed_map: CsParsedMap) -> None:
        self.db.execute(
            """
            INSERT INTO cs_map_results
              (unit_id, map_name, team_a_score, team_b_score,
               map_stats_id, overtime, team_a_first_half, team_a_second_half,
               team_b_first_half, team_b_second_half)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id) DO UPDATE SET
              map_name = EXCLUDED.map_name,
              team_a_score = EXCLUDED.team_a_score,
              team_b_score = EXCLUDED.team_b_score,
              map_stats_id = EXCLUDED.map_stats_id,
              overtime = EXCLUDED.overtime,
              team_a_first_half = EXCLUDED.team_a_first_half,
              team_a_second_half = EXCLUDED.team_a_second_half,
              team_b_first_half = EXCLUDED.team_b_first_half,
              team_b_second_half = EXCLUDED.team_b_second_half
            """,
            (
                unit_id,
                parsed_map.map_name,
                parsed_map.team_a_score,
                parsed_map.team_b_score,
                parsed_map.map_stats_id,
                parsed_map.overtime,
                parsed_map.team_a_first_half,
                parsed_map.team_a_second_half,
                parsed_map.team_b_first_half,
                parsed_map.team_b_second_half,
            ),
        )

    def upsert_veto_action(self, contest_id: str, veto: CsParsedVeto) -> None:
        team_id = cs_participant_id("hltv", veto.team_hltv_id) if veto.team_hltv_id is not None else None
        self.db.execute(
            """
            INSERT INTO cs_veto_actions (contest_id, order_idx, team_id, action, map_name)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (contest_id, order_idx) DO UPDATE SET
              team_id = EXCLUDED.team_id,
              action = EXCLUDED.action,
              map_name = EXCLUDED.map_name
            """,
            (
                contest_id,
                veto.order_idx,
                team_id,
                veto.action,
                veto.map_name,
            ),
        )

    def upsert_map_lineup(self, unit_id: str, team_id: str, player_id: str) -> None:
        self.db.execute(
            """
            INSERT INTO cs_map_lineups (unit_id, team_id, player_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (unit_id, player_id) DO UPDATE SET
              team_id = EXCLUDED.team_id
            """,
            (unit_id, team_id, player_id),
        )

    def upsert_player_map_stats(self, unit_id: str, stats: CsParsedPlayerMapStats) -> None:
        player_id = cs_participant_id("hltv", stats.player_hltv_id)
        team_id = cs_participant_id("hltv", stats.team_hltv_id)
        self.db.execute(
            """
            INSERT INTO cs_player_map_stats
              (unit_id, player_id, team_id,
               kills, deaths, assists, adr, kast, rating_2_0, hs_pct,
               first_kills, first_deaths, clutches_won,
               ct_kills, ct_deaths, t_kills, t_deaths,
               flash_assists, trade_deaths)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id, player_id) DO UPDATE SET
              team_id = EXCLUDED.team_id,
              kills = EXCLUDED.kills,
              deaths = EXCLUDED.deaths,
              assists = EXCLUDED.assists,
              adr = EXCLUDED.adr,
              kast = EXCLUDED.kast,
              rating_2_0 = EXCLUDED.rating_2_0,
              hs_pct = EXCLUDED.hs_pct,
              first_kills = EXCLUDED.first_kills,
              first_deaths = EXCLUDED.first_deaths,
              clutches_won = EXCLUDED.clutches_won,
              ct_kills = EXCLUDED.ct_kills,
              ct_deaths = EXCLUDED.ct_deaths,
              t_kills = EXCLUDED.t_kills,
              t_deaths = EXCLUDED.t_deaths,
              flash_assists = EXCLUDED.flash_assists,
              trade_deaths = EXCLUDED.trade_deaths
            """,
            (
                unit_id,
                player_id,
                team_id,
                stats.kills,
                stats.deaths,
                stats.assists,
                stats.adr,
                stats.kast_pct,
                stats.rating,
                stats.headshot_pct,
                stats.first_kills,
                None,  # first_deaths — not in scraper data
                stats.clutches_won,
                stats.ct_kills,
                stats.ct_deaths,
                stats.t_kills,
                stats.t_deaths,
                stats.flash_assists,
                stats.trade_deaths,
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_cs_repository -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add sports/cs/repository.py tests/test_cs_repository.py
git commit -m "feat: extend CsRepository with lineup, player stats, and rich map result upserts"
```

---

### Task 6: Extend normalize_match for match_stage and head_to_head

**Files:**
- Modify: `sports/cs/normalization/hltv_fixture.py`
- Test: `tests/test_hltv_fixture_normalization.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_hltv_fixture_normalization.py`:

```python
class NormalizeRichMatchTests(unittest.TestCase):
    def test_normalize_passes_match_stage_and_head_to_head(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        normalized = normalize_match(parsed)
        contest = normalized["contest"]
        self.assertEqual(contest.match_stage, "Round of 16")
        self.assertEqual(contest.head_to_head, {"team_a_wins": 3, "team_b_wins": 2})

    def test_normalize_plain_fixture_has_none_for_rich_fields(self) -> None:
        parsed = parse_hltv_payload(FIXTURE)
        normalized = normalize_match(parsed)
        contest = normalized["contest"]
        self.assertIsNone(contest.match_stage)
        self.assertIsNone(contest.head_to_head)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_hltv_fixture_normalization.NormalizeRichMatchTests -v`
Expected: FAIL — Contest constructor doesn't receive match_stage/head_to_head

- [ ] **Step 3: Update normalize_match**

In `sports/cs/normalization/hltv_fixture.py`, update the `Contest(...)` construction inside `normalize_match`:

```python
"contest": Contest(
    contest_id=contest_id,
    game_id=GAME_ID,
    competition_id=competition_id,
    starts_at=parsed.scheduled_at,
    participant_a_id=team_a_id,
    participant_b_id=team_b_id,
    format=f"bo{parsed.best_of}",
    status=parsed.status,
    match_stage=parsed.match_stage,
    head_to_head=parsed.head_to_head,
),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_hltv_fixture_normalization -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add sports/cs/normalization/hltv_fixture.py tests/test_hltv_fixture_normalization.py
git commit -m "feat: pass match_stage and head_to_head through normalize_match to Contest"
```

---

### Task 7: Update backfill_hltv.py and db_ingest_cs_fixture

**Files:**
- Modify: `scripts/backfill_hltv.py`
- Modify: `core/cli/main.py`

These are CLI integration commands, not unit-testable in isolation. The changes are mechanical: after upserting map results, also upsert lineups and player stats.

- [ ] **Step 1: Update backfill_hltv.py**

In `scripts/backfill_hltv.py`, add counters to the `results` dict:

```python
results = {
    ...
    "lineups_upserted": 0,
    "player_stats_upserted": 0,
}
```

In the inner loop, after the map results loop, add lineup and player stats upserts:

```python
for unit, parsed_map in zip(contest_units, normalized["cs_maps"], strict=True):
    cs_repo.upsert_map_result(unit.unit_id, parsed_map)
    results["map_results_upserted"] += 1
    for player_stat in parsed_map.player_stats:
        player_id = cs_participant_id("hltv", player_stat.player_hltv_id)
        team_id = cs_participant_id("hltv", player_stat.team_hltv_id)
        cs_repo.upsert_map_lineup(unit.unit_id, team_id, player_id)
        results["lineups_upserted"] += 1
        cs_repo.upsert_player_map_stats(unit.unit_id, player_stat)
        results["player_stats_upserted"] += 1
```

Add the import at the top:

```python
from sports.cs.normalization.ids import cs_participant_id
```

Note: `cs_participant_id` is already imported via `from sports.cs.normalization import normalize_match, parse_hltv_fixture` — but it's not directly imported. Add it explicitly.

Wait — check the existing imports in backfill_hltv.py. It imports `from sports.cs.normalization import normalize_match, parse_hltv_fixture` but not `cs_participant_id`. Add to imports:

```python
from sports.cs.normalization import normalize_match, parse_hltv_fixture
from sports.cs.normalization.ids import cs_participant_id
```

- [ ] **Step 2: Update db_ingest_cs_fixture in core/cli/main.py**

In `core/cli/main.py`, find the `db_ingest_cs_fixture` function (around line 273). After the existing map results and vetoes loop, add lineup and player stats:

```python
for unit, parsed_map in zip(contest_units, normalized["cs_maps"], strict=True):
    cs_repo.upsert_map_result(unit.unit_id, parsed_map)
    for player_stat in parsed_map.player_stats:
        player_id = cs_participant_id("hltv", player_stat.player_hltv_id)
        team_id = cs_participant_id("hltv", player_stat.team_hltv_id)
        cs_repo.upsert_map_lineup(unit.unit_id, team_id, player_id)
        cs_repo.upsert_player_map_stats(unit.unit_id, player_stat)
```

Add `cs_participant_id` to the imports inside the function (it already uses a local import pattern):

```python
from sports.cs.normalization import normalize_match, parse_hltv_fixture
from sports.cs.normalization.ids import cs_participant_id
```

Update the output JSON to include new counts:

```python
"lineups_upserted": sum(len(pm.player_stats) for pm in normalized["cs_maps"]),
"player_stats_upserted": sum(len(pm.player_stats) for pm in normalized["cs_maps"]),
```

- [ ] **Step 3: Run full test suite**

Run: `python -m unittest discover tests -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_hltv.py core/cli/main.py
git commit -m "feat: write lineups and player stats in backfill and single-fixture ingestion"
```

---

### Task 8: New db-ingest-hltv-scraped CLI Command

**Files:**
- Modify: `core/cli/main.py`

- [ ] **Step 1: Add the ingest function**

In `core/cli/main.py`, add a new function `db_ingest_hltv_scraped`:

```python
def db_ingest_hltv_scraped(args: argparse.Namespace) -> int:
    from core.ingestion import FetchResult
    from sports.cs.normalization import normalize_match, parse_hltv_payload
    from sports.cs.normalization.ids import cs_participant_id
    from sports.cs.repository import CsRepository

    settings = load_settings()
    store = LocalRawStore(settings.raw_store_dir)

    scraped_dir = Path(args.scraped_dir)
    if not scraped_dir.is_absolute():
        scraped_dir = settings.project_root / scraped_dir
    scraped_dir = scraped_dir.resolve()

    fixture_paths = sorted(scraped_dir.glob("*.json"))
    if not fixture_paths:
        return print_error("no_fixtures", f"No JSON files found in {scraped_dir}")

    results: dict[str, object] = {
        "fixtures_found": len(fixture_paths),
        "ingested": 0,
        "skipped": 0,
        "failed": 0,
        "participants_upserted": 0,
        "contest_units_upserted": 0,
        "map_results_upserted": 0,
        "vetoes_upserted": 0,
        "lineups_upserted": 0,
        "player_stats_upserted": 0,
        "errors": [],
    }

    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            cs_repo = CsRepository(db)

            existing: set[str] = set()
            if not args.force:
                rows = db.execute(
                    "SELECT source_id FROM raw_objects WHERE source = %s",
                    ("hltv-scraper",),
                )
                existing = {str(row[0]).removeprefix("scraper-") for row in (rows or [])}

            for path in fixture_paths:
                hltv_id = path.stem
                if hltv_id in existing:
                    results["skipped"] += 1  # type: ignore[operator]
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    parsed = parse_hltv_payload(payload)
                    normalized = normalize_match(parsed)

                    raw_obj = store.put(
                        FetchResult(
                            source="hltv-scraper",
                            source_id=f"scraper-{hltv_id}",
                            url=str(path),
                            content=path.read_bytes(),
                            content_type="application/json",
                            fetched_at=datetime.now(timezone.utc),
                        )
                    )
                    repo.upsert_raw_object(raw_obj)

                    for participant in normalized["participants"]:
                        repo.upsert_participant(participant)
                        results["participants_upserted"] += 1  # type: ignore[operator]

                    repo.upsert_competition(normalized["competition"])
                    repo.upsert_contest(normalized["contest"])

                    contest_units = normalized["contest_units"]
                    for unit in contest_units:
                        repo.upsert_contest_unit(unit)
                        results["contest_units_upserted"] += 1  # type: ignore[operator]

                    contest_id = normalized["contest"].contest_id
                    for veto in normalized["cs_vetoes"]:
                        cs_repo.upsert_veto_action(contest_id, veto)
                        results["vetoes_upserted"] += 1  # type: ignore[operator]

                    for unit, parsed_map in zip(contest_units, normalized["cs_maps"], strict=True):
                        cs_repo.upsert_map_result(unit.unit_id, parsed_map)
                        results["map_results_upserted"] += 1  # type: ignore[operator]
                        for player_stat in parsed_map.player_stats:
                            player_id = cs_participant_id("hltv", player_stat.player_hltv_id)
                            team_id = cs_participant_id("hltv", player_stat.team_hltv_id)
                            cs_repo.upsert_map_lineup(unit.unit_id, team_id, player_id)
                            results["lineups_upserted"] += 1  # type: ignore[operator]
                            cs_repo.upsert_player_map_stats(unit.unit_id, player_stat)
                            results["player_stats_upserted"] += 1  # type: ignore[operator]

                    existing.add(hltv_id)
                    results["ingested"] += 1  # type: ignore[operator]
                except Exception as exc:
                    results["failed"] += 1  # type: ignore[operator]
                    results["errors"].append({"file": path.name, "error": str(exc)})  # type: ignore[union-attr]

    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_ingest_hltv_scraped_failed", str(exc))

    print(json.dumps(results, indent=2, sort_keys=True, default=str))
    return 0
```

- [ ] **Step 2: Register the CLI subcommand**

In the `main()` function of `core/cli/main.py`, add the subparser after the `hltv_scraped_parser` block (around line 1766):

```python
db_ingest_scraped_parser = subparsers.add_parser("db-ingest-hltv-scraped")
db_ingest_scraped_parser.add_argument("--scraped-dir", default="data/hltv_scraped")
db_ingest_scraped_parser.add_argument("--force", action="store_true", help="Re-ingest already imported matches")
db_ingest_scraped_parser.set_defaults(func=db_ingest_hltv_scraped)
```

- [ ] **Step 3: Test CLI registration**

Run: `python -m core.cli --help`
Expected: `db-ingest-hltv-scraped` appears in the list of commands

Run: `python -m core.cli db-ingest-hltv-scraped --help`
Expected: shows `--scraped-dir` and `--force` flags

- [ ] **Step 4: Run full test suite**

Run: `python -m unittest discover tests -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/cli/main.py
git commit -m "feat: add db-ingest-hltv-scraped CLI command with incremental skip"
```

---

### Task 9: Test Fixture for CLI Integration

**Files:**
- Create: `tests/fixtures/hltv_scraped_sample.json`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Create a sample scraper fixture**

Write `tests/fixtures/hltv_scraped_sample.json` using the `RICH_FIXTURE` dict from the parser tests. This is a realistic scraper output file:

```json
{
    "hltv_id": "2394722",
    "schema_version": "hltv-fixture-v1",
    "source": {"name": "hltv-scraper", "url": "https://example.com", "stats_url": "https://example.com/stats"},
    "status": "finished",
    "best_of": 3,
    "match_stage": "Round of 16",
    "scheduled_at": "2026-05-29T17:00:00+00:00",
    "event": {"hltv_id": "9171", "name": "Thunderpick World Championship", "tier": 2, "hltv_stars": 0},
    "team_a": {"hltv_id": "13644", "name": "TDK"},
    "team_b": {"hltv_id": "13403", "name": "TNC"},
    "head_to_head": {"team_a_wins": 3, "team_b_wins": 2},
    "players": [
        {"hltv_id": "16555", "nickname": "Ax1Le", "team_hltv_id": "13644"},
        {"hltv_id": "20312", "nickname": "deko", "team_hltv_id": "13403"}
    ],
    "vetoes": [
        {"order_idx": 1, "action": "ban", "map_name": "Nuke", "team_hltv_id": "13644"},
        {"order_idx": 2, "action": "pick", "map_name": "Dust2", "team_hltv_id": "13403"},
        {"order_idx": 3, "action": "decider", "map_name": "Mirage", "team_hltv_id": null}
    ],
    "maps": [{
        "map_index": 1, "map_name": "Dust2", "map_stats_id": "230451",
        "overtime": false, "winner_hltv_id": "13644",
        "team_a_score": 13, "team_a_first_half": 7, "team_a_second_half": 6,
        "team_b_score": 6, "team_b_first_half": 5, "team_b_second_half": 1,
        "player_stats": {
            "ax1le": {
                "kills": 19, "deaths": 10, "adr": 94.6, "rating": 1.77, "kast_pct": 84.2,
                "ct_kills": 9, "ct_deaths": 3, "t_kills": 10, "t_deaths": 7,
                "assists": null, "headshot_pct": null, "first_kills": null, "clutches_won": null,
                "flash_assists": null, "trade_deaths": null
            },
            "deko": {
                "kills": 8, "deaths": 15, "adr": 55.3, "rating": 0.72, "kast_pct": 63.2,
                "ct_kills": 4, "ct_deaths": 8, "t_kills": 4, "t_deaths": 7,
                "assists": 3, "headshot_pct": 50.0, "first_kills": 1, "clutches_won": 0,
                "flash_assists": 2, "trade_deaths": 1
            }
        }
    }]
}
```

- [ ] **Step 2: Write an integration test**

Add to `tests/test_hltv_fixture_normalization.py`:

```python
class FullPipelineIntegrationTests(unittest.TestCase):
    def test_rich_fixture_produces_all_record_types(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        normalized = normalize_match(parsed)

        self.assertEqual(len(normalized["participants"]), 4)
        self.assertIsNotNone(normalized["competition"])
        self.assertEqual(normalized["contest"].match_stage, "Round of 16")
        self.assertEqual(normalized["contest"].head_to_head, {"team_a_wins": 3, "team_b_wins": 2})
        self.assertEqual(len(normalized["contest_units"]), 1)
        self.assertEqual(len(normalized["cs_maps"]), 1)
        self.assertEqual(len(normalized["cs_vetoes"]), 3)

        parsed_map = normalized["cs_maps"][0]
        self.assertEqual(parsed_map.map_stats_id, "230451")
        self.assertEqual(len(parsed_map.player_stats), 2)

        ax1le = next(s for s in parsed_map.player_stats if s.player_hltv_id == "16555")
        self.assertEqual(ax1le.kills, 19)
        self.assertEqual(ax1le.ct_kills, 9)

    def test_fixture_without_stats_still_normalizes(self) -> None:
        no_stats = {**RICH_FIXTURE, "maps": [{
            "map_index": 1, "map_name": "Dust2", "team_a_score": 13,
            "team_b_score": 6, "winner_hltv_id": "13644",
        }]}
        no_stats_copy = {**no_stats}
        del no_stats_copy["match_stage"]
        del no_stats_copy["head_to_head"]
        parsed = parse_hltv_payload(no_stats_copy)
        normalized = normalize_match(parsed)
        self.assertEqual(len(normalized["cs_maps"]), 1)
        self.assertEqual(normalized["cs_maps"][0].player_stats, ())
        self.assertIsNone(normalized["contest"].match_stage)
```

- [ ] **Step 3: Run tests**

Run: `python -m unittest tests.test_hltv_fixture_normalization -v`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/hltv_scraped_sample.json tests/test_hltv_fixture_normalization.py
git commit -m "feat: add scraper sample fixture and full pipeline integration tests"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Schema migration for rich data columns | `infra/migrations/0006_hltv_scraper_rich_data.sql` |
| 2 | Extend parsed records with rich fields | `sports/cs/normalization/records.py`, tests |
| 3 | Extend HLTV parser for player stats, half scores | `sports/cs/normalization/hltv_fixture.py`, tests |
| 4 | Add match_stage/head_to_head to Contest + core repo | `core/entities/models.py`, `core/db/repository.py`, tests |
| 5 | Extend CsRepository with lineup + player stats | `sports/cs/repository.py`, tests |
| 6 | Pass rich fields through normalize_match | `sports/cs/normalization/hltv_fixture.py`, tests |
| 7 | Update backfill + single-fixture ingestion | `scripts/backfill_hltv.py`, `core/cli/main.py` |
| 8 | New `db-ingest-hltv-scraped` CLI command | `core/cli/main.py` |
| 9 | Sample fixture + integration tests | `tests/fixtures/`, tests |
