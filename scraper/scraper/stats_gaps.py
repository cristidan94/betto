from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.tracking_db import TrackingDB


def collect_stats_gaps(config: ScraperConfig | None = None, limit: int = 100) -> dict[str, Any]:
    if config is None:
        config = load_config()
    gaps: list[dict[str, Any]] = []
    for path in _fixture_files(config.output_dir):
        if len(gaps) >= limit:
            break
        payload = _read_json(path)
        if payload is None:
            continue
        gap = _gap_row(path, payload)
        if gap:
            gaps.append(gap)
    return {"total_sampled": len(gaps), "matches": gaps}


def retry_stats_gaps(config: ScraperConfig | None = None, limit: int = 100) -> dict[str, Any]:
    if config is None:
        config = load_config()
    gaps = collect_stats_gaps(config, limit=limit)["matches"]
    match_ids = [row["match_id"] for row in gaps]
    db = TrackingDB(config.db_path)
    try:
        queued = db.requeue_matches(match_ids, status="stats_gap")
    finally:
        db.close()
    return {"queued_for_retry": queued, "matches": match_ids}


def stats_error_summary(config: ScraperConfig | None = None, limit: int = 200) -> dict[str, Any]:
    if config is None:
        config = load_config()
    db = TrackingDB(config.db_path)
    try:
        rows = db._conn.execute(
            "SELECT match_id, stats_error FROM scrape_queue WHERE stats_error IS NOT NULL ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        db.close()
    by_category: dict[str, int] = {}
    matches: list[dict[str, str]] = []
    for row in rows:
        match_id = row["match_id"]
        error = row["stats_error"]
        matches.append({"match_id": match_id, "stats_error": error})
        for part in error.split("; "):
            category = part.split(":")[-1] if ":" in part else part
            by_category[category] = by_category.get(category, 0) + 1
    return {"total": len(matches), "by_category": dict(sorted(by_category.items(), key=lambda x: -x[1])), "matches": matches}


def _gap_row(path: Path, payload: dict[str, Any]) -> dict[str, Any] | None:
    maps = payload.get("maps") if isinstance(payload.get("maps"), list) else []
    if payload.get("status") != "finished" or not maps:
        return None
    maps_with_stats = sum(1 for item in maps if _has_player_stats(item))
    if maps_with_stats >= len(maps):
        return None
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    return {
        "match_id": str(payload.get("hltv_id") or path.stem),
        "file": str(path),
        "event": (payload.get("event") or {}).get("name") if isinstance(payload.get("event"), dict) else None,
        "team_a": _team_name(payload, "team_a"),
        "team_b": _team_name(payload, "team_b"),
        "maps": len(maps),
        "maps_with_player_stats": maps_with_stats,
        "stats_url": source.get("stats_url"),
        "reason": "missing_map_player_stats",
    }


def _has_player_stats(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    stats = item.get("player_stats")
    return isinstance(stats, dict) and any(stats.values())


def _team_name(payload: dict[str, Any], key: str) -> str | None:
    team = payload.get(key)
    if not isinstance(team, dict):
        return None
    return str(team.get("name") or "")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _fixture_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and item.name != "manifest.json")
