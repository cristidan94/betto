from __future__ import annotations

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
    stats_data: dict[str, Any] = {}
    if match_data.get("stats_url"):
        limiter.sleep()
        stats_result = fetcher.fetch(match_data["stats_url"])
        if stats_result.ok:
            fetcher._save_raw(match_id, "stats.html", stats_result.html)
            stats_data = parse_stats_page(stats_result.html)
            db.mark_stats_fetched(match_id)

    map_stats: dict[str, list[dict[str, Any]]] = {}
    db.set_maps_total(match_id, len(match_data.get("maps", [])))
    for item in match_data.get("maps", []):
        map_stats_id = item.get("map_stats_id")
        if not map_stats_id:
            continue
        limiter.sleep()
        map_result = fetcher.fetch(f"https://www.hltv.org/stats/matches/mapstatsid/{map_stats_id}/slug")
        if map_result.ok:
            fetcher._save_raw(match_id, f"map_{map_stats_id}.html", map_result.html)
            map_stats[map_stats_id] = parse_map_stats_page(map_result.html)
            db.increment_maps_fetched(match_id)

    scraped = _assemble_match(match_data, stats_data.get("players", []), map_stats)
    write_fixture_json(scraped, config.output_dir)
    db.mark_parsed(match_id)
    return scraped


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
    )


def _player_stat(row: dict[str, Any]) -> ScrapedPlayerMapStats:
    cells = row.get("cells") if isinstance(row.get("cells"), list) else []
    return ScrapedPlayerMapStats(
        player_hltv_id=str(row.get("player_hltv_id") or ""),
        nickname=str(row.get("nickname") or ""),
        team_hltv_id=str(row.get("team_hltv_id") or ""),
        kills=_int_cell(cells, 1),
        deaths=_int_cell(cells, 2),
    )


def _int_cell(cells: list[Any], index: int) -> int | None:
    if index >= len(cells):
        return None
    try:
        return int(str(cells[index]).strip().split()[0])
    except (ValueError, IndexError):
        return None
