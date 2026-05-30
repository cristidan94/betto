from __future__ import annotations

import re
from pathlib import Path

from scraper.config import load_config
from scraper.fetcher import FetchResult, HltvFetcher
from scraper.parser import parse_map_stats_page, parse_match_page, parse_results_page, parse_stats_page
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


def run_live_test(fixtures_dir: Path | None = None) -> int:
    config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        cooldown_every=config.cooldown_every,
        cooldown_seconds=config.cooldown_seconds,
        daily_cap=config.daily_cap,
    )
    db = TrackingDB(config.db_path)
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    output_dir = fixtures_dir or Path("tests") / "fixtures"
    output_dir.mkdir(parents=True, exist_ok=True)
    passed = 0
    failed = 0
    entries = []
    try:
        print("\n=== Test 1: Results page ===")
        limiter.sleep()
        result = fetcher.fetch("https://www.hltv.org/results?offset=0")
        _report_fetch("results page", result)
        if result.ok:
            entries = parse_results_page(result.html)
            print(f"  Parsed: {len(entries)} matches found")
            if entries:
                (output_dir / "results_page.html").write_text(result.html, encoding="utf-8")
                passed += 1
            else:
                failed += 1
        else:
            failed += 1

        if entries:
            test_match = entries[0]
            match_id = test_match["match_id"]
            match_url = f"https://www.hltv.org{test_match['match_url']}"
            print(f"\n=== Test 2: Match page ({match_id}) ===")
            limiter.sleep()
            match_result = fetcher.fetch(match_url)
            _report_fetch(f"match {match_id}", match_result)
            if match_result.ok:
                (output_dir / f"match_{match_id}.html").write_text(match_result.html, encoding="utf-8")
                match_data = parse_match_page(match_result.html, match_id)
                print(f"  Parsed: {match_data['team_a']['name']} vs {match_data['team_b']['name']}")
                passed += 1
                if match_data.get("stats_url"):
                    print(f"\n=== Test 3: Stats page ===")
                    limiter.sleep()
                    stats_result = fetcher.fetch(match_data["stats_url"])
                    _report_fetch(f"stats {match_id}", stats_result)
                    if stats_result.ok:
                        parse_stats_page(stats_result.html)
                        passed += 1
                    else:
                        failed += 1
                first_map = match_data.get("maps", [{}])[0] if match_data.get("maps") else {}
                if first_map.get("map_stats_id"):
                    team_slug = _build_team_slug(match_data)
                    print(f"\n=== Test 4: Map stats page ===")
                    limiter.sleep()
                    map_result = fetcher.fetch(f"https://www.hltv.org/stats/matches/mapstatsid/{first_map['map_stats_id']}/{team_slug}")
                    _report_fetch(f"map stats {first_map['map_stats_id']}", map_result)
                    if map_result.ok:
                        parse_map_stats_page(map_result.html)
                        passed += 1
                    else:
                        failed += 1
            else:
                failed += 1

        print("\n=== Test 5: Playwright fallback ===")
        limiter.sleep()
        pw_result = fetcher._fetch_playwright("https://www.hltv.org/results?offset=0")
        _report_fetch("playwright results", pw_result)
        if pw_result.ok and parse_results_page(pw_result.html):
            passed += 1
        else:
            failed += 1
    finally:
        fetcher.close()
        db.close()

    print(f"\nResults: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


def _build_team_slug(match_data: dict) -> str:
    team_a = match_data.get("team_a") or {}
    team_b = match_data.get("team_b") or {}
    a_name = re.sub(r"[^a-z0-9]+", "-", str(team_a.get("name") or "team1").lower()).strip("-")
    b_name = re.sub(r"[^a-z0-9]+", "-", str(team_b.get("name") or "team2").lower()).strip("-")
    return f"{a_name}-vs-{b_name}"


def _report_fetch(label: str, result: FetchResult) -> None:
    status = "OK" if result.ok else "FAIL"
    print(f"  {label}: {status} ({result.content_bytes // 1024}KB, {result.fetcher_type}, {result.elapsed_ms}ms)")
