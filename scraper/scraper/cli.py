from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

from scraper.alerts import send_webhook
from scraper.entity_scraper import scrape_events, scrape_players, scrape_teams
from scraper.rankings import scrape_rankings, scrape_rankings_range
from scraper.tier_registry import describe_registry, load_tier_registry
from scraper.backup import create_backup
from scraper.backfill import BACKFILL_DONE, BACKFILL_DONE_ALERTED, BACKFILL_EMPTY_PAGES, BACKFILL_NEXT_PAGE, run_backfill
from scraper.config import load_config
from scraper.discovery import discover_matches, discover_upcoming
from scraper.fetcher import HltvFetcher
from scraper.health import collect_health
from scraper.inspect import show_match
from scraper.manifest import write_manifest
from scraper.match_scraper import _apply_queue_metadata, _assemble_match, _priority_from_event, _update_lifecycle, scrape_one_match
from scraper.parser import parse_map_stats_page, parse_match_page, parse_stats_page
from scraper.pipeline import run_pipeline
from scraper.preflight import collect_preflight
from scraper.proxy import ProxyRotator
from scraper.quality import collect_quality_report
from scraper.rate_limiter import RateLimiter
from scraper.report import write_html_report
from scraper.status import collect_status
from scraper.stats_gaps import collect_stats_gaps, retry_stats_gaps, stats_error_summary
from scraper.tracking_db import TrackingDB
from scraper.validator import validate_fixtures


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        count = discover_matches(fetcher, db, config, max_pages=args.limit or 10)
        print(json.dumps({"discovered": count}))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_discover_upcoming(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        result = discover_upcoming(fetcher, db, config)
        print(json.dumps(result, indent=2))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    fetched = 0
    try:
        for row in db.pending_matches(limit=args.limit or 50):
            if limiter.daily_cap_reached():
                break
            proxy.start_sticky_session()
            try:
                if scrape_one_match(row["match_id"], row["match_url"], fetcher, db, limiter, config):
                    fetched += 1
            finally:
                proxy.end_sticky_session()
        print(json.dumps({"fetched": fetched}))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    from scraper.models import write_fixture_json

    config = load_config()
    db = TrackingDB(config.db_path)
    parsed = 0
    try:
        for row in db.pending_matches(limit=10000):
            match_dir = config.raw_dir / "matches" / row["match_id"]
            match_html = match_dir / "match.html"
            if not match_html.exists():
                continue
            match_data = parse_match_page(match_html.read_text(encoding="utf-8"), row["match_id"])
            scraped = _assemble_match(match_data, [], {})
            write_fixture_json(scraped, config.output_dir)
            _update_lifecycle(db, scraped)
            parsed += 1
    finally:
        db.close()
    print(json.dumps({"parsed": parsed}))
    return 0


def cmd_reparse_raw(args: argparse.Namespace) -> int:
    config = load_config()
    db = TrackingDB(config.db_path)
    parsed = 0
    skipped = 0
    try:
        match_dirs = sorted((config.raw_dir / "matches").glob("*")) if (config.raw_dir / "matches").exists() else []
        for match_dir in match_dirs:
            if args.limit is not None and parsed >= args.limit:
                break
            if not match_dir.is_dir():
                continue
            match_id = match_dir.name
            match_html = match_dir / "match.html"
            if not match_html.exists():
                skipped += 1
                continue
            match_data = parse_match_page(match_html.read_text(encoding="utf-8"), match_id)
            queue_row = db.get_match(match_id)
            if queue_row is None:
                event = match_data.get("event") if isinstance(match_data.get("event"), dict) else {}
                db.upsert_match(
                    match_id,
                    f"/matches/{match_id}",
                    event_name=event.get("name"),
                    event_stars=event.get("stars"),
                    priority_tier=_priority_from_event(str(event.get("name") or ""), event.get("stars"), config) or 9,
                )
                queue_row = db.get_match(match_id)
            _apply_queue_metadata(match_data, queue_row, config)
            stats_players = []
            stats_html = match_dir / "stats.html"
            if stats_html.exists():
                stats_players = parse_stats_page(stats_html.read_text(encoding="utf-8")).get("players", [])
            map_stats = {}
            for map_file in sorted(match_dir.glob("map_*.html")):
                stats_id = map_file.stem.removeprefix("map_")
                map_stats[stats_id] = parse_map_stats_page(map_file.read_text(encoding="utf-8"))
            scraped = _assemble_match(match_data, stats_players, map_stats)
            from scraper.models import write_fixture_json

            write_fixture_json(scraped, config.output_dir)
            _update_lifecycle(db, scraped)
            parsed += 1
    finally:
        db.close()
    print(json.dumps({"reparsed": parsed, "skipped": skipped}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    result = run_pipeline(load_config(), max_discovery_pages=args.discovery_pages, max_matches=args.matches)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    result = run_pipeline(load_config(), max_discovery_pages=args.pages, max_matches=args.matches)
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_backfill_auto(args: argparse.Namespace) -> int:
    result = run_backfill(
        load_config(),
        pages_per_run=args.pages_per_run,
        max_matches=args.matches,
        empty_pages_to_stop=args.empty_pages_to_stop,
        disable_timer_on_done=args.disable_timer_on_done,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config()
    if args.verbose:
        print(json.dumps(collect_status(config, args.recent), indent=2))
        return 0
    db = TrackingDB(config.db_path)
    try:
        print(json.dumps({"queue": db.queue_stats(), "requests_today": db.request_count_today()}, indent=2))
    finally:
        db.close()
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    result = collect_health(
        load_config(),
        recent_limit=args.recent,
        max_recent_failure_rate=args.max_recent_failure_rate,
        max_failed_queue_ratio=args.max_failed_queue_ratio,
    )
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_quality(args: argparse.Namespace) -> int:
    print(json.dumps(collect_quality_report(load_config(), sample_limit=args.sample), indent=2))
    return 0


def cmd_validate_fixtures(args: argparse.Namespace) -> int:
    result = validate_fixtures(load_config(), sample_limit=args.sample)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_failed(args: argparse.Namespace) -> int:
    db = TrackingDB(load_config().db_path)
    try:
        print(json.dumps({"matches": db.failed_matches(limit=args.limit)}, indent=2, default=str))
    finally:
        db.close()
    return 0


def cmd_show_match(args: argparse.Namespace) -> int:
    print(json.dumps(show_match(args.match_id, load_config()), indent=2, default=str))
    return 0


def cmd_stats_gaps(args: argparse.Namespace) -> int:
    print(json.dumps(collect_stats_gaps(load_config(), limit=args.limit), indent=2))
    return 0


def cmd_retry_stats_only(args: argparse.Namespace) -> int:
    print(json.dumps(retry_stats_gaps(load_config(), limit=args.limit), indent=2))
    return 0


def cmd_stats_errors(args: argparse.Namespace) -> int:
    print(json.dumps(stats_error_summary(load_config(), limit=args.limit), indent=2))
    return 0


def cmd_retry_failed(args: argparse.Namespace) -> int:
    db = TrackingDB(load_config().db_path)
    try:
        count = db.retry_failed(limit=args.limit, min_retries=args.min_retries)
        print(json.dumps({"queued_for_retry": count}))
    finally:
        db.close()
    return 0


def cmd_reset_backfill(args: argparse.Namespace) -> int:
    db = TrackingDB(load_config().db_path)
    try:
        db.set_int_state(BACKFILL_NEXT_PAGE, args.start_page)
        db.set_int_state(BACKFILL_EMPTY_PAGES, 0)
        db.set_state(BACKFILL_DONE, "0")
        db.set_state(BACKFILL_DONE_ALERTED, "0")
        print(json.dumps({"backfill_reset": True, "next_page": args.start_page, "next_offset": args.start_page * 100}))
    finally:
        db.close()
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    result = collect_preflight(create_dirs=args.create_dirs)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


def cmd_test_live(args: argparse.Namespace) -> int:
    from scraper.live_test import run_live_test

    return run_live_test()


def cmd_export(args: argparse.Namespace) -> int:
    config = load_config()
    dest = Path(args.out_dir or "data/hltv_fixtures")
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in config.output_dir.glob("*.json"):
        target = dest / src.name
        if not target.exists():
            shutil.copy2(src, target)
            count += 1
    print(json.dumps({"exported": count, "to": str(dest)}))
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    path = create_backup(load_config(), args.out_dir)
    print(json.dumps({"backup": str(path)}))
    return 0


def cmd_manifest(args: argparse.Namespace) -> int:
    path = write_manifest(Path(args.out), load_config(), include_files=args.include_files)
    print(json.dumps({"manifest": str(path)}))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    path = write_html_report(Path(args.out), load_config())
    print(json.dumps({"report": str(path)}))
    return 0


def cmd_scrape_events(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        ids = args.ids.split(",") if args.ids else None
        result = scrape_events(fetcher, db, limiter, config, event_ids=ids, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_scrape_teams(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        ids = args.ids.split(",") if args.ids else None
        result = scrape_teams(fetcher, db, limiter, config, team_ids=ids, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_scrape_players(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        ids = args.ids.split(",") if args.ids else None
        result = scrape_players(fetcher, db, limiter, config, player_ids=ids, limit=args.limit)
        print(json.dumps(result, indent=2))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_scrape_rankings(args: argparse.Namespace) -> int:
    from datetime import date as _date

    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        if args.start:
            start = _date.fromisoformat(args.start)
            end = _date.fromisoformat(args.end) if args.end else None
            results = scrape_rankings_range(fetcher, limiter, config, start, end)
            print(json.dumps(results, indent=2))
        else:
            ranking_date = _date.fromisoformat(args.date) if args.date else None
            result = scrape_rankings(fetcher, limiter, config, ranking_date)
            print(json.dumps(result, indent=2))
    finally:
        fetcher.close()
        db.close()
    return 0


def cmd_tier_registry(args: argparse.Namespace) -> int:
    config = load_config()
    registry = load_tier_registry(config.tier_registry_path)
    print(json.dumps(describe_registry(registry), indent=2))
    return 0


def cmd_alert(args: argparse.Namespace) -> int:
    config = load_config()
    payload = {
        "status": collect_status(config, recent_limit=args.recent),
        "health": collect_health(config, recent_limit=args.recent),
        "quality": collect_quality_report(config, sample_limit=args.sample),
    }
    result = send_webhook(config.alert_webhook_url, args.title, payload)
    print(json.dumps(result, indent=2))
    return 0 if result.get("sent") or result.get("reason") == "not_configured" else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="hltv-scraper")
    subparsers = parser.add_subparsers(dest="command")

    disc = subparsers.add_parser("discover")
    disc.add_argument("--limit", type=int, default=10)
    disc.set_defaults(func=cmd_discover)

    disc_upcoming = subparsers.add_parser("discover-upcoming")
    disc_upcoming.set_defaults(func=cmd_discover_upcoming)

    fetch = subparsers.add_parser("fetch")
    fetch.add_argument("--limit", type=int, default=50)
    fetch.set_defaults(func=cmd_fetch)

    parse = subparsers.add_parser("parse")
    parse.set_defaults(func=cmd_parse)

    reparse_raw = subparsers.add_parser("reparse-raw")
    reparse_raw.add_argument("--limit", type=int, default=None)
    reparse_raw.set_defaults(func=cmd_reparse_raw)

    run = subparsers.add_parser("run")
    run.add_argument("--discovery-pages", type=int, default=10)
    run.add_argument("--matches", type=int, default=100)
    run.set_defaults(func=cmd_run)

    backfill = subparsers.add_parser("backfill")
    backfill.add_argument("--pages", type=int, default=50)
    backfill.add_argument("--matches", type=int, default=100)
    backfill.set_defaults(func=cmd_backfill)

    backfill_auto = subparsers.add_parser("backfill-auto")
    backfill_auto.add_argument("--pages-per-run", type=int, default=None)
    backfill_auto.add_argument("--matches", type=int, default=None)
    backfill_auto.add_argument("--empty-pages-to-stop", type=int, default=None)
    backfill_auto.add_argument("--disable-timer-on-done", default=None)
    backfill_auto.set_defaults(func=cmd_backfill_auto)

    status = subparsers.add_parser("status")
    status.add_argument("--verbose", action="store_true")
    status.add_argument("--recent", type=int, default=10)
    status.set_defaults(func=cmd_status)

    health = subparsers.add_parser("health")
    health.add_argument("--recent", type=int, default=25)
    health.add_argument("--max-recent-failure-rate", type=float, default=0.5)
    health.add_argument("--max-failed-queue-ratio", type=float, default=0.25)
    health.set_defaults(func=cmd_health)

    quality = subparsers.add_parser("quality-report")
    quality.add_argument("--sample", type=int, default=10)
    quality.set_defaults(func=cmd_quality)

    validate = subparsers.add_parser("validate-fixtures")
    validate.add_argument("--sample", type=int, default=25)
    validate.set_defaults(func=cmd_validate_fixtures)

    failed = subparsers.add_parser("failed")
    failed.add_argument("--limit", type=int, default=50)
    failed.set_defaults(func=cmd_failed)

    show = subparsers.add_parser("show-match")
    show.add_argument("match_id")
    show.set_defaults(func=cmd_show_match)

    stats_gaps = subparsers.add_parser("stats-gaps")
    stats_gaps.add_argument("--limit", type=int, default=100)
    stats_gaps.set_defaults(func=cmd_stats_gaps)

    retry_stats = subparsers.add_parser("retry-stats-only")
    retry_stats.add_argument("--limit", type=int, default=100)
    retry_stats.set_defaults(func=cmd_retry_stats_only)

    stats_errors = subparsers.add_parser("stats-errors")
    stats_errors.add_argument("--limit", type=int, default=200)
    stats_errors.set_defaults(func=cmd_stats_errors)

    retry_failed = subparsers.add_parser("retry-failed")
    retry_failed.add_argument("--limit", type=int, default=100)
    retry_failed.add_argument("--min-retries", type=int, default=1)
    retry_failed.set_defaults(func=cmd_retry_failed)

    reset_backfill = subparsers.add_parser("reset-backfill")
    reset_backfill.add_argument("--start-page", type=int, default=0)
    reset_backfill.set_defaults(func=cmd_reset_backfill)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--create-dirs", action="store_true")
    preflight.set_defaults(func=cmd_preflight)

    test_live = subparsers.add_parser("test-live")
    test_live.set_defaults(func=cmd_test_live)

    export = subparsers.add_parser("export")
    export.add_argument("--out-dir", default=None)
    export.set_defaults(func=cmd_export)

    backup = subparsers.add_parser("backup")
    backup.add_argument("--out-dir", default="backups")
    backup.set_defaults(func=cmd_backup)

    manifest = subparsers.add_parser("manifest")
    manifest.add_argument("--out", default="data/hltv_scraped/manifest.json")
    manifest.add_argument("--include-files", action="store_true")
    manifest.set_defaults(func=cmd_manifest)

    report = subparsers.add_parser("report")
    report.add_argument("--out", default="data/hltv_scraped/report.html")
    report.set_defaults(func=cmd_report)

    scrape_ev = subparsers.add_parser("scrape-events")
    scrape_ev.add_argument("--ids", default=None, help="Comma-separated event IDs")
    scrape_ev.add_argument("--limit", type=int, default=50)
    scrape_ev.set_defaults(func=cmd_scrape_events)

    scrape_tm = subparsers.add_parser("scrape-teams")
    scrape_tm.add_argument("--ids", default=None, help="Comma-separated team IDs")
    scrape_tm.add_argument("--limit", type=int, default=50)
    scrape_tm.set_defaults(func=cmd_scrape_teams)

    scrape_pl = subparsers.add_parser("scrape-players")
    scrape_pl.add_argument("--ids", default=None, help="Comma-separated player IDs")
    scrape_pl.add_argument("--limit", type=int, default=100)
    scrape_pl.set_defaults(func=cmd_scrape_players)

    scrape_rank = subparsers.add_parser("scrape-rankings")
    scrape_rank.add_argument("--date", default=None, help="YYYY-MM-DD date (defaults to latest Monday)")
    scrape_rank.add_argument("--start", default=None, help="Range start date YYYY-MM-DD")
    scrape_rank.add_argument("--end", default=None, help="Range end date YYYY-MM-DD")
    scrape_rank.set_defaults(func=cmd_scrape_rankings)

    tier_reg = subparsers.add_parser("tier-registry")
    tier_reg.set_defaults(func=cmd_tier_registry)

    alert = subparsers.add_parser("alert")
    alert.add_argument("--title", default="HLTV scraper status")
    alert.add_argument("--recent", type=int, default=25)
    alert.add_argument("--sample", type=int, default=10)
    alert.set_defaults(func=cmd_alert)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
