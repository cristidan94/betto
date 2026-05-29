from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.parser import parse_event_page, parse_player_page, parse_team_page
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

log = logging.getLogger(__name__)


def scrape_events(
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
    config: ScraperConfig,
    event_ids: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if event_ids is None:
        event_ids = _collect_event_ids(config.output_dir, limit=limit)
    out_dir = config.raw_dir / "events"
    scraped = 0
    skipped = 0
    errors = 0
    for event_id in event_ids:
        if limiter.daily_cap_reached():
            break
        json_path = out_dir / f"{event_id}.json"
        if json_path.exists():
            skipped += 1
            continue
        limiter.sleep()
        result = fetcher.fetch(f"https://www.hltv.org/events/{event_id}/slug")
        if not result.ok:
            log.warning("event %s fetch failed: %s", event_id, result.status)
            errors += 1
            continue
        _save_raw(config.raw_dir, "events", event_id, "event.html", result.html)
        data = parse_event_page(result.html, event_id)
        _write_json(out_dir, event_id, data)
        scraped += 1
    return {"scraped": scraped, "skipped": skipped, "errors": errors, "total_ids": len(event_ids)}


def scrape_teams(
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
    config: ScraperConfig,
    team_ids: list[str] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    if team_ids is None:
        team_ids = _collect_team_ids(config.output_dir, limit=limit)
    out_dir = config.raw_dir / "teams"
    scraped = 0
    skipped = 0
    errors = 0
    for team_id in team_ids:
        if limiter.daily_cap_reached():
            break
        json_path = out_dir / f"{team_id}.json"
        if json_path.exists():
            skipped += 1
            continue
        limiter.sleep()
        result = fetcher.fetch(f"https://www.hltv.org/team/{team_id}/slug")
        if not result.ok:
            log.warning("team %s fetch failed: %s", team_id, result.status)
            errors += 1
            continue
        _save_raw(config.raw_dir, "teams", team_id, "team.html", result.html)
        data = parse_team_page(result.html, team_id)
        _write_json(out_dir, team_id, data)
        scraped += 1
    return {"scraped": scraped, "skipped": skipped, "errors": errors, "total_ids": len(team_ids)}


def scrape_players(
    fetcher: HltvFetcher,
    db: TrackingDB,
    limiter: RateLimiter,
    config: ScraperConfig,
    player_ids: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    if player_ids is None:
        player_ids = _collect_player_ids(config.output_dir, limit=limit)
    out_dir = config.raw_dir / "players"
    scraped = 0
    skipped = 0
    errors = 0
    for player_id in player_ids:
        if limiter.daily_cap_reached():
            break
        json_path = out_dir / f"{player_id}.json"
        if json_path.exists():
            skipped += 1
            continue
        limiter.sleep()
        result = fetcher.fetch(f"https://www.hltv.org/player/{player_id}/slug")
        if not result.ok:
            log.warning("player %s fetch failed: %s", player_id, result.status)
            errors += 1
            continue
        _save_raw(config.raw_dir, "players", player_id, "player.html", result.html)
        data = parse_player_page(result.html, player_id)
        _write_json(out_dir, player_id, data)
        scraped += 1
    return {"scraped": scraped, "skipped": skipped, "errors": errors, "total_ids": len(player_ids)}


def _collect_event_ids(output_dir: Path, limit: int = 50) -> list[str]:
    ids: set[str] = set()
    for path in _fixture_files(output_dir):
        if len(ids) >= limit:
            break
        data = _read_json(path)
        if data is None:
            continue
        event = data.get("event")
        if isinstance(event, dict) and event.get("hltv_id"):
            eid = str(event["hltv_id"])
            if eid != "unknown":
                ids.add(eid)
    return sorted(ids)


def _collect_team_ids(output_dir: Path, limit: int = 50) -> list[str]:
    ids: set[str] = set()
    for path in _fixture_files(output_dir):
        if len(ids) >= limit:
            break
        data = _read_json(path)
        if data is None:
            continue
        for key in ("team_a", "team_b"):
            team = data.get(key)
            if isinstance(team, dict) and team.get("hltv_id"):
                tid = str(team["hltv_id"])
                if tid not in ("unknown-a", "unknown-b"):
                    ids.add(tid)
    return sorted(ids)


def _collect_player_ids(output_dir: Path, limit: int = 100) -> list[str]:
    ids: set[str] = set()
    for path in _fixture_files(output_dir):
        if len(ids) >= limit:
            break
        data = _read_json(path)
        if data is None:
            continue
        players = data.get("players")
        if isinstance(players, list):
            for player in players:
                if isinstance(player, dict) and player.get("hltv_id"):
                    ids.add(str(player["hltv_id"]))
    return sorted(ids)


def _fixture_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and item.name != "manifest.json")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_raw(raw_dir: Path, entity_type: str, entity_id: str, filename: str, html: str) -> None:
    directory = raw_dir / entity_type / entity_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(html, encoding="utf-8")


def _write_json(out_dir: Path, entity_id: str, data: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{entity_id}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path
