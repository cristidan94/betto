from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from scraper.backfill import BACKFILL_COMPLETED_AT, BACKFILL_DONE, BACKFILL_EMPTY_PAGES, BACKFILL_NEXT_PAGE, BACKFILL_STARTED_AT
from scraper.config import ScraperConfig, load_config
from scraper.tracking_db import TrackingDB


def collect_status(config: ScraperConfig | None = None, recent_limit: int = 10) -> dict[str, Any]:
    if config is None:
        config = load_config()
    db = TrackingDB(config.db_path)
    try:
        return {
            "queue": db.queue_stats(),
            "backfill": {
                "next_page": db.get_int_state(BACKFILL_NEXT_PAGE, config.backfill_start_page),
                "next_offset": db.get_int_state(BACKFILL_NEXT_PAGE, config.backfill_start_page) * 100,
                "empty_pages": db.get_int_state(BACKFILL_EMPTY_PAGES, 0),
                "done": db.get_state(BACKFILL_DONE, "0") == "1",
                "started_at": db.get_state(BACKFILL_STARTED_AT),
                "completed_at": db.get_state(BACKFILL_COMPLETED_AT),
                "max_page": config.backfill_max_page,
                "stop_date": config.backfill_stop_date,
            },
            "lifecycle": _lifecycle_counts(config.db_path),
            "requests": {
                "today": db.request_count_today(),
                "recent": _recent_requests(config.db_path, recent_limit),
            },
            "files": {
                "parsed_json": _count_files(config.output_dir, "*.json"),
                "raw_match_dirs": _count_dirs(config.raw_dir / "matches"),
                "latest_json": _latest_files(config.output_dir, "*.json", 5),
                "latest_backups": _latest_files(Path("backups"), "*.tar.gz", 5),
            },
        }
    finally:
        db.close()


def _lifecycle_counts(db_path: Path) -> dict[str, int]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT COALESCE(lifecycle_status, 'unknown') AS status, COUNT(*) AS count
            FROM scrape_queue
            GROUP BY COALESCE(lifecycle_status, 'unknown')
            ORDER BY count DESC, status ASC
            """
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
    finally:
        con.close()


def _recent_requests(db_path: Path, limit: int) -> list[dict[str, Any]]:
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT requested_at, status, fetcher_type, proxy_region, content_bytes, elapsed_ms, url
            FROM request_log
            ORDER BY request_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def _count_files(path: Path, pattern: str) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.glob(pattern) if item.is_file())


def _count_dirs(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.iterdir() if item.is_dir())


def _latest_files(path: Path, pattern: str, limit: int) -> list[str]:
    if not path.exists():
        return []
    items = sorted((item for item in path.glob(pattern) if item.is_file()), key=lambda item: item.stat().st_mtime, reverse=True)
    return [str(item) for item in items[:limit]]
