from __future__ import annotations

import logging
import subprocess
import time

from scraper.alerts import send_webhook
from scraper.config import ScraperConfig, load_config
from scraper.discovery import discover_page
from scraper.fetcher import HltvFetcher
from scraper.match_scraper import scrape_one_match
from scraper.proxy import ProxyRotator
from scraper.rate_limiter import RateLimiter
from scraper.tracking_db import TrackingDB

_logger = logging.getLogger(__name__)

BACKFILL_NEXT_PAGE = "backfill_next_page"
BACKFILL_EMPTY_PAGES = "backfill_empty_pages"
BACKFILL_DONE = "backfill_done"
BACKFILL_STARTED_AT = "backfill_started_at"
BACKFILL_COMPLETED_AT = "backfill_completed_at"
BACKFILL_DONE_ALERTED = "backfill_done_alerted"


def run_backfill(
    config: ScraperConfig | None = None,
    pages_per_run: int | None = None,
    max_matches: int | None = None,
    empty_pages_to_stop: int | None = None,
    disable_timer_on_done: str | None = None,
) -> dict:
    if config is None:
        config = load_config()
    pages_per_run = pages_per_run if pages_per_run is not None else config.backfill_pages_per_run
    max_matches = max_matches if max_matches is not None else config.backfill_matches_per_run
    empty_pages_to_stop = empty_pages_to_stop if empty_pages_to_stop is not None else config.backfill_empty_pages_to_stop

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
    limiter.request_count = db.request_count_today()
    fetcher = HltvFetcher(proxy, limiter, db, config.raw_dir)
    try:
        if limiter.in_quiet_hours():
            return {"skipped": True, "reason": "quiet_hours"}
        if limiter.daily_cap_reached():
            return {"skipped": True, "reason": "daily_cap"}

        done = db.get_state(BACKFILL_DONE, "0") == "1"
        next_page = db.get_int_state(BACKFILL_NEXT_PAGE, config.backfill_start_page)
        empty_pages = db.get_int_state(BACKFILL_EMPTY_PAGES, 0)
        if db.get_state(BACKFILL_STARTED_AT) is None:
            db.set_state(BACKFILL_STARTED_AT, _utc_now())
        discovered = 0
        scanned = 0
        last_page = None

        while not done and scanned < pages_per_run and not limiter.daily_cap_reached():
            if config.backfill_max_page is not None and next_page > config.backfill_max_page:
                done = True
                db.set_state(BACKFILL_DONE, "1")
                db.set_state(BACKFILL_COMPLETED_AT, _utc_now())
                break
            page_result = discover_page(fetcher, db, config, next_page, limiter=limiter)
            if not page_result["ok"]:
                break
            scanned += 1
            last_page = next_page
            next_page += 1
            discovered += int(page_result["discovered"])
            if int(page_result["entries"]) == 0 or int(page_result["allowed"]) == 0:
                empty_pages += 1
            else:
                empty_pages = 0
            db.set_int_state(BACKFILL_NEXT_PAGE, next_page)
            db.set_int_state(BACKFILL_EMPTY_PAGES, empty_pages)
            if empty_pages >= empty_pages_to_stop:
                done = True
                db.set_state(BACKFILL_DONE, "1")
                db.set_state(BACKFILL_COMPLETED_AT, _utc_now())
                break
            if _past_stop_date(page_result.get("oldest_scheduled_at"), config.backfill_stop_date):
                done = True
                db.set_state(BACKFILL_DONE, "1")
                db.set_state(BACKFILL_COMPLETED_AT, _utc_now())
                break

        fetched = 0
        for row in db.pending_matches(limit=max_matches):
            if limiter.daily_cap_reached():
                break
            backoff = limiter.failure_backoff_delay()
            if backoff:
                _logger.warning("failure backoff: pausing %.0fs", backoff)
                time.sleep(backoff)
            result = scrape_one_match(row["match_id"], row["match_url"], fetcher, db, limiter, config)
            if result:
                fetched += 1

        queue = db.queue_stats()
        done = db.get_state(BACKFILL_DONE, "0") == "1"
        output = {
            "discovered": discovered,
            "fetched": fetched,
            "pages_scanned": scanned,
            "last_page": last_page,
            "next_page": db.get_int_state(BACKFILL_NEXT_PAGE, next_page),
            "empty_pages": db.get_int_state(BACKFILL_EMPTY_PAGES, empty_pages),
            "done": done,
            "queue": queue,
        }
        if disable_timer_on_done and done and queue.get("due", 0) == 0:
            output["timer_disabled"] = _disable_timer(disable_timer_on_done)
        if done and db.get_state(BACKFILL_DONE_ALERTED, "0") != "1":
            output["alert"] = send_webhook(config.alert_webhook_url, "HLTV backfill done", output)
            if output["alert"].get("sent") or output["alert"].get("reason") == "not_configured":
                db.set_state(BACKFILL_DONE_ALERTED, "1")
        return output
    finally:
        fetcher.close()
        db.close()


def _disable_timer(timer_name: str) -> bool:
    try:
        subprocess.run(["systemctl", "disable", "--now", timer_name], check=False)
    except OSError:
        return False
    return True


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _past_stop_date(scheduled_at: object, stop_date: str | None) -> bool:
    if not stop_date or scheduled_at is None:
        return False
    return str(scheduled_at)[:10] <= stop_date[:10]
