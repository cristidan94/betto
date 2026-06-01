from __future__ import annotations

import argparse
import hashlib
import json
from urllib.error import URLError
from pathlib import Path
from datetime import datetime, timezone

from core import __version__
from core.config import load_settings
from core.db import MissingPostgresDriverError, PostgresExecutor, PostgresRepository, apply_migrations, list_migrations
from core.logging import configure_logging, get_logger
from core.raw_store import LocalRawStore
from sports.cs.plugin import build_plugin


def validate_config(args: argparse.Namespace) -> int:
    settings = load_settings()
    payload = {
        "env": settings.env,
        "project_root": str(settings.project_root),
        "data_dir": str(settings.data_dir),
        "raw_store_dir": str(settings.raw_store_dir),
        "database_url": settings.database_url,
        "redis_url": settings.redis_url,
        "polymarket_gamma_url": settings.polymarket_gamma_url,
        "polymarket_clob_url": settings.polymarket_clob_url,
        "polymarket_snapshot_interval_sec": settings.polymarket_snapshot_interval_sec,
        "default_timezone": settings.default_timezone,
        "oddspapi_api_key": "***" if settings.oddspapi_api_key else "",
        "oddspapi_base_url": settings.oddspapi_base_url,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def print_error(error: str, detail: str) -> int:
    print(json.dumps({"error": error, "detail": detail}, indent=2, sort_keys=True))
    return 1


def show_migrations(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    for migration in list_migrations(root):
        print(migration)
    return 0


def seed_cs_raw(args: argparse.Namespace) -> int:
    settings = load_settings()
    since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    store = LocalRawStore(settings.raw_store_dir)
    plugin = build_plugin()
    objects = [store.put(payload) for payload in plugin.fetch_seed_payloads(since)]
    print(
        json.dumps(
            [
                {
                    "source": obj.source,
                    "source_id": obj.source_id,
                    "content_hash": obj.content_hash,
                    "body_path": str(obj.body_path),
                    "metadata_path": str(obj.metadata_path),
                }
                for obj in objects
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def poll_polymarket_cs(args: argparse.Namespace) -> int:
    settings = load_settings()
    store = LocalRawStore(settings.raw_store_dir)
    from sports.cs.ingestion import PolymarketClient

    client = PolymarketClient(
        gamma_url=settings.polymarket_gamma_url,
        clob_url=settings.polymarket_clob_url,
    )
    try:
        discovery = client.discover_cs_markets(limit=args.limit, offset=args.offset, include_closed=args.include_closed)
    except URLError as exc:
        return print_error("network_unavailable", str(exc))
    raw_market_obj = store.put(discovery.raw_payload)
    raw_objects = [raw_market_obj]
    snapshots = []
    for market in discovery.markets:
        for token in market.tokens:
            try:
                book = client.get_order_book(market.market.market_id, token)
            except URLError as exc:
                return print_error("network_unavailable", str(exc))
            raw_objects.append(store.put(book.raw_payload))
            snapshots.append(book.snapshot)

    print(
        json.dumps(
            {
                "markets_found": len(discovery.markets),
                "snapshots_found": len(snapshots),
                "raw_objects": [
                    {
                        "source": obj.source,
                        "source_id": obj.source_id,
                        "content_hash": obj.content_hash,
                        "body_path": str(obj.body_path),
                    }
                    for obj in raw_objects
                ],
                "snapshots": [
                    {
                        "market_id": snapshot.market_id,
                        "outcome": snapshot.outcome,
                        "taken_at": snapshot.taken_at.isoformat(),
                        "best_bid": snapshot.best_bid,
                        "best_ask": snapshot.best_ask,
                        "last_trade_price": snapshot.last_trade_price,
                        "depth_bid_1pct": snapshot.depth_bid_1pct,
                        "depth_ask_1pct": snapshot.depth_ask_1pct,
                    }
                    for snapshot in snapshots
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def db_check(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            ready = db.ping()
    except MissingPostgresDriverError as exc:
        print(json.dumps({"ready": False, "error": "missing_postgres_driver", "detail": str(exc)}, indent=2, sort_keys=True))
        return 1
    except Exception as exc:
        print(json.dumps({"ready": False, "error": "postgres_unavailable", "detail": str(exc)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps({"ready": ready}, indent=2, sort_keys=True))
    return 0


def db_driver_info(args: argparse.Namespace) -> int:
    import importlib.util
    import sys

    from core.vendor import active_vendor_dir, add_vendor_path, load_vendor_package

    add_vendor_path()
    spec = importlib.util.find_spec("psycopg")
    payload = {
        "active_vendor_dir": str(active_vendor_dir()),
        "python": sys.executable,
        "version": sys.version,
        "spec_origin": spec.origin if spec else None,
        "spec_locations": list(spec.submodule_search_locations or []) if spec else [],
        "sys_path_head": sys.path[:8],
    }
    try:
        import psycopg

        payload["module_file"] = getattr(psycopg, "__file__", None)
        payload["has_connect"] = hasattr(psycopg, "connect")
        if not payload["has_connect"]:
            psycopg = load_vendor_package("psycopg")
            payload["module_file_after_direct_load"] = getattr(psycopg, "__file__", None)
            payload["has_connect_after_direct_load"] = hasattr(psycopg, "connect")
    except Exception as exc:
        payload["import_error"] = str(exc)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def db_apply_migrations(args: argparse.Namespace) -> int:
    settings = load_settings()
    root = Path(args.root).resolve()
    try:
        with PostgresExecutor(settings.database_url) as db:
            results = apply_migrations(db, root)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("migration_failed", str(exc))
    print(json.dumps([{"migration": item.migration_name, "applied": item.applied} for item in results], indent=2, sort_keys=True))
    return 0


def db_ingest_polymarket_cs(args: argparse.Namespace) -> int:
    settings = load_settings()
    store = LocalRawStore(settings.raw_store_dir)
    from sports.cs.ingestion import PolymarketClient

    client = PolymarketClient(
        gamma_url=settings.polymarket_gamma_url,
        clob_url=settings.polymarket_clob_url,
    )
    try:
        discovery = client.discover_cs_markets(limit=args.limit, offset=args.offset, include_closed=args.include_closed)
    except URLError as exc:
        return print_error("network_unavailable", str(exc))

    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            repo.upsert_raw_object(store.put(discovery.raw_payload))
            for market in discovery.markets:
                repo.upsert_market(market.market)
                for token in market.tokens:
                    try:
                        book = client.get_order_book(market.market.market_id, token)
                    except URLError as exc:
                        return print_error("network_unavailable", str(exc))
                    repo.upsert_raw_object(store.put(book.raw_payload))
                    repo.insert_market_snapshot(book.snapshot)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_ingest_failed", str(exc))

    snapshot_count = sum(len(market.tokens) for market in discovery.markets)
    print(json.dumps({"markets_upserted": len(discovery.markets), "snapshots_inserted": snapshot_count}, indent=2, sort_keys=True))
    return 0


def parse_cs_fixture(args: argparse.Namespace) -> int:
    from core.ingestion import FetchResult
    from sports.cs.normalization import normalize_match, parse_hltv_fixture

    settings = load_settings()
    fixture_path = Path(args.path).resolve()
    parsed = parse_hltv_fixture(fixture_path)
    normalized = normalize_match(parsed)
    store = LocalRawStore(settings.raw_store_dir)
    raw_obj = store.put(
        FetchResult(
            source="hltv-fixture",
            source_id=fixture_path.stem,
            url=str(fixture_path),
            content=fixture_path.read_bytes(),
            content_type="application/json",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    print(
        json.dumps(
            {
                "raw_object": {
                    "source": raw_obj.source,
                    "source_id": raw_obj.source_id,
                    "content_hash": raw_obj.content_hash,
                    "body_path": str(raw_obj.body_path),
                },
                "participants": len(normalized["participants"]),  # type: ignore[arg-type]
                "competition_id": normalized["competition"].competition_id,  # type: ignore[union-attr]
                "contest_id": normalized["contest"].contest_id,  # type: ignore[union-attr]
                "contest_units": len(normalized["contest_units"]),  # type: ignore[arg-type]
                "vetoes": len(normalized["cs_vetoes"]),  # type: ignore[arg-type]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def db_ingest_cs_fixture(args: argparse.Namespace) -> int:
    from core.ingestion import FetchResult
    from sports.cs.normalization import normalize_match, parse_hltv_fixture
    from sports.cs.normalization.ids import cs_participant_id
    from sports.cs.repository import CsRepository

    settings = load_settings()
    fixture_path = Path(args.path).resolve()
    parsed = parse_hltv_fixture(fixture_path)
    normalized = normalize_match(parsed)
    store = LocalRawStore(settings.raw_store_dir)
    raw_obj = store.put(
        FetchResult(
            source="hltv-fixture",
            source_id=fixture_path.stem,
            url=str(fixture_path),
            content=fixture_path.read_bytes(),
            content_type="application/json",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            cs_repo = CsRepository(db)
            repo.upsert_raw_object(raw_obj)
            for participant in normalized["participants"]:  # type: ignore[union-attr]
                repo.upsert_participant(participant)
            repo.upsert_competition(normalized["competition"])  # type: ignore[arg-type]
            repo.upsert_contest(normalized["contest"])  # type: ignore[arg-type]
            contest_units = normalized["contest_units"]  # type: ignore[assignment]
            for unit in contest_units:
                repo.upsert_contest_unit(unit)
            for unit, parsed_map in zip(contest_units, normalized["cs_maps"], strict=True):  # type: ignore[arg-type]
                cs_repo.upsert_map_result(unit.unit_id, parsed_map)
                for player_stat in parsed_map.player_stats:
                    player_id = cs_participant_id("hltv", player_stat.player_hltv_id)
                    team_id = cs_participant_id("hltv", player_stat.team_hltv_id)
                    cs_repo.upsert_map_lineup(unit.unit_id, team_id, player_id)
                    cs_repo.upsert_player_map_stats(unit.unit_id, player_stat)
            contest_id = normalized["contest"].contest_id  # type: ignore[union-attr]
            for veto in normalized["cs_vetoes"]:  # type: ignore[union-attr]
                cs_repo.upsert_veto_action(contest_id, veto)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_ingest_cs_fixture_failed", str(exc))

    print(
        json.dumps(
            {
                "raw_object": raw_obj.content_hash,
                "participants_upserted": len(normalized["participants"]),  # type: ignore[arg-type]
                "competition_id": normalized["competition"].competition_id,  # type: ignore[union-attr]
                "contest_id": normalized["contest"].contest_id,  # type: ignore[union-attr]
                "contest_units_upserted": len(normalized["contest_units"]),  # type: ignore[arg-type]
                "map_results_upserted": len(normalized["cs_maps"]),  # type: ignore[arg-type]
                "vetoes_upserted": len(normalized["cs_vetoes"]),  # type: ignore[arg-type]
                "lineups_upserted": sum(len(parsed_map.player_stats) for parsed_map in normalized["cs_maps"]),  # type: ignore[union-attr]
                "player_stats_upserted": sum(len(parsed_map.player_stats) for parsed_map in normalized["cs_maps"]),  # type: ignore[union-attr]
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


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

            for index, path in enumerate(fixture_paths):
                hltv_id = path.stem
                if hltv_id in existing:
                    results["skipped"] += 1  # type: ignore[operator]
                    continue

                savepoint = f"hltv_scraped_fixture_{index}"
                db.execute(f"SAVEPOINT {savepoint}", ())
                try:
                    file_bytes = path.read_bytes()
                    payload = json.loads(file_bytes.decode("utf-8"))
                    parsed = parse_hltv_payload(payload)
                    normalized = normalize_match(parsed)
                    fixture_counts = {
                        "participants_upserted": 0,
                        "contest_units_upserted": 0,
                        "map_results_upserted": 0,
                        "vetoes_upserted": 0,
                        "lineups_upserted": 0,
                        "player_stats_upserted": 0,
                    }

                    for participant in normalized["participants"]:  # type: ignore[union-attr]
                        repo.upsert_participant(participant)
                        fixture_counts["participants_upserted"] += 1

                    repo.upsert_competition(normalized["competition"])  # type: ignore[arg-type]
                    repo.upsert_contest(normalized["contest"])  # type: ignore[arg-type]

                    contest_units = normalized["contest_units"]  # type: ignore[assignment]
                    for unit in contest_units:
                        repo.upsert_contest_unit(unit)
                        fixture_counts["contest_units_upserted"] += 1

                    contest_id = normalized["contest"].contest_id  # type: ignore[union-attr]
                    for veto in normalized["cs_vetoes"]:  # type: ignore[union-attr]
                        cs_repo.upsert_veto_action(contest_id, veto)
                        fixture_counts["vetoes_upserted"] += 1

                    for unit, parsed_map in zip(contest_units, normalized["cs_maps"], strict=True):  # type: ignore[arg-type]
                        cs_repo.upsert_map_result(unit.unit_id, parsed_map)
                        fixture_counts["map_results_upserted"] += 1
                        for player_stat in parsed_map.player_stats:
                            player_id = cs_participant_id("hltv", player_stat.player_hltv_id)
                            team_id = cs_participant_id("hltv", player_stat.team_hltv_id)
                            cs_repo.upsert_map_lineup(unit.unit_id, team_id, player_id)
                            fixture_counts["lineups_upserted"] += 1
                            cs_repo.upsert_player_map_stats(unit.unit_id, player_stat)
                            fixture_counts["player_stats_upserted"] += 1

                    raw_obj = store.put(
                        FetchResult(
                            source="hltv-scraper",
                            source_id=f"scraper-{hltv_id}",
                            url=str(path),
                            content=file_bytes,
                            content_type="application/json",
                            fetched_at=datetime.now(timezone.utc),
                        )
                    )
                    repo.upsert_raw_object(raw_obj)

                    db.execute(f"RELEASE SAVEPOINT {savepoint}", ())
                    for key, value in fixture_counts.items():
                        results[key] += value  # type: ignore[operator]
                    existing.add(hltv_id)
                    results["ingested"] += 1  # type: ignore[operator]
                except Exception as exc:
                    db.execute(f"ROLLBACK TO SAVEPOINT {savepoint}", ())
                    db.execute(f"RELEASE SAVEPOINT {savepoint}", ())
                    results["failed"] += 1  # type: ignore[operator]
                    results["errors"].append({"file": path.name, "error": str(exc)})  # type: ignore[union-attr]

    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_ingest_hltv_scraped_failed", str(exc))

    print(json.dumps(results, indent=2, sort_keys=True, default=str))
    return 0


def convert_cs_kaggle_hltv_results(args: argparse.Namespace) -> int:
    from sports.cs.ingestion import (
        KAGGLE_HLTV_RESULTS_CS2_SOURCE,
        KAGGLE_HLTV_RESULTS_CS2_URL,
        parse_kaggle_hltv_results_csv,
        write_kaggle_hltv_fixture_payloads,
    )

    path = Path(args.path).resolve()
    out_dir = Path(args.out_dir).resolve()
    limit = args.limit if args.limit and args.limit > 0 else None
    try:
        matches = parse_kaggle_hltv_results_csv(path, limit=limit)
        written = write_kaggle_hltv_fixture_payloads(matches, out_dir)
    except Exception as exc:
        return print_error("cs_kaggle_hltv_results_failed", str(exc))

    print(
        json.dumps(
            {
                "source": KAGGLE_HLTV_RESULTS_CS2_SOURCE,
                "source_url": KAGGLE_HLTV_RESULTS_CS2_URL,
                "input": str(path),
                "out_dir": str(out_dir),
                "matches_converted": len(matches),
                "fixtures_written": len(written),
                "first_fixture": str(written[0]) if written else None,
                "note": "Converted rows use synthetic IDs because this Kaggle CSV has no HLTV numeric IDs or per-map facts.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def convert_cs_kaggle_competitive_results(args: argparse.Namespace) -> int:
    from sports.cs.ingestion import (
        KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_SOURCE,
        KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_URL,
        parse_kaggle_competitive_match_results_csv,
        write_kaggle_competitive_fixture_payloads,
    )

    path = Path(args.path).resolve()
    out_dir = Path(args.out_dir).resolve()
    players_path = Path(args.players_path).resolve() if args.players_path else None
    limit = args.limit if args.limit and args.limit > 0 else None
    try:
        matches = parse_kaggle_competitive_match_results_csv(path, players_path=players_path, limit=limit)
        written = write_kaggle_competitive_fixture_payloads(matches, out_dir)
    except Exception as exc:
        return print_error("cs_kaggle_competitive_results_failed", str(exc))

    print(
        json.dumps(
            {
                "source": KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_SOURCE,
                "source_url": KAGGLE_COUNTER_STRIKE_COMPETITIVE_DATA_URL,
                "input": str(path),
                "players_input": str(players_path) if players_path is not None else None,
                "out_dir": str(out_dir),
                "matches_converted": len(matches),
                "maps_converted": sum(len(match.maps) for match in matches),
                "players_converted": sum(len(match.players) for match in matches),
                "fixtures_written": len(written),
                "first_fixture": str(written[0]) if written else None,
                "note": "Converted rows preserve HLTV-derived match/team IDs when present and include map-level winners.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def convert_cs_kaggle_pro_matches(args: argparse.Namespace) -> int:
    from sports.cs.ingestion import (
        KAGGLE_CSGO_PRO_MATCHES_SOURCE,
        KAGGLE_CSGO_PRO_MATCHES_URL,
        parse_kaggle_csgo_pro_results_csv,
        write_kaggle_csgo_pro_fixture_payloads,
    )

    path = Path(args.path).resolve()
    out_dir = Path(args.out_dir).resolve()
    picks_path = Path(args.picks_path).resolve() if args.picks_path else None
    players_path = Path(args.players_path).resolve() if args.players_path else None
    limit = args.limit if args.limit and args.limit > 0 else None
    try:
        matches = parse_kaggle_csgo_pro_results_csv(path, picks_path=picks_path, players_path=players_path, limit=limit)
        written = write_kaggle_csgo_pro_fixture_payloads(matches, out_dir)
    except Exception as exc:
        return print_error("cs_kaggle_pro_matches_failed", str(exc))

    print(
        json.dumps(
            {
                "source": KAGGLE_CSGO_PRO_MATCHES_SOURCE,
                "source_url": KAGGLE_CSGO_PRO_MATCHES_URL,
                "input": str(path),
                "picks_input": str(picks_path) if picks_path is not None else None,
                "players_input": str(players_path) if players_path is not None else None,
                "out_dir": str(out_dir),
                "matches_converted": len(matches),
                "maps_converted": sum(len(match.maps) for match in matches),
                "players_converted": sum(len(match.players) for match in matches),
                "vetoes_converted": sum(len(match.vetoes) for match in matches),
                "fixtures_written": len(written),
                "first_fixture": str(written[0]) if written else None,
                "note": "Converted from Kaggle CS:GO Professional Matches dataset with map-level results, vetoes, and player stats when available.",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def materialize_cs_features(args: argparse.Namespace) -> int:
    from sports.cs.features import materialize_map_win_rate_90d
    from sports.cs.normalization import parse_hltv_fixture

    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    matches = [parse_hltv_fixture(Path(path).resolve()) for path in args.fixtures]
    features = materialize_map_win_rate_90d(matches, as_of)
    print(
        json.dumps(
            [
                {
                    "entity_id": feature.entity_id,
                    "name": feature.name,
                    "as_of": feature.as_of.isoformat(),
                    "value": feature.value,
                }
                for feature in features
            ],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def db_materialize_cs_features(args: argparse.Namespace) -> int:
    from sports.cs.features import materialize_map_win_rate_90d
    from sports.cs.normalization import parse_hltv_fixture

    settings = load_settings()
    as_of = datetime.fromisoformat(args.as_of.replace("Z", "+00:00"))
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    fixture_paths = [Path(path).resolve() for path in args.fixtures]
    matches = [parse_hltv_fixture(path) for path in fixture_paths]
    features = materialize_map_win_rate_90d(matches, as_of)
    data_snapshot_id = args.data_snapshot_id or _feature_snapshot_id(fixture_paths, as_of)
    description = args.description or f"CS fixture feature materialization at {as_of.isoformat()}"
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            repo.upsert_data_snapshot(data_snapshot_id, description)
            for feature in features:
                repo.insert_feature_value(feature, data_snapshot_id=data_snapshot_id)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_materialize_cs_features_failed", str(exc))
    print(
        json.dumps(
            {
                "data_snapshot_id": data_snapshot_id,
                "features_upserted": len(features),
                "feature_names": sorted({feature.name for feature in features}),
                "as_of": as_of.isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def db_list_cs_features(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            summaries = repo.list_feature_summaries(feature_name=args.feature_name, entity_prefix=args.entity_prefix)
            values = repo.list_latest_feature_values(
                feature_name=args.feature_name,
                entity_prefix=args.entity_prefix,
                limit=args.limit,
            )
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_cs_features_failed", str(exc))
    print(
        json.dumps(
            {
                "summaries": [
                    {
                        "feature_name": item["feature_name"],
                        "row_count": item["row_count"],
                        "first_as_of": item["first_as_of"].isoformat() if item["first_as_of"] is not None else None,
                        "latest_as_of": item["latest_as_of"].isoformat() if item["latest_as_of"] is not None else None,
                    }
                    for item in summaries
                ],
                "values": [
                    {
                        "entity_id": item["entity_id"],
                        "feature_name": item["feature_name"],
                        "as_of": item["as_of"].isoformat(),
                        "value": item["value"],
                        "data_snapshot_id": item["data_snapshot_id"],
                    }
                    for item in values
                ],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def _feature_snapshot_id(fixture_paths: list[Path], as_of: datetime) -> str:
    digest = hashlib.sha256()
    digest.update(as_of.isoformat().encode("utf-8"))
    for path in sorted(fixture_paths):
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
    return f"cs-fixture-features-{digest.hexdigest()[:16]}"


def evaluate_cs_baseline(args: argparse.Namespace) -> int:
    from sports.cs.models import calibration_payload_from_fixtures, evaluate_baseline_from_fixtures

    settings = load_settings()
    fixture_paths = [Path(path).resolve() for path in args.fixtures]
    artifact_dir = settings.data_dir / "artifacts" / "models" if args.write_artifact else None
    try:
        result = evaluate_baseline_from_fixtures(fixture_paths, artifact_dir)
    except ValueError as exc:
        return print_error("baseline_evaluation_failed", str(exc))
    payload = {
        "rows": result.rows,
        "metrics": result.metrics,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
    }
    if args.include_calibration:
        payload["calibration_buckets"] = calibration_payload_from_fixtures(fixture_paths)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def db_evaluate_cs_baseline(args: argparse.Namespace) -> int:
    from sports.cs.models import calibration_payload_from_fixtures, evaluate_baseline_from_fixtures

    settings = load_settings()
    fixture_paths = [Path(path).resolve() for path in args.fixtures]
    artifact_dir = settings.data_dir / "artifacts" / "models" if args.write_artifact else None
    try:
        result = evaluate_baseline_from_fixtures(fixture_paths, artifact_dir)
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            repo.upsert_model_artifact(result.artifact)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except ValueError as exc:
        return print_error("baseline_evaluation_failed", str(exc))
    except Exception as exc:
        return print_error("db_evaluate_cs_baseline_failed", str(exc))
    payload = {
        "rows": result.rows,
        "model_id": result.artifact.model_id,
        "metrics": result.metrics,
        "artifact_path": str(result.artifact_path) if result.artifact_path else None,
        "persisted": True,
    }
    if args.include_calibration:
        payload["calibration_buckets"] = calibration_payload_from_fixtures(fixture_paths)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def db_list_model_artifacts(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            artifacts = repo.list_model_artifacts(target=args.target, limit=args.limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_model_artifacts_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "model_id": item["model_id"],
                    "game_id": item["game_id"],
                    "target": item["target"],
                    "data_snapshot_id": item["data_snapshot_id"],
                    "config_hash": item["config_hash"],
                    "feature_names": item["feature_names"],
                    "metrics": item["metrics"],
                    "artifact_uri": item["artifact_uri"],
                    "created_at": item["created_at"].isoformat() if item["created_at"] is not None else None,
                }
                for item in artifacts
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def walk_forward_cs_baseline(args: argparse.Namespace) -> int:
    from sports.cs.fixtures import load_fixture_corpus
    from sports.cs.models import evaluate_baseline_walk_forward, walk_forward_payload

    matches = load_fixture_corpus(Path(args.corpus).resolve())
    results = evaluate_baseline_walk_forward(
        matches,
        start=datetime.fromisoformat(args.start).date(),
        end=datetime.fromisoformat(args.end).date(),
        train_days=args.train_days,
        validate_days=args.validate_days,
        step_days=args.step_days,
    )
    print(json.dumps({"windows": walk_forward_payload(results)}, indent=2, sort_keys=True))
    return 0


def db_walk_forward_cs_baseline(args: argparse.Namespace) -> int:
    from sports.cs import GAME_ID
    from sports.cs.fixtures import load_fixture_corpus
    from sports.cs.models import evaluate_baseline_walk_forward, summarize_walk_forward_results, walk_forward_payload

    settings = load_settings()
    corpus_path = Path(args.corpus).resolve()
    try:
        matches = load_fixture_corpus(corpus_path)
        start = datetime.fromisoformat(args.start).date()
        end = datetime.fromisoformat(args.end).date()
        results = evaluate_baseline_walk_forward(
            matches,
            start=start,
            end=end,
            train_days=args.train_days,
            validate_days=args.validate_days,
            step_days=args.step_days,
        )
        windows = walk_forward_payload(results)
        metrics = summarize_walk_forward_results(results)
        data_snapshot_id = args.data_snapshot_id or _corpus_snapshot_id(corpus_path)
        run_config = {
            "corpus": str(corpus_path),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "train_days": args.train_days,
            "validate_days": args.validate_days,
            "step_days": args.step_days,
        }
        backtest_run_id = args.backtest_run_id or _backtest_run_id(args.strategy_id, data_snapshot_id, run_config)
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            repo.upsert_data_snapshot(data_snapshot_id, f"CS fixture corpus snapshot for {corpus_path}")
            repo.upsert_backtest_run(
                backtest_run_id=backtest_run_id,
                strategy_id=args.strategy_id,
                game_id=GAME_ID,
                target="cs.map_winner",
                data_snapshot_id=data_snapshot_id,
                run_config=run_config,
                metrics=metrics,
                window_results=windows,
            )
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except ValueError as exc:
        return print_error("walk_forward_failed", str(exc))
    except Exception as exc:
        return print_error("db_walk_forward_failed", str(exc))
    print(
        json.dumps(
            {
                "backtest_run_id": backtest_run_id,
                "strategy_id": args.strategy_id,
                "data_snapshot_id": data_snapshot_id,
                "target": "cs.map_winner",
                "metrics": metrics,
                "windows": windows,
                "persisted": True,
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_list_backtest_runs(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            runs = repo.list_backtest_runs(strategy_id=args.strategy_id, limit=args.limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_backtest_runs_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "backtest_run_id": item["backtest_run_id"],
                    "strategy_id": item["strategy_id"],
                    "game_id": item["game_id"],
                    "target": item["target"],
                    "data_snapshot_id": item["data_snapshot_id"],
                    "run_config": item["run_config"],
                    "metrics": item["metrics"],
                    "window_results": item["window_results"],
                    "artifact_uri": item["artifact_uri"],
                    "created_at": item["created_at"].isoformat() if item["created_at"] is not None else None,
                }
                for item in runs
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def _corpus_snapshot_id(corpus_path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(str(corpus_path).encode("utf-8"))
    files = [corpus_path] if corpus_path.is_file() else sorted(path for path in corpus_path.glob("*.json") if path.is_file())
    for path in files:
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    return f"cs-fixture-corpus-{digest.hexdigest()[:16]}"


def _backtest_run_id(strategy_id: str, data_snapshot_id: str, run_config: dict[str, object]) -> str:
    digest = hashlib.sha256()
    digest.update(strategy_id.encode("utf-8"))
    digest.update(data_snapshot_id.encode("utf-8"))
    digest.update(json.dumps(run_config, sort_keys=True).encode("utf-8"))
    return f"cs-backtest-{digest.hexdigest()[:16]}"


def paper_evaluate_cs_baseline(args: argparse.Namespace) -> int:
    from sports.cs.fixtures import load_fixture_corpus
    from sports.cs.markets import (
        accepted_paper_recommendations_digest,
        accepted_paper_recommendations_payload,
        compact_paper_evaluation_payload,
        load_market_price_corpus,
        paper_evaluate_baseline,
        paper_evaluation_payload,
        write_accepted_paper_recommendations_artifact,
        write_accepted_paper_recommendations_csv,
        write_paper_evaluation_artifact,
        write_paper_recommendations_csv,
    )

    settings = load_settings()
    matches = load_fixture_corpus(Path(args.corpus).resolve())
    prices = load_market_price_corpus(Path(args.markets).resolve())
    max_per_match = args.max_recommendations_per_match if args.max_recommendations_per_match > 0 else None
    max_daily_bankroll = args.max_daily_bankroll_fraction if args.max_daily_bankroll_fraction > 0 else None
    try:
        summary = paper_evaluate_baseline(
            matches,
            prices,
            min_edge=args.min_edge,
            min_liquidity_usd=args.min_liquidity_usd,
            max_recommendations_per_match=max_per_match,
            market_bankroll_cap=args.market_bankroll_cap,
            max_daily_bankroll_fraction=max_daily_bankroll,
        )
    except ValueError as exc:
        return print_error("paper_evaluation_invalid_controls", str(exc))
    max_accepted_output = args.max_accepted_output if args.max_accepted_output > 0 else None
    if args.digest:
        payload = accepted_paper_recommendations_digest(summary, max_items=max_accepted_output)
    elif args.accepted_only:
        payload = accepted_paper_recommendations_payload(summary, max_items=max_accepted_output)
    else:
        payload = compact_paper_evaluation_payload(summary) if args.compact else paper_evaluation_payload(summary)
    if args.write_artifact:
        artifact_path = write_paper_evaluation_artifact(summary, settings.data_dir / "artifacts" / "paper")
        payload["artifact_path"] = str(artifact_path)
    if args.write_csv:
        csv_path = write_paper_recommendations_csv(summary, settings.data_dir / "artifacts" / "paper")
        payload["csv_path"] = str(csv_path)
    if args.write_accepted_json:
        accepted_json_path = write_accepted_paper_recommendations_artifact(
            summary,
            settings.data_dir / "artifacts" / "paper",
            max_items=max_accepted_output,
        )
        payload["accepted_json_path"] = str(accepted_json_path)
    if args.write_accepted_csv:
        accepted_csv_path = write_accepted_paper_recommendations_csv(
            summary,
            settings.data_dir / "artifacts" / "paper",
            max_items=max_accepted_output,
        )
        payload["accepted_csv_path"] = str(accepted_csv_path)
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0


def db_paper_evaluate_cs_baseline(args: argparse.Namespace) -> int:
    from core.markets import Market
    from sports.cs.fixtures import load_fixture_corpus
    from sports.cs.markets import load_market_price_corpus, paper_evaluate_baseline, paper_evaluation_payload

    settings = load_settings()
    matches = load_fixture_corpus(Path(args.corpus).resolve())
    prices = load_market_price_corpus(Path(args.markets).resolve())
    max_per_match = args.max_recommendations_per_match if args.max_recommendations_per_match > 0 else None
    max_daily_bankroll = args.max_daily_bankroll_fraction if args.max_daily_bankroll_fraction > 0 else None
    try:
        summary = paper_evaluate_baseline(
            matches,
            prices,
            min_edge=args.min_edge,
            min_liquidity_usd=args.min_liquidity_usd,
            max_recommendations_per_match=max_per_match,
            market_bankroll_cap=args.market_bankroll_cap,
            max_daily_bankroll_fraction=max_daily_bankroll,
        )
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            for result in summary.results:
                repo.upsert_market(
                    Market(
                        market_id=result.recommendation.market_id,
                        source="fixture",
                        question=f"Fixture CS map {result.map_index} winner for {result.contest_hltv_id}: {result.team_id}",
                        market_type="cs_map_winner",
                        contest_id=None,
                        outcomes=(result.team_id,),
                        created_at=result.recommendation.taken_at,
                    )
                )
                repo.upsert_recommendation(result.recommendation, strategy_id=args.strategy_id, model_id=args.model_id)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except ValueError as exc:
        return print_error("paper_evaluation_invalid_controls", str(exc))
    except Exception as exc:
        return print_error("db_paper_evaluation_failed", str(exc))
    payload = paper_evaluation_payload(summary)
    payload["persisted"] = True
    payload["strategy_id"] = args.strategy_id
    payload["model_id"] = args.model_id
    print(json.dumps(payload if not args.compact else {key: value for key, value in payload.items() if key != "results"}, indent=2, sort_keys=True, default=str))
    return 0


def db_list_recommendations(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            summaries = repo.list_recommendation_summaries(strategy_id=args.strategy_id)
            recommendations = [] if args.summary_only else repo.list_recommendations(
                strategy_id=args.strategy_id,
                passes_filter=True if args.passing_only else None,
                limit=args.limit,
            )
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_recommendations_failed", str(exc))
    print(
        json.dumps(
            {
                "summaries": summaries,
                "recommendations": [
                    {
                        "recommendation_id": item["recommendation_id"],
                        "market_id": item["market_id"],
                        "outcome": item["outcome"],
                        "taken_at": item["taken_at"].isoformat() if item["taken_at"] is not None else None,
                        "model_id": item["model_id"],
                        "model_prob": item["model_prob"],
                        "market_prob": item["market_prob"],
                        "edge": item["edge"],
                        "bankroll_fraction": item["bankroll_fraction"],
                        "passes_filter": item["passes_filter"],
                        "reason": item["reason"],
                        "strategy_id": item["strategy_id"],
                    }
                    for item in recommendations
                ],
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_log_paper_bets_from_recommendations(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            recommendations = repo.list_recommendations(
                strategy_id=args.strategy_id,
                passes_filter=True,
                limit=args.limit,
            )
            for recommendation in recommendations:
                repo.upsert_paper_bet_from_recommendation(recommendation, bankroll_usd=args.bankroll_usd)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_log_paper_bets_failed", str(exc))
    print(
        json.dumps(
            {
                "strategy_id": args.strategy_id,
                "bankroll_usd": args.bankroll_usd,
                "paper_bets_logged": len(recommendations),
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_list_paper_bets(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            bets = repo.list_paper_bets(strategy_id=args.strategy_id, limit=args.limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_paper_bets_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "bet_id": item["bet_id"],
                    "recommendation_id": item["recommendation_id"],
                    "market_id": item["market_id"],
                    "outcome": item["outcome"],
                    "placed_at": item["placed_at"].isoformat() if item["placed_at"] is not None else None,
                    "model_prob": item["model_prob"],
                    "market_prob": item["market_prob"],
                    "edge": item["edge"],
                    "kelly_fraction": item["kelly_fraction"],
                    "stake_usd": item["stake_usd"],
                    "price_in": item["price_in"],
                    "price_close": item["price_close"],
                    "clv": item["clv"],
                    "resolved_outcome": item["resolved_outcome"],
                    "pnl_usd": item["pnl_usd"],
                    "model_version": item["model_version"],
                    "strategy_id": item["strategy_id"],
                }
                for item in bets
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_summarize_paper_bets(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            summaries = repo.summarize_paper_bets(strategy_id=args.strategy_id)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_summarize_paper_bets_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "strategy_id": item["strategy_id"],
                    "bets": item["bets"],
                    "settled_bets": item["settled_bets"],
                    "open_bets": item["open_bets"],
                    "stake_usd": item["stake_usd"],
                    "pnl_usd": item["pnl_usd"],
                    "roi": item["roi"],
                    "mean_clv": item["mean_clv"],
                    "hit_rate": item["hit_rate"],
                    "first_placed_at": item["first_placed_at"].isoformat() if item["first_placed_at"] is not None else None,
                    "latest_placed_at": item["latest_placed_at"].isoformat() if item["latest_placed_at"] is not None else None,
                }
                for item in summaries
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_summarize_paper_bets_by_day(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            summaries = repo.summarize_paper_bets_by_day(strategy_id=args.strategy_id, limit=args.limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_summarize_paper_bets_by_day_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "placed_date": item["placed_date"].isoformat() if item["placed_date"] is not None else None,
                    "strategy_id": item["strategy_id"],
                    "bets": item["bets"],
                    "settled_bets": item["settled_bets"],
                    "stake_usd": item["stake_usd"],
                    "pnl_usd": item["pnl_usd"],
                    "roi": item["roi"],
                    "mean_clv": item["mean_clv"],
                    "hit_rate": item["hit_rate"],
                }
                for item in summaries
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_check_paper_bet_readiness(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            summaries = repo.summarize_paper_bets(strategy_id=args.strategy_id)
            bets = repo.list_paper_bets(strategy_id=args.strategy_id, limit=args.drawdown_limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_check_paper_bet_readiness_failed", str(exc))
    drawdown_by_strategy = _paper_bet_drawdowns_by_strategy(bets)
    payload = [
        _paper_bet_readiness_payload(
            summary,
            min_settled_bets=args.min_settled_bets,
            min_roi=args.min_roi,
            min_hit_rate=args.min_hit_rate,
            min_mean_clv=args.min_mean_clv,
            min_pnl_usd=args.min_pnl_usd,
            max_drawdown_usd=args.max_drawdown_usd,
            drawdown_usd=drawdown_by_strategy.get(str(summary.get("strategy_id")), 0.0),
        )
        for summary in summaries
    ]
    if not payload and args.strategy_id is not None:
        payload = [
            _paper_bet_readiness_payload(
                {"strategy_id": args.strategy_id, "settled_bets": 0, "roi": None, "hit_rate": None, "mean_clv": None, "pnl_usd": None},
                min_settled_bets=args.min_settled_bets,
                min_roi=args.min_roi,
                min_hit_rate=args.min_hit_rate,
                min_mean_clv=args.min_mean_clv,
                min_pnl_usd=args.min_pnl_usd,
                max_drawdown_usd=args.max_drawdown_usd,
                drawdown_usd=0.0,
            )
        ]
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    return 0 if all(item["passed"] for item in payload) else 1


def _paper_bet_readiness_payload(
    summary: dict[str, object],
    min_settled_bets: int,
    min_roi: float,
    min_hit_rate: float,
    min_mean_clv: float,
    min_pnl_usd: float,
    max_drawdown_usd: float,
    drawdown_usd: float,
) -> dict[str, object]:
    settled_bets = int(summary.get("settled_bets") or 0)
    roi = _optional_float(summary.get("roi"))
    hit_rate = _optional_float(summary.get("hit_rate"))
    mean_clv = _optional_float(summary.get("mean_clv"))
    pnl_usd = _optional_float(summary.get("pnl_usd"))
    checks = [
        {
            "name": "settled_bets",
            "passed": settled_bets >= min_settled_bets,
            "value": settled_bets,
            "threshold": min_settled_bets,
            "direction": "min",
        },
        {
            "name": "roi",
            "passed": (roi or 0.0) >= min_roi,
            "value": roi,
            "threshold": min_roi,
            "direction": "min",
        },
        {
            "name": "hit_rate",
            "passed": (hit_rate or 0.0) >= min_hit_rate,
            "value": hit_rate,
            "threshold": min_hit_rate,
            "direction": "min",
        },
        {
            "name": "mean_clv",
            "passed": (mean_clv or 0.0) >= min_mean_clv,
            "value": mean_clv,
            "threshold": min_mean_clv,
            "direction": "min",
        },
        {
            "name": "pnl_usd",
            "passed": (pnl_usd or 0.0) >= min_pnl_usd,
            "value": pnl_usd,
            "threshold": min_pnl_usd,
            "direction": "min",
        },
        {
            "name": "max_drawdown_usd",
            "passed": drawdown_usd <= max_drawdown_usd,
            "value": drawdown_usd,
            "threshold": max_drawdown_usd,
            "direction": "max",
        },
    ]
    return {
        "strategy_id": summary.get("strategy_id"),
        "passed": all(bool(check["passed"]) for check in checks),
        "checks": checks,
    }


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _paper_bet_drawdowns_by_strategy(bets: list[dict[str, object]]) -> dict[str, float]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for bet in bets:
        if bet.get("pnl_usd") is None:
            continue
        grouped.setdefault(str(bet.get("strategy_id")), []).append(bet)
    return {
        strategy_id: _max_drawdown_usd(strategy_bets)
        for strategy_id, strategy_bets in grouped.items()
    }


def _max_drawdown_usd(bets: list[dict[str, object]]) -> float:
    peak = 0.0
    equity = 0.0
    max_drawdown = 0.0
    for bet in sorted(bets, key=lambda item: item.get("placed_at")):
        equity += float(bet.get("pnl_usd") or 0.0)
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    return max_drawdown


def db_settle_paper_bets_from_market_fixtures(args: argparse.Namespace) -> int:
    from sports.cs.markets import load_market_price_corpus
    from sports.cs.normalization.ids import cs_participant_id

    settings = load_settings()
    prices = load_market_price_corpus(Path(args.markets).resolve())
    settlement_candidates = [
        price
        for price in prices
        if price.close_price is not None or price.resolved_team_hltv_id is not None
    ]
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            for price in settlement_candidates:
                resolved_outcome = (
                    cs_participant_id("hltv", price.resolved_team_hltv_id)
                    if price.resolved_team_hltv_id is not None
                    else None
                )
                repo.update_paper_bet_settlement(
                    market_id=f"fixture:{price.contest_hltv_id}:{price.map_index}:{price.team_id}",
                    outcome=price.team_id,
                    price_close=price.close_price,
                    resolved_outcome=resolved_outcome,
                    strategy_id=args.strategy_id,
                )
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except ValueError as exc:
        return print_error("paper_bet_settlement_failed", str(exc))
    except Exception as exc:
        return print_error("db_settle_paper_bets_failed", str(exc))
    print(
        json.dumps(
            {
                "strategy_id": args.strategy_id,
                "settlement_candidates": len(settlement_candidates),
            },
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def report_cs_baseline_strategy(args: argparse.Namespace) -> int:
    from sports.cs.reports import build_baseline_strategy_report, compact_strategy_report, write_strategy_report

    settings = load_settings()
    try:
        report = build_baseline_strategy_report(
            fixture_corpus=Path(args.corpus).resolve(),
            market_corpus=Path(args.markets).resolve(),
            min_edge=args.min_edge,
            min_liquidity_usd=args.min_liquidity_usd,
            max_recommendations_per_match=args.max_recommendations_per_match if args.max_recommendations_per_match > 0 else None,
            market_bankroll_cap=args.market_bankroll_cap,
            max_daily_bankroll_fraction=args.max_daily_bankroll_fraction if args.max_daily_bankroll_fraction > 0 else None,
            max_brier_score=args.max_brier_score,
            max_log_loss=args.max_log_loss,
            max_total_bankroll_fraction=args.max_total_bankroll_fraction,
            max_drawdown_per_unit_stake=args.max_drawdown_per_unit_stake,
            min_paper_recommendations=args.min_paper_recommendations,
            min_mean_edge=args.min_mean_edge,
        )
    except ValueError as exc:
        error = "strategy_report_empty_dataset" if "no baseline dataset rows" in str(exc) else "strategy_report_invalid_controls"
        return print_error(error, str(exc))
    if args.write_artifact:
        report["artifact_path"] = str(write_strategy_report(report, settings.data_dir / "artifacts" / "reports"))
    if args.compact:
        report = compact_strategy_report(report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


def db_report_cs_baseline_strategy(args: argparse.Namespace) -> int:
    from sports.cs.reports import build_baseline_strategy_report, compact_strategy_report, write_strategy_report

    settings = load_settings()
    try:
        report = build_baseline_strategy_report(
            fixture_corpus=Path(args.corpus).resolve(),
            market_corpus=Path(args.markets).resolve(),
            min_edge=args.min_edge,
            min_liquidity_usd=args.min_liquidity_usd,
            max_recommendations_per_match=args.max_recommendations_per_match if args.max_recommendations_per_match > 0 else None,
            market_bankroll_cap=args.market_bankroll_cap,
            max_daily_bankroll_fraction=args.max_daily_bankroll_fraction if args.max_daily_bankroll_fraction > 0 else None,
            max_brier_score=args.max_brier_score,
            max_log_loss=args.max_log_loss,
            max_total_bankroll_fraction=args.max_total_bankroll_fraction,
            max_drawdown_per_unit_stake=args.max_drawdown_per_unit_stake,
            min_paper_recommendations=args.min_paper_recommendations,
            min_mean_edge=args.min_mean_edge,
        )
        artifact_path = write_strategy_report(report, settings.data_dir / "artifacts" / "reports")
        report["artifact_path"] = str(artifact_path)
        report_id = Path(artifact_path).stem
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            repo.upsert_report_artifact(
                report_id=report_id,
                strategy_id=str(report["strategy_id"]),
                report_type="cs_baseline_strategy",
                artifact_uri=str(artifact_path),
                metrics={
                    "model": report["model"],
                    "paper": {
                        key: value
                        for key, value in dict(report["paper"]).items()  # type: ignore[arg-type]
                        if key != "results"
                    },
                },
                readiness=dict(report["readiness"]),  # type: ignore[arg-type]
            )
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except ValueError as exc:
        error = "strategy_report_empty_dataset" if "no baseline dataset rows" in str(exc) else "strategy_report_invalid_controls"
        return print_error(error, str(exc))
    except Exception as exc:
        return print_error("db_report_cs_baseline_strategy_failed", str(exc))
    output = compact_strategy_report(report) if args.compact else report
    output["persisted"] = True
    print(json.dumps(output, indent=2, sort_keys=True, default=str))
    return 0


def db_list_report_artifacts(args: argparse.Namespace) -> int:
    settings = load_settings()
    try:
        with PostgresExecutor(settings.database_url) as db:
            repo = PostgresRepository(db)
            reports = repo.list_report_artifacts(strategy_id=args.strategy_id, limit=args.limit)
    except MissingPostgresDriverError as exc:
        return print_error("missing_postgres_driver", str(exc))
    except Exception as exc:
        return print_error("db_list_report_artifacts_failed", str(exc))
    print(
        json.dumps(
            [
                {
                    "report_id": item["report_id"],
                    "strategy_id": item["strategy_id"],
                    "report_type": item["report_type"],
                    "artifact_uri": item["artifact_uri"],
                    "metrics": item["metrics"],
                    "readiness": item["readiness"],
                    "created_at": item["created_at"].isoformat() if item["created_at"] is not None else None,
                }
                for item in reports
            ],
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    return 0


def db_backfill_hltv(args: argparse.Namespace) -> int:
    from scripts.backfill_hltv import backfill

    settings = load_settings()
    corpus_dir = Path(args.corpus_dir)
    if not corpus_dir.is_absolute():
        corpus_dir = settings.project_root / corpus_dir
    corpus_dir = corpus_dir.resolve()
    try:
        results = backfill(corpus_dir, dry_run=args.dry_run)
    except Exception as exc:
        return print_error("db_backfill_hltv_failed", str(exc))
    print(json.dumps(results, indent=2, sort_keys=True, default=str))
    return 0 if "error" not in results else 1


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

    imported = 0
    skipped = 0
    for src in sorted(raw_dir.glob("*.json")):
        target = out_dir / src.name
        if target.exists():
            skipped += 1
            continue
        shutil.copy2(src, target)
        imported += 1
    print(json.dumps({"imported": imported, "skipped": skipped, "out_dir": str(out_dir)}))
    return 0


def convert_cs_rolling_stats(args: argparse.Namespace) -> int:
    from sports.cs.ingestion.kaggle_hltv import parse_kaggle_rolling_stats_csv, write_kaggle_rolling_stats_fixture_payloads

    settings = load_settings()
    path = Path(args.path)
    if not path.is_absolute():
        path = settings.project_root / path
    path = path.resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = settings.project_root / out_dir
    out_dir = out_dir.resolve()

    limit = args.limit if hasattr(args, "limit") and args.limit else None
    try:
        matches, features = parse_kaggle_rolling_stats_csv(path, limit=limit)
        written = write_kaggle_rolling_stats_fixture_payloads(matches, features, out_dir)
    except Exception as exc:
        return print_error("rolling_stats_convert_failed", str(exc))
    print(json.dumps({"matches": len(matches), "files_written": len(written), "out_dir": str(out_dir)}, indent=2))
    return 0


def convert_cs2_match_data_betting(args: argparse.Namespace) -> int:
    from sports.cs.ingestion.kaggle_hltv import parse_kaggle_cs2_match_data_csv, write_kaggle_cs2_match_data_fixture_payloads

    settings = load_settings()
    path = Path(args.path)
    if not path.is_absolute():
        path = settings.project_root / path
    path = path.resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = settings.project_root / out_dir
    out_dir = out_dir.resolve()

    limit = args.limit if hasattr(args, "limit") and args.limit else None
    try:
        matches, player_features = parse_kaggle_cs2_match_data_csv(path, limit=limit)
        written = write_kaggle_cs2_match_data_fixture_payloads(matches, player_features, out_dir)
    except Exception as exc:
        return print_error("cs2_match_data_convert_failed", str(exc))
    print(json.dumps({"matches": len(matches), "files_written": len(written), "out_dir": str(out_dir)}, indent=2))
    return 0


def convert_oddspapi_cs2(args: argparse.Namespace) -> int:
    from sports.cs.ingestion.oddspapi import convert_raw_oddspapi_to_market_fixtures

    settings = load_settings()
    raw_dir = Path(args.raw_dir)
    if not raw_dir.is_absolute():
        raw_dir = settings.project_root / raw_dir
    raw_dir = raw_dir.resolve()

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = settings.project_root / out_dir
    out_dir = out_dir.resolve()

    try:
        summary = convert_raw_oddspapi_to_market_fixtures(raw_dir, out_dir)
    except ValueError as exc:
        return print_error("oddspapi_convert_failed", str(exc))
    except Exception as exc:
        return print_error("oddspapi_convert_failed", str(exc))

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    logger = get_logger(__name__)
    parser = argparse.ArgumentParser(prog="betto")
    parser.add_argument("--version", action="store_true", help="Show version and exit.")
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate-config")
    validate_parser.set_defaults(func=validate_config)

    migrations_parser = subparsers.add_parser("migrations")
    migrations_parser.add_argument("--root", default=".")
    migrations_parser.set_defaults(func=show_migrations)

    seed_parser = subparsers.add_parser("seed-cs-raw")
    seed_parser.add_argument("--since", required=True, help="ISO date, e.g. 2026-01-01")
    seed_parser.set_defaults(func=seed_cs_raw)

    pm_parser = subparsers.add_parser("poll-polymarket-cs")
    pm_parser.add_argument("--limit", type=int, default=100)
    pm_parser.add_argument("--offset", type=int, default=0)
    pm_parser.add_argument("--include-closed", action="store_true")
    pm_parser.set_defaults(func=poll_polymarket_cs)

    db_check_parser = subparsers.add_parser("db-check")
    db_check_parser.set_defaults(func=db_check)

    db_driver_parser = subparsers.add_parser("db-driver-info")
    db_driver_parser.set_defaults(func=db_driver_info)

    db_migrations_parser = subparsers.add_parser("db-apply-migrations")
    db_migrations_parser.add_argument("--root", default=".")
    db_migrations_parser.set_defaults(func=db_apply_migrations)

    db_pm_parser = subparsers.add_parser("db-ingest-polymarket-cs")
    db_pm_parser.add_argument("--limit", type=int, default=100)
    db_pm_parser.add_argument("--offset", type=int, default=0)
    db_pm_parser.add_argument("--include-closed", action="store_true")
    db_pm_parser.set_defaults(func=db_ingest_polymarket_cs)

    parse_fixture_parser = subparsers.add_parser("parse-cs-fixture")
    parse_fixture_parser.add_argument("--path", required=True)
    parse_fixture_parser.set_defaults(func=parse_cs_fixture)

    kaggle_results_parser = subparsers.add_parser("convert-cs-kaggle-hltv-results")
    kaggle_results_parser.add_argument("--path", required=True)
    kaggle_results_parser.add_argument("--out-dir", default="data/hltv_kaggle_results")
    kaggle_results_parser.add_argument("--limit", type=int, default=0)
    kaggle_results_parser.set_defaults(func=convert_cs_kaggle_hltv_results)

    kaggle_competitive_parser = subparsers.add_parser("convert-cs-kaggle-competitive-results")
    kaggle_competitive_parser.add_argument("--path", required=True)
    kaggle_competitive_parser.add_argument("--players-path")
    kaggle_competitive_parser.add_argument("--out-dir", default="data/hltv_kaggle_competitive")
    kaggle_competitive_parser.add_argument("--limit", type=int, default=0)
    kaggle_competitive_parser.set_defaults(func=convert_cs_kaggle_competitive_results)

    kaggle_pro_parser = subparsers.add_parser("convert-cs-kaggle-pro-matches")
    kaggle_pro_parser.add_argument("--path", required=True)
    kaggle_pro_parser.add_argument("--picks-path")
    kaggle_pro_parser.add_argument("--players-path")
    kaggle_pro_parser.add_argument("--out-dir", default="data/hltv_kaggle_csgo_pro")
    kaggle_pro_parser.add_argument("--limit", type=int, default=0)
    kaggle_pro_parser.set_defaults(func=convert_cs_kaggle_pro_matches)

    db_fixture_parser = subparsers.add_parser("db-ingest-cs-fixture")
    db_fixture_parser.add_argument("--path", required=True)
    db_fixture_parser.set_defaults(func=db_ingest_cs_fixture)

    features_parser = subparsers.add_parser("materialize-cs-features")
    features_parser.add_argument("--as-of", required=True)
    features_parser.add_argument("--fixtures", nargs="+", required=True)
    features_parser.set_defaults(func=materialize_cs_features)

    db_features_parser = subparsers.add_parser("db-materialize-cs-features")
    db_features_parser.add_argument("--as-of", required=True)
    db_features_parser.add_argument("--fixtures", nargs="+", required=True)
    db_features_parser.add_argument("--data-snapshot-id")
    db_features_parser.add_argument("--description")
    db_features_parser.set_defaults(func=db_materialize_cs_features)

    db_list_features_parser = subparsers.add_parser("db-list-cs-features")
    db_list_features_parser.add_argument("--feature-name")
    db_list_features_parser.add_argument("--entity-prefix")
    db_list_features_parser.add_argument("--limit", type=int, default=20)
    db_list_features_parser.set_defaults(func=db_list_cs_features)

    eval_parser = subparsers.add_parser("evaluate-cs-baseline")
    eval_parser.add_argument("--fixtures", nargs="+", required=True)
    eval_parser.add_argument("--write-artifact", action="store_true")
    eval_parser.add_argument("--include-calibration", action="store_true")
    eval_parser.set_defaults(func=evaluate_cs_baseline)

    db_eval_parser = subparsers.add_parser("db-evaluate-cs-baseline")
    db_eval_parser.add_argument("--fixtures", nargs="+", required=True)
    db_eval_parser.add_argument("--write-artifact", action="store_true")
    db_eval_parser.add_argument("--include-calibration", action="store_true")
    db_eval_parser.set_defaults(func=db_evaluate_cs_baseline)

    db_models_parser = subparsers.add_parser("db-list-model-artifacts")
    db_models_parser.add_argument("--target")
    db_models_parser.add_argument("--limit", type=int, default=20)
    db_models_parser.set_defaults(func=db_list_model_artifacts)

    wf_parser = subparsers.add_parser("walk-forward-cs-baseline")
    wf_parser.add_argument("--corpus", required=True)
    wf_parser.add_argument("--start", required=True)
    wf_parser.add_argument("--end", required=True)
    wf_parser.add_argument("--train-days", type=int, required=True)
    wf_parser.add_argument("--validate-days", type=int, required=True)
    wf_parser.add_argument("--step-days", type=int, required=True)
    wf_parser.set_defaults(func=walk_forward_cs_baseline)

    db_wf_parser = subparsers.add_parser("db-walk-forward-cs-baseline")
    db_wf_parser.add_argument("--corpus", required=True)
    db_wf_parser.add_argument("--start", required=True)
    db_wf_parser.add_argument("--end", required=True)
    db_wf_parser.add_argument("--train-days", type=int, required=True)
    db_wf_parser.add_argument("--validate-days", type=int, required=True)
    db_wf_parser.add_argument("--step-days", type=int, required=True)
    db_wf_parser.add_argument("--strategy-id", default="cs_baseline_fixture_v1")
    db_wf_parser.add_argument("--data-snapshot-id")
    db_wf_parser.add_argument("--backtest-run-id")
    db_wf_parser.set_defaults(func=db_walk_forward_cs_baseline)

    db_backtests_parser = subparsers.add_parser("db-list-backtest-runs")
    db_backtests_parser.add_argument("--strategy-id")
    db_backtests_parser.add_argument("--limit", type=int, default=20)
    db_backtests_parser.set_defaults(func=db_list_backtest_runs)

    paper_parser = subparsers.add_parser("paper-evaluate-cs-baseline")
    paper_parser.add_argument("--corpus", required=True)
    paper_parser.add_argument("--markets", required=True)
    paper_parser.add_argument("--min-edge", type=float, default=0.03)
    paper_parser.add_argument("--min-liquidity-usd", type=float, default=0.0)
    paper_parser.add_argument("--max-recommendations-per-match", type=int, default=0)
    paper_parser.add_argument("--market-bankroll-cap", type=float, default=0.04)
    paper_parser.add_argument("--max-daily-bankroll-fraction", type=float, default=0.0)
    paper_parser.add_argument("--write-artifact", action="store_true")
    paper_parser.add_argument("--write-csv", action="store_true")
    paper_parser.add_argument("--write-accepted-json", action="store_true")
    paper_parser.add_argument("--write-accepted-csv", action="store_true")
    paper_parser.add_argument("--max-accepted-output", type=int, default=0)
    paper_parser.add_argument("--compact", action="store_true")
    paper_parser.add_argument("--accepted-only", action="store_true")
    paper_parser.add_argument("--digest", action="store_true")
    paper_parser.set_defaults(func=paper_evaluate_cs_baseline)

    db_paper_parser = subparsers.add_parser("db-paper-evaluate-cs-baseline")
    db_paper_parser.add_argument("--corpus", required=True)
    db_paper_parser.add_argument("--markets", required=True)
    db_paper_parser.add_argument("--min-edge", type=float, default=0.03)
    db_paper_parser.add_argument("--min-liquidity-usd", type=float, default=0.0)
    db_paper_parser.add_argument("--max-recommendations-per-match", type=int, default=0)
    db_paper_parser.add_argument("--market-bankroll-cap", type=float, default=0.04)
    db_paper_parser.add_argument("--max-daily-bankroll-fraction", type=float, default=0.0)
    db_paper_parser.add_argument("--strategy-id", default="cs_baseline_fixture_v1")
    db_paper_parser.add_argument("--model-id")
    db_paper_parser.add_argument("--compact", action="store_true")
    db_paper_parser.set_defaults(func=db_paper_evaluate_cs_baseline)

    db_recs_parser = subparsers.add_parser("db-list-recommendations")
    db_recs_parser.add_argument("--strategy-id")
    db_recs_parser.add_argument("--passing-only", action="store_true")
    db_recs_parser.add_argument("--summary-only", action="store_true")
    db_recs_parser.add_argument("--limit", type=int, default=20)
    db_recs_parser.set_defaults(func=db_list_recommendations)

    db_log_bets_parser = subparsers.add_parser("db-log-paper-bets-from-recommendations")
    db_log_bets_parser.add_argument("--strategy-id", default="cs_baseline_fixture_v1")
    db_log_bets_parser.add_argument("--bankroll-usd", type=float, default=1000.0)
    db_log_bets_parser.add_argument("--limit", type=int, default=100)
    db_log_bets_parser.set_defaults(func=db_log_paper_bets_from_recommendations)

    db_bets_parser = subparsers.add_parser("db-list-paper-bets")
    db_bets_parser.add_argument("--strategy-id")
    db_bets_parser.add_argument("--limit", type=int, default=20)
    db_bets_parser.set_defaults(func=db_list_paper_bets)

    db_bet_summary_parser = subparsers.add_parser("db-summarize-paper-bets")
    db_bet_summary_parser.add_argument("--strategy-id")
    db_bet_summary_parser.set_defaults(func=db_summarize_paper_bets)

    db_bet_daily_parser = subparsers.add_parser("db-summarize-paper-bets-by-day")
    db_bet_daily_parser.add_argument("--strategy-id")
    db_bet_daily_parser.add_argument("--limit", type=int, default=30)
    db_bet_daily_parser.set_defaults(func=db_summarize_paper_bets_by_day)

    db_bet_readiness_parser = subparsers.add_parser("db-check-paper-bet-readiness")
    db_bet_readiness_parser.add_argument("--strategy-id", default="cs_baseline_fixture_v1")
    db_bet_readiness_parser.add_argument("--min-settled-bets", type=int, default=1)
    db_bet_readiness_parser.add_argument("--min-roi", type=float, default=0.0)
    db_bet_readiness_parser.add_argument("--min-hit-rate", type=float, default=0.0)
    db_bet_readiness_parser.add_argument("--min-mean-clv", type=float, default=0.0)
    db_bet_readiness_parser.add_argument("--min-pnl-usd", type=float, default=0.0)
    db_bet_readiness_parser.add_argument("--max-drawdown-usd", type=float, default=1000000000.0)
    db_bet_readiness_parser.add_argument("--drawdown-limit", type=int, default=1000)
    db_bet_readiness_parser.set_defaults(func=db_check_paper_bet_readiness)

    db_settle_bets_parser = subparsers.add_parser("db-settle-paper-bets-from-market-fixtures")
    db_settle_bets_parser.add_argument("--markets", required=True)
    db_settle_bets_parser.add_argument("--strategy-id", default="cs_baseline_fixture_v1")
    db_settle_bets_parser.set_defaults(func=db_settle_paper_bets_from_market_fixtures)

    report_parser = subparsers.add_parser("report-cs-baseline-strategy")
    report_parser.add_argument("--corpus", required=True)
    report_parser.add_argument("--markets", required=True)
    report_parser.add_argument("--min-edge", type=float, default=0.03)
    report_parser.add_argument("--min-liquidity-usd", type=float, default=0.0)
    report_parser.add_argument("--max-recommendations-per-match", type=int, default=0)
    report_parser.add_argument("--market-bankroll-cap", type=float, default=0.04)
    report_parser.add_argument("--max-daily-bankroll-fraction", type=float, default=0.0)
    report_parser.add_argument("--max-brier-score", type=float, default=0.30)
    report_parser.add_argument("--max-log-loss", type=float, default=0.80)
    report_parser.add_argument("--max-total-bankroll-fraction", type=float, default=0.25)
    report_parser.add_argument("--max-drawdown-per-unit-stake", type=float, default=3.0)
    report_parser.add_argument("--min-paper-recommendations", type=int, default=1)
    report_parser.add_argument("--min-mean-edge", type=float, default=0.03)
    report_parser.add_argument("--write-artifact", action="store_true")
    report_parser.add_argument("--compact", action="store_true")
    report_parser.set_defaults(func=report_cs_baseline_strategy)

    db_report_parser = subparsers.add_parser("db-report-cs-baseline-strategy")
    db_report_parser.add_argument("--corpus", required=True)
    db_report_parser.add_argument("--markets", required=True)
    db_report_parser.add_argument("--min-edge", type=float, default=0.03)
    db_report_parser.add_argument("--min-liquidity-usd", type=float, default=0.0)
    db_report_parser.add_argument("--max-recommendations-per-match", type=int, default=0)
    db_report_parser.add_argument("--market-bankroll-cap", type=float, default=0.04)
    db_report_parser.add_argument("--max-daily-bankroll-fraction", type=float, default=0.0)
    db_report_parser.add_argument("--max-brier-score", type=float, default=0.30)
    db_report_parser.add_argument("--max-log-loss", type=float, default=0.80)
    db_report_parser.add_argument("--max-total-bankroll-fraction", type=float, default=0.25)
    db_report_parser.add_argument("--max-drawdown-per-unit-stake", type=float, default=3.0)
    db_report_parser.add_argument("--min-paper-recommendations", type=int, default=1)
    db_report_parser.add_argument("--min-mean-edge", type=float, default=0.03)
    db_report_parser.add_argument("--compact", action="store_true")
    db_report_parser.set_defaults(func=db_report_cs_baseline_strategy)

    db_reports_parser = subparsers.add_parser("db-list-report-artifacts")
    db_reports_parser.add_argument("--strategy-id")
    db_reports_parser.add_argument("--limit", type=int, default=20)
    db_reports_parser.set_defaults(func=db_list_report_artifacts)

    db_backfill_parser = subparsers.add_parser("db-backfill-hltv")
    db_backfill_parser.add_argument("--corpus-dir", default="data/hltv_backfill")
    db_backfill_parser.add_argument("--dry-run", action="store_true")
    db_backfill_parser.set_defaults(func=db_backfill_hltv)

    hltv_scraped_parser = subparsers.add_parser("convert-hltv-scraped")
    hltv_scraped_parser.add_argument("--raw-dir", default="data/hltv_scraped")
    hltv_scraped_parser.add_argument("--out-dir", default="data/hltv_fixtures")
    hltv_scraped_parser.set_defaults(func=convert_hltv_scraped)

    db_ingest_scraped_parser = subparsers.add_parser("db-ingest-hltv-scraped")
    db_ingest_scraped_parser.add_argument("--scraped-dir", default="data/hltv_scraped")
    db_ingest_scraped_parser.add_argument("--force", action="store_true", help="Re-ingest already imported matches")
    db_ingest_scraped_parser.set_defaults(func=db_ingest_hltv_scraped)

    rolling_stats_parser = subparsers.add_parser("convert-cs-rolling-stats")
    rolling_stats_parser.add_argument("--path", required=True)
    rolling_stats_parser.add_argument("--out-dir", default="data/cs2_rolling_stats")
    rolling_stats_parser.add_argument("--limit", type=int, default=None)
    rolling_stats_parser.set_defaults(func=convert_cs_rolling_stats)

    cs2_betting_parser = subparsers.add_parser("convert-cs2-match-data-betting")
    cs2_betting_parser.add_argument("--path", required=True)
    cs2_betting_parser.add_argument("--out-dir", default="data/cs2_match_data_betting")
    cs2_betting_parser.add_argument("--limit", type=int, default=None)
    cs2_betting_parser.set_defaults(func=convert_cs2_match_data_betting)

    oddspapi_convert_parser = subparsers.add_parser("convert-oddspapi-cs2")
    oddspapi_convert_parser.add_argument("--raw-dir", default="data/oddspapi_raw")
    oddspapi_convert_parser.add_argument("--out-dir", default="data/oddspapi_markets")
    oddspapi_convert_parser.set_defaults(func=convert_oddspapi_cs2)

    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    logger.info("running command", extra={"run_id": "cli"})
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
