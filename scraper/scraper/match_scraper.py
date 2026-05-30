from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.models import (
    ScrapedEvent,
    ScrapedMap,
    ScrapedMatch,
    ScrapedPlayer,
    ScrapedPlayerMapStats,
    ScrapedTeam,
    ScrapedVeto,
    write_fixture_json,
)
from scraper.parser import parse_map_stats_page, parse_match_page, parse_stats_page
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB


SCHEDULED_REFRESH_SECONDS = 6 * 60 * 60
LIVE_REFRESH_SECONDS = 15 * 60
INCOMPLETE_FINISHED_REFRESH_SECONDS = 60 * 60
STATS_RETRY_SECONDS = 30 * 60
MAX_MAP_STATS_RETRIES = 2


def scrape_one_match(
    match_id: str,
    match_url: str,
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
    config: ScraperConfig,
) -> ScrapedMatch | None:
    url = match_url if match_url.startswith("http") else f"https://www.hltv.org{match_url}"
    result = fetcher.fetch(url)
    if not result.ok:
        db.record_error(match_id, f"match fetch failed: {result.status}")
        return None
    fetcher._save_raw(match_id, "match.html", result.html)
    db.mark_match_fetched(match_id)

    match_data = parse_match_page(result.html, match_id)
    _apply_queue_metadata(match_data, db.get_match(match_id), config)

    stats_data: dict[str, Any] = {}
    limiter.sleep()
    stats_error = _fetch_stats_page(match_id, match_data, fetcher, db, limiter)
    if stats_error is None:
        stats_html_path = config.raw_dir / "matches" / match_id / "stats.html"
        if stats_html_path.exists():
            stats_data = parse_stats_page(stats_html_path.read_text(encoding="utf-8"))

    team_slug = _build_team_slug(match_data)
    map_stats: dict[str, list[dict[str, Any]]] = {}
    map_errors: list[str] = []
    db.set_maps_total(match_id, len(match_data.get("maps", [])))
    for item in match_data.get("maps", []):
        map_stats_id = item.get("map_stats_id")
        if not map_stats_id:
            continue
        parsed, error = _fetch_map_stats(match_id, map_stats_id, team_slug, fetcher, db, limiter)
        if parsed is not None:
            map_stats[map_stats_id] = parsed
        elif error:
            map_errors.append(error)

    if stats_error or map_errors:
        combined = "; ".join(filter(None, [stats_error] + map_errors))
        db.record_stats_error(match_id, combined)
    else:
        db.clear_stats_error(match_id)

    scraped = _assemble_match(match_data, stats_data.get("players", []), map_stats)
    write_fixture_json(scraped, config.output_dir)
    _update_lifecycle(db, scraped)
    return scraped


def _fetch_stats_page(
    match_id: str,
    match_data: dict[str, Any],
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
) -> str | None:
    stats_url = match_data.get("stats_url")
    if not stats_url:
        return "no_stats_url" if match_data.get("status") == "finished" else None
    limiter.sleep()
    stats_result = fetcher.fetch(stats_url)
    if stats_result.ok:
        fetcher._save_raw(match_id, "stats.html", stats_result.html)
        db.mark_stats_fetched(match_id)
        return None
    return _classify_fetch_error(stats_result)


