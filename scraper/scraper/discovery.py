from __future__ import annotations

from datetime import date, datetime

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.parser import parse_results_page
from scraper.tracking_db import TrackingDB


def discover_matches(fetcher: HltvFetcher, db: TrackingDB, config: ScraperConfig, max_pages: int = 10, start_page: int = 0) -> int:
    discovered = 0
    for page in range(start_page, start_page + max_pages):
        result = discover_page(fetcher, db, config, page)
        if not result["ok"]:
            continue
        discovered += int(result["discovered"])
    return discovered


def discover_page(fetcher: HltvFetcher, db: TrackingDB, config: ScraperConfig, page: int) -> dict[str, int | bool]:
    offset = page * 100
    result = fetcher.fetch(f"https://www.hltv.org/results?stars=4&stars=5&offset={offset}")
    if not result.ok:
        return {"ok": False, "page": page, "entries": 0, "allowed": 0, "discovered": 0}
    entries = parse_results_page(result.html)
    allowed = 0
    discovered = 0
    for entry in entries:
        event_name = entry.get("event_name") or ""
        if not _allowed(event_name, config.event_allow_list):
            continue
        if not _inside_stop_date(entry.get("scheduled_at"), config.backfill_stop_date):
            continue
        allowed += 1
        before = db.get_match(entry["match_id"])
        db.upsert_match(
            entry["match_id"],
            entry["match_url"],
            event_name=event_name,
            event_stars=entry.get("event_stars"),
            scheduled_at=entry.get("scheduled_at"),
            priority_tier=_priority(event_name, entry.get("event_stars"), config.event_tier_overrides),
        )
        if before is None:
            discovered += 1
    return {
        "ok": True,
        "page": page,
        "entries": len(entries),
        "allowed": allowed,
        "discovered": discovered,
        "oldest_scheduled_at": _oldest_scheduled_at(entries),
    }


def _allowed(event_name: str, allow_list: list[str]) -> bool:
    if not event_name:
        return True
    lowered = event_name.lower()
    return any(item.lower() in lowered for item in allow_list)


def _priority(event_name: str, stars: int | None, tier_overrides: dict[str, int] | None = None) -> int:
    if tier_overrides:
        lowered = event_name.lower()
        for pattern, tier in tier_overrides.items():
            if pattern.lower() in lowered:
                return tier
    if stars is None:
        return 5
    return max(1, 6 - stars)


def _inside_stop_date(scheduled_at: object, stop_date: str | None) -> bool:
    if not stop_date or scheduled_at is None:
        return True
    parsed = _date_value(str(scheduled_at))
    stop = _date_value(stop_date)
    if parsed is None or stop is None:
        return True
    return parsed >= stop


def _oldest_scheduled_at(entries: list[dict]) -> str | None:
    dates = [str(entry["scheduled_at"]) for entry in entries if entry.get("scheduled_at")]
    return min(dates) if dates else None


def _date_value(value: str) -> date | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
