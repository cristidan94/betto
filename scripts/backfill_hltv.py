"""Batch HLTV backfill: ingest all match payloads from data/hltv_backfill/ into the database.

Processes each match file through the existing normalization pipeline:
  1. Parse and normalize the HLTV fixture payload
  2. Upsert participants, competition, contest, contest_units, map results, vetoes
  3. Materialize point-in-time features for each match date
  4. Store raw object provenance

Usage (from WSL betto environment):
  python -m scripts.backfill_hltv [--corpus-dir data/hltv_backfill]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import load_settings
from core.db import PostgresExecutor, PostgresRepository
from core.ingestion import FetchResult
from core.raw_store import LocalRawStore
from sports.cs.features import materialize_map_win_rate_90d
from sports.cs.normalization import normalize_match, parse_hltv_fixture
from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMatch
from sports.cs.repository import CsRepository


def backfill(corpus_dir: Path, dry_run: bool = False) -> dict:
    settings = load_settings()
    store = LocalRawStore(settings.raw_store_dir)

    fixture_paths = sorted(corpus_dir.glob("*.json"))
    if not fixture_paths:
        print(f"No JSON fixtures found in {corpus_dir}", file=sys.stderr)
        return {"error": "no_fixtures"}

    parsed_matches: list[CsParsedMatch] = []
    results = {
        "fixtures_found": len(fixture_paths),
        "matches_ingested": 0,
        "participants_upserted": 0,
        "contest_units_upserted": 0,
        "map_results_upserted": 0,
        "vetoes_upserted": 0,
        "lineups_upserted": 0,
        "player_stats_upserted": 0,
        "features_materialized": 0,
    }

    if dry_run:
        for path in fixture_paths:
            parsed = parse_hltv_fixture(path)
            parsed_matches.append(parsed)
            normalized = normalize_match(parsed)
            results["matches_ingested"] += 1
            results["participants_upserted"] += len(normalized["participants"])
            results["contest_units_upserted"] += len(normalized["contest_units"])
            results["map_results_upserted"] += len(normalized["cs_maps"])
            results["vetoes_upserted"] += len(normalized["cs_vetoes"])
            player_stats_count = sum(len(parsed_map.player_stats) for parsed_map in normalized["cs_maps"])
            results["lineups_upserted"] += player_stats_count
            results["player_stats_upserted"] += player_stats_count
        features = materialize_map_win_rate_90d(
            parsed_matches,
            parsed_matches[-1].scheduled_at,
        )
        results["features_materialized"] = len(features)
        results["dry_run"] = True
        return results

    with PostgresExecutor(settings.database_url) as db:
        repo = PostgresRepository(db)
        cs_repo = CsRepository(db)

        for path in fixture_paths:
            parsed = parse_hltv_fixture(path)
            parsed_matches.append(parsed)
            normalized = normalize_match(parsed)

            raw_obj = store.put(
                FetchResult(
                    source="hltv-backfill",
                    source_id=f"backfill-{path.stem}",
                    url=str(path),
                    content=path.read_bytes(),
                    content_type="application/json",
                    fetched_at=datetime.now(timezone.utc),
                )
            )
            repo.upsert_raw_object(raw_obj)

            for participant in normalized["participants"]:
                repo.upsert_participant(participant)
                results["participants_upserted"] += 1

            repo.upsert_competition(normalized["competition"])
            repo.upsert_contest(normalized["contest"])

            contest_units = normalized["contest_units"]
            for unit in contest_units:
                repo.upsert_contest_unit(unit)
                results["contest_units_upserted"] += 1

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

            contest_id = normalized["contest"].contest_id
            for veto in normalized["cs_vetoes"]:
                cs_repo.upsert_veto_action(contest_id, veto)
                results["vetoes_upserted"] += 1

            results["matches_ingested"] += 1

        as_of = parsed_matches[-1].scheduled_at
        features = materialize_map_win_rate_90d(parsed_matches, as_of)

        digest = hashlib.sha256()
        digest.update(as_of.isoformat().encode("utf-8"))
        for path in fixture_paths:
            digest.update(path.read_bytes())
        data_snapshot_id = f"hltv-backfill-{digest.hexdigest()[:16]}"

        repo.upsert_data_snapshot(data_snapshot_id, f"HLTV backfill features as-of {as_of.date().isoformat()}")
        for feature in features:
            repo.insert_feature_value(feature, data_snapshot_id=data_snapshot_id)
        results["features_materialized"] = len(features)
        results["data_snapshot_id"] = data_snapshot_id
        results["features_as_of"] = as_of.isoformat()

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch HLTV backfill ingestion")
    parser.add_argument(
        "--corpus-dir",
        default=str(PROJECT_ROOT / "data" / "hltv_backfill"),
        help="Directory containing match JSON files",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir).resolve()
    results = backfill(corpus_dir, dry_run=args.dry_run)
    print(json.dumps(results, indent=2, sort_keys=True, default=str))
    return 0 if "error" not in results else 1


if __name__ == "__main__":
    sys.exit(main())
