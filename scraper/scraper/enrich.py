from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.parser import parse_stats_map_detailed
from scraper.unblocker import fetch_via_unblocker, unblocker_configured

_logger = logging.getLogger(__name__)

# Fields the /stats/ page adds on top of the embedded match-page scoreboard.
_DETAIL_FIELDS = (
    "first_kills",
    "first_deaths",
    "hs_kills",
    "multi_kills",
    "flash_assists",
    "trade_deaths",
    "clutches_won",
    "headshot_pct",
)


def enrich_stats(
    config: ScraperConfig | None = None,
    max_tier: int = 1,
    limit: int = 50,
    min_delay: float = 2.0,
) -> dict[str, Any]:
    """Fetch the detailed /stats/ page (via unblocker) for finished tier<=max_tier
    matches and merge the granular fields into existing fixtures. `limit` caps the
    number of /stats/ (map) requests so trial budgets stay bounded."""
    if config is None:
        config = load_config()
    if not unblocker_configured(config):
        return {"error": "unblocker_not_configured", "enriched_maps": 0}

    fetched = enriched_maps = enriched_matches = failed = 0
    for path in sorted(config.output_dir.glob("*.json")):
        if fetched >= limit:
            break
        if path.name == "manifest.json":
            continue
        payload = _read_json(path)
        if not _is_candidate(payload, max_tier):
            continue
        slug = _team_slug(payload)
        match_enriched = False
        for map_obj in payload["maps"]:
            if fetched >= limit:
                break
            stats_id = map_obj.get("map_stats_id")
            if not stats_id or _already_enriched(map_obj):
                continue
            url = f"https://www.hltv.org/stats/matches/mapstatsid/{stats_id}/{slug}"
            time.sleep(min_delay)
            ok, html = fetch_via_unblocker(url, config)
            fetched += 1
            if not ok or not html:
                failed += 1
                _logger.warning("enrich: failed stats fetch for map %s (match %s)", stats_id, payload.get("hltv_id"))
                continue
            rows = parse_stats_map_detailed(html)
            if _merge_rows(map_obj, rows):
                enriched_maps += 1
                match_enriched = True
        if match_enriched:
            path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            enriched_matches += 1
    return {
        "stats_requests": fetched,
        "enriched_maps": enriched_maps,
        "enriched_matches": enriched_matches,
        "failed_requests": failed,
        "limit": limit,
        "max_tier": max_tier,
    }


def _is_candidate(payload: dict[str, Any] | None, max_tier: int) -> bool:
    if not payload or payload.get("status") != "finished":
        return False
    event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    tier = event.get("tier")
    if tier is None or int(tier) > max_tier:
        return False
    maps = payload.get("maps")
    if not isinstance(maps, list) or not maps:
        return False
    return any(m.get("map_stats_id") and not _already_enriched(m) for m in maps)


def _already_enriched(map_obj: dict[str, Any]) -> bool:
    stats = map_obj.get("player_stats")
    if not isinstance(stats, dict) or not stats:
        return False
    return any(isinstance(v, dict) and v.get("first_kills") is not None for v in stats.values())


def _merge_rows(map_obj: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    stats = map_obj.get("player_stats")
    if not isinstance(stats, dict) or not rows:
        return False
    by_nick = {str(k).lower(): v for k, v in stats.items() if isinstance(v, dict)}
    merged = False
    for row in rows:
        target = by_nick.get(str(row.get("nickname", "")).lower())
        if target is None:
            continue
        for field in _DETAIL_FIELDS:
            if row.get(field) is not None:
                target[field] = row[field]
        # Backfill core stats only if the embedded pass missed them.
        for field in ("adr", "kast_pct", "rating", "kills", "deaths", "assists"):
            if target.get(field) is None and row.get(field) is not None:
                target[field] = row[field]
        merged = True
    return merged


def _team_slug(payload: dict[str, Any]) -> str:
    a = _slug(payload.get("team_a", {}).get("name") if isinstance(payload.get("team_a"), dict) else None)
    b = _slug(payload.get("team_b", {}).get("name") if isinstance(payload.get("team_b"), dict) else None)
    return f"{a or 'team1'}-vs-{b or 'team2'}"


def _slug(name: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
