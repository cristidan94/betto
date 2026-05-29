from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.models import SCHEMA_VERSION

VALID_MAPS = {"Ancient", "Anubis", "Cache", "Cobblestone", "Dust2", "Inferno", "Mirage", "Nuke", "Overpass", "Train", "Vertigo"}


def validate_fixtures(config: ScraperConfig | None = None, sample_limit: int = 25) -> dict[str, Any]:
    if config is None:
        config = load_config()
    files = _fixture_files(config.output_dir)
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _append(errors, sample_limit, path, "invalid_json", str(exc))
            continue
        _validate_fixture(path, payload, errors, warnings, sample_limit)
    return {
        "ok": not errors,
        "training_safe": not errors,
        "files": len(files),
        "errors": {"total": _count_all(errors), "sample": errors},
        "warnings": {"total": _count_all(warnings), "sample": warnings},
    }


def _validate_fixture(
    path: Path,
    payload: dict[str, Any],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    sample_limit: int,
) -> None:
    match_id = str(payload.get("hltv_id") or path.stem)
    if payload.get("schema_version") != SCHEMA_VERSION:
        _append(errors, sample_limit, path, "schema_version_mismatch", match_id=match_id, expected=SCHEMA_VERSION)
    if not _valid_datetime(payload.get("scheduled_at")):
        _append(errors, sample_limit, path, "invalid_scheduled_at", match_id=match_id)
    if int(payload.get("best_of") or 0) <= 0:
        _append(errors, sample_limit, path, "invalid_best_of", match_id=match_id)
    for key in ("team_a", "team_b", "event"):
        if not isinstance(payload.get(key), dict):
            _append(errors, sample_limit, path, f"missing_{key}", match_id=match_id)
    if not _team_name(payload, "team_a") or not _team_name(payload, "team_b"):
        _append(errors, sample_limit, path, "missing_team_name", match_id=match_id)
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    if event.get("tier") is None:
        _append(warnings, sample_limit, path, "missing_event_tier", match_id=match_id)
    maps = payload.get("maps") if isinstance(payload.get("maps"), list) else []
    if payload.get("status") == "finished" and not maps:
        _append(errors, sample_limit, path, "finished_without_maps", match_id=match_id)
    if maps and int(payload.get("best_of") or 0) < len(maps):
        _append(warnings, sample_limit, path, "map_count_exceeds_best_of", match_id=match_id)
    for item in maps:
        _validate_map(path, match_id, item, errors, warnings, sample_limit)
    players = payload.get("players") if isinstance(payload.get("players"), list) else []
    if payload.get("status") == "finished" and len(players) not in {0, 10}:
        _append(warnings, sample_limit, path, "unexpected_player_count", match_id=match_id, count=len(players))


def _validate_map(
    path: Path,
    match_id: str,
    item: Any,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    sample_limit: int,
) -> None:
    if not isinstance(item, dict):
        _append(errors, sample_limit, path, "invalid_map", match_id=match_id)
        return
    map_name = str(item.get("map_name") or "")
    if map_name not in VALID_MAPS:
        _append(warnings, sample_limit, path, "unknown_map_name", match_id=match_id, map_name=map_name)
    score_a = _int_or_none(item.get("team_a_score"))
    score_b = _int_or_none(item.get("team_b_score"))
    if score_a is None or score_b is None or score_a < 0 or score_b < 0:
        _append(errors, sample_limit, path, "invalid_map_score", match_id=match_id, map_name=map_name)
    if score_a is not None and score_b is not None and score_a == score_b:
        _append(errors, sample_limit, path, "tied_finished_map", match_id=match_id, map_name=map_name)
    stats = item.get("player_stats")
    if isinstance(stats, dict) and stats and len(stats) not in {10, 12}:
        _append(warnings, sample_limit, path, "unexpected_map_player_stats_count", match_id=match_id, map_name=map_name, count=len(stats))


def _append(target: list[dict[str, Any]], limit: int, path: Path, issue: str, detail: str | None = None, **extra: Any) -> None:
    if len(target) >= limit:
        return
    row = {"file": str(path), "issue": issue, **extra}
    if detail:
        row["detail"] = detail
    target.append(row)


def _count_all(rows: list[dict[str, Any]]) -> int:
    return len(rows)


def _team_name(payload: dict[str, Any], key: str) -> str:
    team = payload.get(key)
    if not isinstance(team, dict):
        return ""
    return str(team.get("name") or "")


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _fixture_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and item.name != "manifest.json")
