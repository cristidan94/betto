from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path

from scraper.backup import create_backup
from scraper.config import load_config
from scraper.discovery import discover_matches
from scraper.fetcher import HltvFetcher
from scraper.match_scraper import _assemble_match, scrape_one_match
from scraper.parser import parse_match_page
from scraper.pipeline import run_pipeline
from scraper.preflight import collect_preflight
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


def cmd_discover(args: argparse.Namespace) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(config.min_delay, config.max_delay)
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
    limiter = RateLimiter(config.min_delay, config.max_delay, config.cooldown_every, config.cooldown_seconds, config.daily_cap)
    db = TrackingDB(config.db_path)
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
            db.mark_parsed(row["match_id"])
            parsed += 1
    finally:
        db.close()
    print(json.dumps({"parsed": parsed}))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    result = run_pipeline(load_config())
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config()
    db = TrackingDB(config.db_path)
    try:
        print(json.dumps({"queue": db.queue_stats(), "requests_today": db.request_count_today()}, indent=2))
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

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
