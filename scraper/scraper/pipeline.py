from __future__ import annotations

import logging
import time

from scraper.config import ScraperConfig, load_config
from scraper.discovery import discover_matches
from scraper.fetcher import HltvFetcher
from scraper.match_scraper import scrape_one_match
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)


def run_pipeline(config: ScraperConfig | None = None, max_discovery_pages: int = 10, max_matches: int = 100) -> dict:
    if config is None:
        config = load_config()
    proxy = ProxyRotator(config.proxy_url, config.proxy_regions)
    limiter = RateLimiter(
        min_delay=config.min_delay,
        max_delay=config.max_delay,
        cooldown_every=config.cooldown_every,
        cooldown_seconds=config.cooldown_seconds,
        daily_cap=config.daily_cap,
        quiet_hours_start=config.quiet_hours_start,
        quiet_hours_end=config.quiet_hours_end,
    )
    db = TrackingDB(config.db_path)
    requests_today = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    limiter.request_count = requests_today
    try:
        if limiter.in_quiet_hours():
            return {"skipped": True, "reason": "quiet_hours"}
        if limiter.daily_cap_reached():
            return {"skipped": True, "reason": "daily_cap"}
        discovered = discover_matches(fetcher, db, config, max_pages=max_discovery_pages)
        fetched = 0
        for row in db.pending_matches(limit=max_matches):
            if limiter.daily_cap_reached():
                break
            backoff = limiter.failure_backoff_delay()
            if backoff:
                _logger.warning("failure backoff: pausing %.0fs", backoff)
                time.sleep(backoff)
            proxy.start_sticky_session()
            try:
                result = scrape_one_match(row["match_id"], row["match_url"], fetcher, db, limiter, config)
                if result:
                    fetched += 1
            finally:
                proxy.end_sticky_session()
        return {"discovered": discovered, "fetched": fetched, "queue": db.queue_stats()}
    finally:
        fetcher.close()
        db.close()
