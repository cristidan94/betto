from __future__ import annotations

from scraper.config import ScraperConfig
from scraper.fetcher import HltvFetcher
from scraper.parser import parse_results_page
from scraper.tracking_db import TrackingDB


def discover_matches(fetcher: HltvFetcher, db: TrackingDB, config: ScraperConfig, max_pages: int = 10) -> int:
    discovered = 0
    for page in range(max_pages):
        offset = page * 100
        result = fetcher.fetch(f"https://www.hltv.org/results?stars=4&stars=5&offset={offset}")
        if not result.ok:
            continue
        entries = parse_results_page(result.html)
        for entry in entries:
            event_name = entry.get("event_name") or ""
            if not _allowed(event_name, config.event_allow_list):
                continue
            before = db.get_match(entry["match_id"])
            db.upsert_match(
                entry["match_id"],
                entry["match_url"],
                event_name=event_name,
                event_stars=entry.get("event_stars"),
                scheduled_at=entry.get("scheduled_at"),
                priority_tier=_priority(entry.get("event_stars")),
            )
            if before is None:
                discovered += 1
    return discovered


def _allowed(event_name: str, allow_list: list[str]) -> bool:
    if not event_name:
        return True
    lowered = event_name.lower()
    return any(item.lower() in lowered for item in allow_list)


def _priority(stars: int | None) -> int:
    if stars is None:
        return 5
    return max(1, 6 - stars)
