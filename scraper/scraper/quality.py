from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.tracking_db import TrackingDB


def collect_quality_report(config: ScraperConfig | None = None, sample_limit: int = 10) -> dict[str, Any]:
    if config is None:
        config = load_config()
    files = _fixture_files(config.output_dir)
    counters: Counter[str] = Counter()
    warnings: list[dict[str, Any]] = []
    earliest: str | None = None
    latest: str | None = None

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            counters["invalid_json"] += 1
            if len(warnings) < sample_limit:
                warnings.append({"file": str(path), "issue": "invalid_json", "detail": str(exc)})
            continue

        counters["matches"] += 1
        status = str(payload.get("status") or "unknown")
        counters[f"status_{status}"] += 1
        scheduled_at = payload.get("scheduled_at")
        if isinstance(scheduled_at, str):
            earliest = scheduled_at if earliest is None else min(earliest, scheduled_at)
            latest = scheduled_at if latest is None else max(latest, scheduled_at)
        tier = _event_tier(payload)
        if tier is not None:
            counters[f"tier_{tier}"] += 1
        _count_match_quality(payload, counters)
        for issue in _match_warnings(path, payload):
            counters[f"warning_{issue['issue']}"] += 1
            if len(warnings) < sample_limit:
                warnings.append(issue)

    db = TrackingDB(config.db_path)
    try:
        queue = db.queue_stats()
    finally:
        db.close()

    return {
        "score": _score(counters, queue),
        "queue": queue,
        "coverage": {
            "json_files": len(files),
            "matches": counters["matches"],
            "finished": counters["status_finished"],
            "live": counters["status_live"],
            "scheduled": counters["status_scheduled"],
            "with_maps": counters["with_maps"],
            "with_vetoes": counters["with_vetoes"],
            "with_players": counters["with_players"],
            "with_player_stats": counters["with_player_stats"],
            "with_stats_url": counters["with_stats_url"],
            "tier_1": counters["tier_1"],
            "tier_2": counters["tier_2"],
            "earliest_scheduled_at": earliest,
            "latest_scheduled_at": latest,
        },
        "warnings": {
            "total": sum(value for key, value in counters.items() if key.startswith("warning_")),
            "by_type": {
                key.removeprefix("warning_"): value
                for key, value in sorted(counters.items())
                if key.startswith("warning_")
            },
            "sample": warnings,
        },
    }


def _count_match_quality(payload: dict[str, Any], counters: Counter[str]) -> None:
    maps = payload.get("maps") if isinstance(payload.get("maps"), list) else []
    vetoes = payload.get("vetoes") if isinstance(payload.get("vetoes"), list) else []
    players = payload.get("players") if isinstance(payload.get("players"), list) else []
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    if maps:
        counters["with_maps"] += 1
    if vetoes:
        counters["with_vetoes"] += 1
    if players:
        counters["with_players"] += 1
    if source.get("stats_url"):
        counters["with_stats_url"] += 1
    if any(_map_has_player_stats(item) for item in maps):
        counters["with_player_stats"] += 1


def _match_warnings(path: Path, payload: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    match_id = payload.get("hltv_id") or path.stem
    if not payload.get("scheduled_at"):
        issues.append(_issue(path, match_id, "missing_scheduled_at"))
    if not _team_name(payload, "team_a") or not _team_name(payload, "team_b"):
        issues.append(_issue(path, match_id, "missing_team"))
    maps = payload.get("maps") if isinstance(payload.get("maps"), list) else []
    if payload.get("status") == "finished" and not maps:
        issues.append(_issue(path, match_id, "finished_without_maps"))
    if maps and not any(_map_has_player_stats(item) for item in maps):
        issues.append(_issue(path, match_id, "maps_without_player_stats"))
    players = payload.get("players") if isinstance(payload.get("players"), list) else []
    if payload.get("status") == "finished" and len(players) not in {0, 10}:
        issues.append(_issue(path, match_id, "unexpected_player_count", count=len(players)))
    return issues


def _map_has_player_stats(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    stats = item.get("player_stats")
    return isinstance(stats, dict) and any(stats.values())


def _team_name(payload: dict[str, Any], key: str) -> str:
    team = payload.get(key)
    if not isinstance(team, dict):
        return ""
    return str(team.get("name") or "")


def _event_tier(payload: dict[str, Any]) -> str | None:
    event = payload.get("event")
    if not isinstance(event, dict):
        return None
    value = event.get("tier")
    return str(value) if value is not None else None


def _issue(path: Path, match_id: Any, issue: str, **extra: Any) -> dict[str, Any]:
    return {"file": str(path), "match_id": str(match_id), "issue": issue, **extra}


def _score(counters: Counter[str], queue: dict[str, int]) -> float:
    matches = max(counters["matches"], 1)
    final_ratio = queue.get("final", 0) / max(queue.get("total", 0), 1)
    map_ratio = counters["with_maps"] / matches
    player_ratio = counters["with_players"] / matches
    stats_ratio = counters["with_player_stats"] / matches
    warning_penalty = min(0.25, counters["invalid_json"] / matches + (sum(v for k, v in counters.items() if k.startswith("warning_")) / matches) * 0.05)
    return round(max(0.0, min(1.0, 0.35 * final_ratio + 0.3 * map_ratio + 0.2 * player_ratio + 0.15 * stats_ratio - warning_penalty)), 4)


def _fixture_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and item.name != "manifest.json")
