from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TrackingDB:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        self._conn.close()

    def upsert_match(
        self,
        match_id: str,
        match_url: str,
        event_name: str | None = None,
        event_stars: int | None = None,
        scheduled_at: str | None = None,
        priority_tier: int = 9,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO scrape_queue
              (match_id, match_url, event_name, event_stars, scheduled_at, priority_tier, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(match_id) DO UPDATE SET
              match_url = excluded.match_url,
              event_name = COALESCE(excluded.event_name, scrape_queue.event_name),
              event_stars = COALESCE(excluded.event_stars, scrape_queue.event_stars),
              scheduled_at = COALESCE(excluded.scheduled_at, scrape_queue.scheduled_at),
              priority_tier = MIN(scrape_queue.priority_tier, excluded.priority_tier),
              updated_at = excluded.updated_at
            """,
            (match_id, match_url, event_name, event_stars, scheduled_at, priority_tier, _now()),
        )
        self._conn.commit()

    def get_match(self, match_id: str) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM scrape_queue WHERE match_id = ?", (match_id,)).fetchone()
        return dict(row) if row else None

    def mark_match_fetched(self, match_id: str) -> None:
        self._mark(match_id, "match_fetched")

    def mark_stats_fetched(self, match_id: str) -> None:
        self._mark(match_id, "stats_fetched")

    def set_maps_total(self, match_id: str, total: int) -> None:
        self._conn.execute("UPDATE scrape_queue SET maps_total = ?, updated_at = ? WHERE match_id = ?", (total, _now(), match_id))
        self._conn.commit()

    def increment_maps_fetched(self, match_id: str) -> None:
        self._conn.execute(
            "UPDATE scrape_queue SET maps_fetched = maps_fetched + 1, updated_at = ? WHERE match_id = ?",
            (_now(), match_id),
        )
        self._conn.commit()

    def mark_parsed(self, match_id: str) -> None:
        self._mark(match_id, "parsed")

    def pending_matches(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT * FROM scrape_queue
            WHERE parsed = 0
            ORDER BY priority_tier ASC, COALESCE(scheduled_at, '') ASC, retry_count ASC, match_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def record_error(self, match_id: str, error: str) -> None:
        self._conn.execute(
            """
            UPDATE scrape_queue
            SET retry_count = retry_count + 1, last_error = ?, updated_at = ?
            WHERE match_id = ?
            """,
            (error, _now(), match_id),
        )
        self._conn.commit()

    def log_request(
        self,
        url: str,
        status: int,
        fetcher_type: str,
        proxy_region: str | None,
        content_bytes: int,
        elapsed_ms: int,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO request_log
              (requested_at, url, status, fetcher_type, proxy_region, content_bytes, elapsed_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (_now(), url, status, fetcher_type, proxy_region, content_bytes, elapsed_ms),
        )
        self._conn.commit()

    def request_count_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self._conn.execute(
            "SELECT COUNT(*) AS count FROM request_log WHERE substr(requested_at, 1, 10) = ?",
            (today,),
        ).fetchone()
        return int(row["count"])

    def record_block(self, pattern: str) -> None:
        self._conn.execute(
            """
            INSERT INTO blocked_patterns (pattern, blocked_count, updated_at)
            VALUES (?, 1, ?)
            ON CONFLICT(pattern) DO UPDATE SET
              blocked_count = blocked_count + 1,
              updated_at = excluded.updated_at
            """,
            (pattern, _now()),
        )
        self._conn.commit()

    def needs_playwright(self, url_or_pattern: str) -> bool:
        rows = self._conn.execute("SELECT pattern, blocked_count FROM blocked_patterns").fetchall()
        for row in rows:
            if row["blocked_count"] >= 3 and row["pattern"] in url_or_pattern:
                return True
        return False

    def queue_stats(self) -> dict[str, int]:
        row = self._conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN match_fetched = 1 THEN 1 ELSE 0 END) AS match_fetched,
              SUM(CASE WHEN stats_fetched = 1 THEN 1 ELSE 0 END) AS stats_fetched,
              SUM(CASE WHEN parsed = 1 THEN 1 ELSE 0 END) AS parsed
            FROM scrape_queue
            """
        ).fetchone()
        return {key: int(row[key] or 0) for key in ("total", "match_fetched", "stats_fetched", "parsed")}

    def _mark(self, match_id: str, column: str) -> None:
        if column not in {"match_fetched", "stats_fetched", "parsed"}:
            raise ValueError(f"unsupported mark column: {column}")
        self._conn.execute(f"UPDATE scrape_queue SET {column} = 1, updated_at = ? WHERE match_id = ?", (_now(), match_id))
        self._conn.commit()

    def _create_tables(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS scrape_queue (
              match_id TEXT PRIMARY KEY,
              match_url TEXT NOT NULL,
              event_name TEXT,
              event_stars INTEGER,
              scheduled_at TEXT,
              priority_tier INTEGER NOT NULL DEFAULT 9,
              match_fetched INTEGER NOT NULL DEFAULT 0,
              stats_fetched INTEGER NOT NULL DEFAULT 0,
              maps_total INTEGER NOT NULL DEFAULT 0,
              maps_fetched INTEGER NOT NULL DEFAULT 0,
              parsed INTEGER NOT NULL DEFAULT 0,
              retry_count INTEGER NOT NULL DEFAULT 0,
              last_error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS blocked_patterns (
              pattern TEXT PRIMARY KEY,
              blocked_count INTEGER NOT NULL DEFAULT 0,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS request_log (
              request_id INTEGER PRIMARY KEY AUTOINCREMENT,
              requested_at TEXT NOT NULL,
              url TEXT NOT NULL,
              status INTEGER NOT NULL,
              fetcher_type TEXT NOT NULL,
              proxy_region TEXT,
              content_bytes INTEGER NOT NULL,
              elapsed_ms INTEGER NOT NULL
            );
            """
        )
        self._conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
