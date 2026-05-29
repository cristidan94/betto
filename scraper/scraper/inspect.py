from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.tracking_db import TrackingDB


def show_match(match_id: str, config: ScraperConfig | None = None) -> dict[str, Any]:
    if config is None:
        config = load_config()
    db = TrackingDB(config.db_path)
    try:
        queue_row = db.get_match(match_id)
    finally:
        db.close()
    fixture_path = config.output_dir / f"{match_id}.json"
    fixture = _read_json(fixture_path)
    raw_dir = config.raw_dir / "matches" / match_id
    return {
        "match_id": match_id,
        "queue": queue_row,
        "fixture": _fixture_summary(fixture_path, fixture),
        "raw": _raw_summary(raw_dir),
    }


def _fixture_summary(path: Path, payload: dict[str, Any] | None) -> dict[str, Any]:
    if payload is None:
        return {"exists": path.exists(), "path": str(path)}
    maps = payload.get("maps") if isinstance(payload.get("maps"), list) else []
    return {
        "exists": True,
        "path": str(path),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "scheduled_at": payload.get("scheduled_at"),
        "team_a": _team_name(payload, "team_a"),
        "team_b": _team_name(payload, "team_b"),
        "event": payload.get("event"),
        "maps": len(maps),
        "vetoes": len(payload.get("vetoes") or []),
        "players": len(payload.get("players") or []),
        "maps_with_player_stats": sum(1 for item in maps if _has_player_stats(item)),
        "source": payload.get("source"),
    }


def _raw_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path), "files": []}
    files = sorted(item for item in path.glob("*") if item.is_file())
    return {
        "exists": True,
        "path": str(path),
        "files": [{"name": item.name, "bytes": item.stat().st_size} for item in files],
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _team_name(payload: dict[str, Any], key: str) -> str | None:
    team = payload.get(key)
    if not isinstance(team, dict):
        return None
    return str(team.get("name") or "")


def _has_player_stats(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    stats = item.get("player_stats")
    return isinstance(stats, dict) and any(stats.values())
