# HLTV Scraper Ingestion: Full-Fidelity Import Pipeline

**Date:** 2026-06-01
**Status:** Approved
**Goal:** Connect VPS HLTV scraper output to the Betto platform, replacing fixture-backed data with real scraped data. No data dropped — all rich fields (player stats, half scores, head-to-head, match stage, overtime, CT/T splits) are captured.

## Context

A scraper running on a VPS produces one JSON file per HLTV match (`hltv-fixture-v1` schema). ~1,917 files exist today, ~9,800 total queued. The platform already has:

- `parse_hltv_payload()` — parses HLTV fixture JSON into `CsParsedMatch`
- `normalize_match()` — converts parsed match into core entities
- `PostgresRepository` + `CsRepository` — upserts for core and CS tables
- `backfill_hltv.py` — batch ingest from a directory of fixture files
- `BETTO_API_DATA_SOURCE=postgres` toggle — flips the API from fixtures to DB

**Gaps:** The parsed records, repository, and schema drop rich data the scraper provides (player stats, half scores, head-to-head, overtime, map_stats_id, CT/T splits, match_stage). No incremental import support.

## Scraper Output Format

One JSON file per match, named `<hltv_id>.json`, flat in `data/hltv_scraped/`:

```json
{
  "hltv_id": "2394722",
  "schema_version": "hltv-fixture-v1",
  "source": { "name": "hltv-scraper", "url": "...", "stats_url": "..." },
  "status": "finished",
  "best_of": 3,
  "match_stage": "Round of 16",
  "scheduled_at": "2026-05-29T17:00:00+00:00",
  "event": { "hltv_id": "9171", "name": "...", "tier": 2, "hltv_stars": 0 },
  "team_a": { "hltv_id": "13644", "name": "TDK" },
  "team_b": { "hltv_id": "13403", "name": "TNC" },
  "head_to_head": { "team_a_wins": 3, "team_b_wins": 2 },
  "players": [{ "hltv_id": "16555", "nickname": "Ax1Le", "team_hltv_id": "13644" }],
  "vetoes": [{ "order_idx": 1, "action": "ban", "map_name": "Nuke", "team_hltv_id": "13644" }],
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
      }
    }
  }]
}
```

**Gotchas:**
1. All IDs are strings, not ints — matches existing convention
2. `player_stats` keys are lowercased nicknames; `players[].nickname` uses display casing — join case-insensitively
3. ~half the per-player stat fields are frequently null — treat as optional
4. Veto `team_hltv_id` is null for decider actions
5. 64 of 1,917 files lack player stats — map scores/vetoes still present
6. The SQLite DB is scraper orchestration only — read JSON files directly

## Changes

### 1. Schema Migration: `0002_hltv_scraper_rich_data.sql`

Add columns to existing tables:

**`cs_map_results`:**
- `map_stats_id TEXT` — HLTV stats page ID
- `overtime BOOLEAN` — whether map went to OT
- `team_a_first_half INT`, `team_a_second_half INT`
- `team_b_first_half INT`, `team_b_second_half INT`

**`cs_player_map_stats`:**
- `ct_kills INT`, `ct_deaths INT` — CT-side kills/deaths
- `t_kills INT`, `t_deaths INT` — T-side kills/deaths
- `flash_assists INT`
- `trade_deaths INT`

**`contests`:**
- `match_stage TEXT` — e.g. "Round of 16", "Grand Final"
- `head_to_head JSONB` — e.g. `{"team_a_wins": 3, "team_b_wins": 2}`

### 2. Extend Parsed Records: `sports/cs/normalization/records.py`

New dataclass for per-player per-map stats:

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

Extend `CsParsedMap` with:
- `map_stats_id: str | None = None`
- `overtime: bool | None = None`
- `team_a_first_half: int | None = None`
- `team_a_second_half: int | None = None`
- `team_b_first_half: int | None = None`
- `team_b_second_half: int | None = None`
- `player_stats: tuple[CsParsedPlayerMapStats, ...] = ()`

Extend `CsParsedMatch` with:
- `match_stage: str | None = None`
- `head_to_head: dict[str, int] | None = None`

All new fields have defaults — existing fixtures and Kaggle converters still parse without changes.

### 3. Extend Parser: `sports/cs/normalization/hltv_fixture.py`

**`parse_hltv_payload`:** Extract `match_stage` and `head_to_head` from payload.

**`_parse_map`:** Extract `map_stats_id`, `overtime`, half scores from map payload.

**New `_parse_player_map_stats`:** Takes the `player_stats` dict and the `players` list. Builds a case-insensitive nickname → `(hltv_id, team_hltv_id)` lookup from `players`. For each entry in `player_stats`, resolves the player's hltv_id via the lookup. Skips unresolvable entries (logs a warning). Returns a tuple of `CsParsedPlayerMapStats`.

### 4. Extend CS Repository: `sports/cs/repository.py`

