from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

from scraper.config import DEFAULT_TIER_OVERRIDES, EVENT_ALLOW_LIST


def load_tier_registry(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return _default_registry()
    if yaml is None:
        return _default_registry()
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return _default_registry()
    return _normalize(data)


def tier_overrides_from_registry(registry: dict[str, Any]) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for entry in registry.get("events", []):
        pattern = entry.get("pattern", "")
        tier = entry.get("tier")
        if pattern and isinstance(tier, int) and tier >= 1:
            overrides[pattern] = tier
    return overrides


def allow_list_from_registry(registry: dict[str, Any]) -> list[str]:
    raw = registry.get("allow_list", [])
    if isinstance(raw, list):
        return [str(item) for item in raw if item]
    return list(EVENT_ALLOW_LIST)


def describe_registry(registry: dict[str, Any]) -> dict[str, Any]:
    events = registry.get("events", [])
    overrides = tier_overrides_from_registry(registry)
    allow_list = allow_list_from_registry(registry)
    by_tier: dict[int, list[str]] = {}
    for entry in events:
        tier = entry.get("tier", 9)
        by_tier.setdefault(tier, []).append(entry.get("pattern", ""))
    return {
        "event_count": len(events),
        "allow_list_count": len(allow_list),
        "tier_overrides": overrides,
        "by_tier": {k: sorted(v) for k, v in sorted(by_tier.items())},
        "allow_list": allow_list,
    }


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    events = data.get("events", [])
    if not isinstance(events, list):
        events = []
    normalized_events = []
    for entry in events:
        if not isinstance(entry, dict):
            continue
        normalized_events.append({
            "pattern": str(entry.get("pattern", "")),
            "tier": int(entry["tier"]) if "tier" in entry and entry["tier"] is not None else 9,
            "tags": list(entry.get("tags", [])),
        })
    return {
        "events": normalized_events,
        "allow_list": data.get("allow_list", list(EVENT_ALLOW_LIST)),
    }


def _default_registry() -> dict[str, Any]:
    events = [{"pattern": pattern, "tier": tier, "tags": []} for pattern, tier in DEFAULT_TIER_OVERRIDES.items()]
    return {"events": events, "allow_list": list(EVENT_ALLOW_LIST)}