def _fetch_map_stats(
    match_id: str,
    map_stats_id: str,
    team_slug: str,
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    url = f"https://www.hltv.org/stats/matches/mapstatsid/{map_stats_id}/{team_slug}"
    for attempt in range(1, MAX_MAP_STATS_RETRIES + 1):
        limiter.sleep()
        result = fetcher.fetch(url)
        if result.ok:
            fetcher._save_raw(match_id, f"map_{map_stats_id}.html", result.html)
            parsed = parse_map_stats_page(result.html)
            if parsed:
                db.increment_maps_fetched(match_id)
                return parsed, None
            return None, f"map_{map_stats_id}:parse_empty"
        if result.status == 404:
            return None, f"map_{map_stats_id}:404"
        if attempt < MAX_MAP_STATS_RETRIES:
            limiter.sleep()
    return None, f"map_{map_stats_id}:{_classify_fetch_error(result)}"


def _build_team_slug(match_data: dict[str, Any]) -> str:
    team_a = match_data.get("team_a") or {}
    team_b = match_data.get("team_b") or {}
    a_name = re.sub(r"[^a-z0-9]+", "-", str(team_a.get("name") or "team1").lower()).strip("-")
    b_name = re.sub(r"[^a-z0-9]+", "-", str(team_b.get("name") or "team2").lower()).strip("-")
    return f"{a_name}-vs-{b_name}"


def _classify_fetch_error(result: Any) -> str:
    if result.status == 0:
        html_lower = result.html.lower() if result.html else ""
        if "timeout" in html_lower:
            return "timeout"
        if "daily cap" in html_lower:
            return "daily_cap"
        return "connection_error"
    if result.status == 403:
        return "blocked"
    if result.status == 404:
        return "not_found"
    if result.status == 429:
        return "rate_limited"
    if result.status >= 500:
        return "server_error"
    return f"http_{result.status}"


def _update_lifecycle(db: TrackingDB, scraped: ScrapedMatch) -> None:
    if scraped.status == "finished" and _finished_match_complete(scraped):
        db.mark_lifecycle(scraped.hltv_id, status=scraped.status, final=True)
        return
    if scraped.status == "finished":
        db.defer_match(scraped.hltv_id, status="finished_incomplete", delay_seconds=INCOMPLETE_FINISHED_REFRESH_SECONDS)
        return
    if scraped.status == "live":
        db.defer_match(scraped.hltv_id, status=scraped.status, delay_seconds=LIVE_REFRESH_SECONDS)
        return
    db.defer_match(scraped.hltv_id, status=scraped.status, delay_seconds=SCHEDULED_REFRESH_SECONDS)


def _finished_match_complete(scraped: ScrapedMatch) -> bool:
    if not scraped.maps:
        return False
    maps_with_stats_ids = [item for item in scraped.maps if item.map_stats_id]
    if not maps_with_stats_ids:
        return True
    return all(item.player_stats for item in maps_with_stats_ids)


def _assemble_match(
    match_data: dict[str, Any],
    stat_players: list[dict[str, Any]],
    map_stats: dict[str, list[dict[str, Any]]],
) -> ScrapedMatch:
    players = tuple(
        ScrapedPlayer(
            hltv_id=str(row.get("hltv_id")),
            nickname=str(row.get("nickname") or row.get("hltv_id")),
            team_hltv_id=str(row.get("team_hltv_id") or ""),
        )
        for row in (match_data.get("players") or stat_players)
    )
    maps = []
    for row in match_data.get("maps", []):
        stats_id = row.get("map_stats_id")
        stats = tuple(_player_stat(item) for item in map_stats.get(str(stats_id), [])) if stats_id else ()
        maps.append(
            ScrapedMap(
                map_index=int(row["map_index"]),
                map_name=str(row["map_name"]),
                team_a_score=int(row["team_a_score"]),
                team_b_score=int(row["team_b_score"]),
                winner_hltv_id=str(row["winner_hltv_id"]),
                map_stats_id=str(stats_id) if stats_id else None,
                team_a_first_half=row.get("team_a_first_half"),
                team_b_first_half=row.get("team_b_first_half"),
                team_a_second_half=row.get("team_a_second_half"),
                team_b_second_half=row.get("team_b_second_half"),
                overtime=bool(row.get("overtime", False)),
                player_stats=stats,
            )
        )
    return ScrapedMatch(
        hltv_id=str(match_data["hltv_id"]),
        scheduled_at=datetime.fromisoformat(str(match_data["scheduled_at"]).replace("Z", "+00:00")),
        best_of=int(match_data["best_of"]),
        status=str(match_data["status"]),
        team_a=ScrapedTeam(**match_data["team_a"]),
        team_b=ScrapedTeam(**match_data["team_b"]),
        event=ScrapedEvent(**match_data["event"]),
        players=players,
        maps=tuple(maps),
        vetoes=tuple(ScrapedVeto(**row) for row in match_data.get("vetoes", [])),
        stats_url=match_data.get("stats_url"),
        match_stage=match_data.get("match_stage"),
        head_to_head=match_data.get("head_to_head"),
    )


def _apply_queue_metadata(match_data: dict[str, Any], queue_row: dict[str, Any] | None, config: ScraperConfig) -> None:
    event = match_data.get("event")
    if not isinstance(event, dict):
        return
    if queue_row:
        if not event.get("name") or event.get("name") == "Unknown Event":
            event["name"] = queue_row.get("event_name") or event.get("name")
        if event.get("stars") is None and queue_row.get("event_stars") is not None:
            event["stars"] = int(queue_row["event_stars"])
        if queue_row.get("priority_tier") is not None and int(queue_row["priority_tier"]) < 9:
            event["priority_tier"] = int(queue_row["priority_tier"])
    if event.get("priority_tier") is None:
        event["priority_tier"] = _priority_from_event(str(event.get("name") or ""), event.get("stars"), config)


def _priority_from_event(event_name: str, stars: Any, config: ScraperConfig) -> int | None:
    lowered = event_name.lower()
    for pattern, tier in config.event_tier_overrides.items():
        if pattern.lower() in lowered:
            return int(tier)
    try:
        return max(1, 6 - int(stars)) if stars is not None else None
    except (TypeError, ValueError):
        return None


def _player_stat(row: dict[str, Any]) -> ScrapedPlayerMapStats:
    cells = row.get("cells") if isinstance(row.get("cells"), list) else []
    kills, deaths = _kills_deaths(cells)
    return ScrapedPlayerMapStats(
        player_hltv_id=str(row.get("player_hltv_id") or ""),
        nickname=str(row.get("nickname") or ""),
        team_hltv_id=str(row.get("team_hltv_id") or ""),
        kills=kills,
        deaths=deaths,
        assists=_assist_value(cells),
        adr=_first_float(cells, minimum=20.0, maximum=200.0),
        rating=_last_float(cells, minimum=0.0, maximum=3.0),
        headshot_pct=_percent_near(cells, "hs"),
        kast_pct=_first_percent(cells),
        first_kills=_labeled_int(cells, "fk"),
        first_deaths=_labeled_int(cells, "fd"),
        ct_kills=_safe_int(row.get("ct_kills")),
        ct_deaths=_safe_int(row.get("ct_deaths")),
        t_kills=_safe_int(row.get("t_kills")),
        t_deaths=_safe_int(row.get("t_deaths")),
        clutches_won=_labeled_int(cells, "clutch") or _labeled_int(cells, "1v"),
    )


def _kills_deaths(cells: list[Any]) -> tuple[int | None, int | None]:
    if len(cells) <= 1:
        return None, None
    combined = str(cells[1])
    match = re.search(r"(\d+)\s*[-/]\s*(\d+)", combined)
    if match:
        return int(match.group(1)), int(match.group(2))
    return _int_cell(cells, 1), _int_cell(cells, 2)


def _int_cell(cells: list[Any], index: int) -> int | None:
    if index >= len(cells):
        return None
    try:
        return int(str(cells[index]).strip().split()[0])
    except (ValueError, IndexError):
        return None


def _assist_value(cells: list[Any]) -> int | None:
    if len(cells) <= 2:
        return None
    if re.search(r"(\d+)\s*[-/]\s*(\d+)", str(cells[1])):
        return _int_cell(cells, 2)
    return _int_cell(cells, 3) if len(cells) > 3 else None


def _first_float(cells: list[Any], minimum: float, maximum: float) -> float | None:
    for cell in cells[2:]:
        value = _float_value(cell)
        if value is not None and minimum <= value <= maximum and "%" not in str(cell):
            return value
    return None


def _last_float(cells: list[Any], minimum: float, maximum: float) -> float | None:
    for cell in reversed(cells):
        value = _float_value(cell)
        if value is not None and minimum <= value <= maximum:
            return value
    return None


def _first_percent(cells: list[Any]) -> float | None:
    for cell in cells:
        text = str(cell)
        if "%" in text:
            value = _float_value(text)
            if value is not None:
                return value
    return None


def _percent_near(cells: list[Any], label: str) -> float | None:
    for cell in cells:
        text = str(cell).lower()
        if label in text and "%" in text:
            return _float_value(text)
    return None


def _labeled_int(cells: list[Any], label: str) -> int | None:
    for cell in cells:
        text = str(cell).lower()
        if label in text:
            value = _float_value(text)
            return int(value) if value is not None else None
    return None


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_value(value: Any) -> float | None:
    import re

    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None