**Update `upsert_map_result`:** Write all new columns (map_stats_id, overtime, half scores).

**New `upsert_map_lineup(unit_id, team_id, player_id)`:** Insert into `cs_map_lineups`.

**New `upsert_player_map_stats(unit_id, player_id, team_id, stats)`:** Insert into `cs_player_map_stats` with all columns including new CT/T splits.

### 5. Extend Core Repository: `core/db/repository.py`

**Update `upsert_contest`:** Include `match_stage` and `head_to_head` in the INSERT and ON CONFLICT UPDATE.

This requires adding `match_stage` and `head_to_head` to the `Contest` entity, or passing them separately. Since these are CS-specific metadata on a core table, pass them as optional parameters to `upsert_contest` to avoid changing the core `Contest` dataclass. Alternatively, add them to the `Contest` dataclass with `None` defaults.

**Decision:** Add `match_stage: str | None = None` and `head_to_head: dict[str, int] | None = None` to the `Contest` dataclass. They're nullable and don't break existing code.

### 6. Update Existing Ingestion Commands

**`db_ingest_cs_fixture` (single file):** Add map lineup and player stats upserts after the existing map result and veto upserts.

**`backfill_hltv.py` (batch):** Same — extend the inner loop to write lineups and player stats. Update counters.

### 7. New CLI Command: `db-ingest-hltv-scraped`

Batch ingestion for the VPS-scraped directory. Based on backfill but with:

**Incremental skip:** At batch start, query all existing HLTV source_ids from `raw_objects WHERE source = 'hltv-scraper'`, build a set. For each file, if `file.stem` is in the set, skip it. This makes re-running after rsync only process new files.

**Tolerant:** Wraps each file in try/except. Reports per-file failures but continues. At end, prints summary with counts of ingested, skipped, failed.

**Source tag:** `"hltv-scraper"` (distinct from `"hltv-backfill"` and `"hltv-fixture"`).

**Default dir:** `data/hltv_scraped/`.

**CLI interface:**
```
betto db-ingest-hltv-scraped [--scraped-dir data/hltv_scraped] [--force]
```

`--force` re-ingests already-imported matches (upserts are idempotent, just slower).

### 8. Files Modified

| File | Change |
|------|--------|
| `infra/migrations/0002_hltv_scraper_rich_data.sql` | New migration — ALTER TABLE adds |
| `sports/cs/normalization/records.py` | New `CsParsedPlayerMapStats`, extend `CsParsedMap`, `CsParsedMatch` |
| `sports/cs/normalization/hltv_fixture.py` | Extend parser for rich data |
| `sports/cs/repository.py` | Extend `upsert_map_result`, add lineup + player stats upserts |
| `core/entities/models.py` | Add `match_stage`, `head_to_head` to `Contest` |
| `core/db/repository.py` | Update `upsert_contest` for new fields |
| `core/cli/main.py` | Add `db-ingest-hltv-scraped` command, update `db-ingest-cs-fixture` |
| `scripts/backfill_hltv.py` | Extend to write lineups and player stats |
| `tests/test_cs_repository.py` | Update tests for new methods |

### 9. Data Flow

```
VPS: data/hltv_scraped/*.json
        | (rsync to local or mount)
        v
betto db-ingest-hltv-scraped --scraped-dir data/hltv_scraped
        |
        v
For each *.json not already in raw_objects:
  parse_hltv_payload() -> CsParsedMatch (all rich fields)
        |
  normalize_match() -> {
    participants (teams + players),
    competition,
    contest (with match_stage, head_to_head),
    contest_units (maps),
    cs_maps (with half scores, overtime, map_stats_id),
    cs_vetoes,
    cs_player_stats (per map, per player)
  }
        |
  PostgresRepository.upsert_*() -> core tables
  CsRepository.upsert_*() -> cs_map_results, cs_veto_actions,
                              cs_map_lineups, cs_player_map_stats
        |
        v
Set BETTO_API_DATA_SOURCE=postgres -> console shows real data
```

### 10. Incremental Import

The `db-ingest-hltv-scraped` command supports incremental imports:

1. On startup, queries `SELECT source_id FROM raw_objects WHERE source = 'hltv-scraper'`
2. Builds a set of already-imported HLTV IDs
3. For each `*.json` file in the scraped directory, checks if `file.stem` is in the set
4. If present: skip (increment skip counter)
5. If absent: parse, normalize, upsert, add to set
6. Summary output shows ingested/skipped/failed counts

This handles the scenario where the user imports 1,917 matches now, scrapes 7,900 more later, rsyncs again, and re-runs — only the new files are processed.

### 11. Testing

- Unit tests for the extended parser (with and without player_stats, with sparse fields)
- Unit tests for CsRepository new methods (map_lineup, player_map_stats)
- Integration test: parse a real scraper file → normalize → verify all records produced
- The existing test fixtures still parse without changes (new fields have defaults)
