from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from scraper.backfill import BACKFILL_DONE, BACKFILL_EMPTY_PAGES, BACKFILL_NEXT_PAGE, BACKFILL_STARTED_AT
from scraper.config import ScraperConfig


def collect_activity(config: ScraperConfig, days: int = 7) -> dict[str, Any]:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    con = sqlite3.connect(str(config.db_path))
    con.row_factory = sqlite3.Row
    try:
        return {
            "period_days": days,
            "requests_by_day": _requests_by_day(con, days),
            "requests_by_type": _requests_by_type(con, cutoff),
            "matches_discovered": _matches_created(con, cutoff),
            "matches_finalized": _matches_finalized(con, cutoff),
            "matches_deferred": _matches_deferred(con, cutoff),
            "errors_recent": _recent_errors(con, cutoff),
            "backfill": _backfill_state(con, config),
            "rankings_scraped": _recent_files(config.output_dir.parent / "raw" / "hltv" / "rankings", days),
            "entities": {
                "events": _recent_files(config.output_dir.parent / "raw" / "hltv" / "events", days),
                "teams": _recent_files(config.output_dir.parent / "raw" / "hltv" / "teams", days),
                "players": _recent_files(config.output_dir.parent / "raw" / "hltv" / "players", days),
            },
            "fixtures_written": _recent_files(config.output_dir, days),
        }
    finally:
        con.close()


def _requests_by_day(con: sqlite3.Connection, days: int) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT
          substr(requested_at, 1, 10) AS day,
          COUNT(*) AS total,
          SUM(CASE WHEN status >= 200 AND status < 400 THEN 1 ELSE 0 END) AS ok,
          SUM(CASE WHEN status >= 400 OR status < 200 THEN 1 ELSE 0 END) AS failed,
          SUM(content_bytes) AS bytes,
          ROUND(AVG(elapsed_ms)) AS avg_ms
        FROM request_log
        WHERE requested_at >= date('now', ?)
        GROUP BY day
        ORDER BY day DESC
        """,
        (f"-{days} days",),
    ).fetchall()
    return [dict(r) for r in rows]


def _requests_by_type(con: sqlite3.Connection, cutoff: str) -> dict[str, int]:
    rows = con.execute(
        """
        SELECT fetcher_type, COUNT(*) AS count
        FROM request_log
        WHERE requested_at >= ?
        GROUP BY fetcher_type
        ORDER BY count DESC
        """,
        (cutoff,),
    ).fetchall()
    return {str(r["fetcher_type"]): int(r["count"]) for r in rows}


def _matches_created(con: sqlite3.Connection, cutoff: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT COUNT(*) AS count FROM scrape_queue WHERE created_at >= ?",
        (cutoff,),
    ).fetchone()
    recent = con.execute(
        """
        SELECT match_id, event_name, priority_tier, created_at
        FROM scrape_queue
        WHERE created_at >= ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (cutoff,),
    ).fetchall()
    return {"count": int(row["count"]), "recent": [dict(r) for r in recent]}


def _matches_finalized(con: sqlite3.Connection, cutoff: str) -> dict[str, Any]:
    row = con.execute(
        "SELECT COUNT(*) AS count FROM scrape_queue WHERE completed_at >= ? AND final = 1",
        (cutoff,),
    ).fetchone()
    recent = con.execute(
        """
        SELECT match_id, event_name, lifecycle_status, completed_at
        FROM scrape_queue
        WHERE completed_at >= ? AND final = 1
        ORDER BY completed_at DESC
        LIMIT 10
        """,
        (cutoff,),
    ).fetchall()
    return {"count": int(row["count"]), "recent": [dict(r) for r in recent]}


def _matches_deferred(con: sqlite3.Connection, cutoff: str) -> dict[str, Any]:
    rows = con.execute(
        """
        SELECT lifecycle_status, COUNT(*) AS count
        FROM scrape_queue
        WHERE final = 0 AND updated_at >= ?
        GROUP BY lifecycle_status
        ORDER BY count DESC
        """,
        (cutoff,),
    ).fetchall()
    return {str(r["lifecycle_status"] or "unknown"): int(r["count"]) for r in rows}


def _recent_errors(con: sqlite3.Connection, cutoff: str) -> list[dict[str, Any]]:
    rows = con.execute(
        """
        SELECT match_id, event_name, retry_count, last_error, stats_error, updated_at
        FROM scrape_queue
        WHERE (last_error IS NOT NULL OR stats_error IS NOT NULL)
          AND updated_at >= ?
        ORDER BY updated_at DESC
        LIMIT 15
        """,
        (cutoff,),
    ).fetchall()
    return [dict(r) for r in rows]


def _backfill_state(con: sqlite3.Connection, config: ScraperConfig) -> dict[str, Any]:
    def _state(key: str, default: str | None = None) -> str | None:
        row = con.execute("SELECT value FROM scraper_state WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else default

    next_page = int(_state(BACKFILL_NEXT_PAGE, str(config.backfill_start_page)) or "0")
    return {
        "next_page": next_page,
        "next_offset": next_page * 100,
        "empty_pages": int(_state(BACKFILL_EMPTY_PAGES, "0") or "0"),
        "done": _state(BACKFILL_DONE, "0") == "1",
        "started_at": _state(BACKFILL_STARTED_AT),
    }


def _recent_files(directory: Path, days: int) -> int:
    if not directory.exists():
        return 0
    cutoff_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
    count = 0
    for item in directory.iterdir():
        if item.is_file() and item.stat().st_mtime >= cutoff_ts:
            count += 1
        elif item.is_dir():
            for sub in item.iterdir():
                if sub.is_file() and sub.stat().st_mtime >= cutoff_ts:
                    count += 1
    return count


def format_activity(data: dict[str, Any]) -> str:
    lines: list[str] = []
    days = data["period_days"]
    lines.append(f"=== HLTV Scraper Activity (last {days} days) ===")
    lines.append("")

    req_days = data.get("requests_by_day", [])
    if req_days:
        lines.append("REQUESTS BY DAY")
        lines.append(f"  {'Date':<12} {'Total':>6} {'OK':>6} {'Fail':>6} {'Avg ms':>7} {'MB':>8}")
        for rd in req_days:
            mb = (rd.get("bytes") or 0) / (1024 * 1024)
            lines.append(
                f"  {rd['day']:<12} {rd['total']:>6} {rd.get('ok', 0):>6} {rd.get('failed', 0):>6}"
                f" {int(rd.get('avg_ms') or 0):>7} {mb:>8.1f}"
            )
        lines.append("")

    req_types = data.get("requests_by_type", {})
    if req_types:
        lines.append("REQUESTS BY TYPE")
        for ft, count in req_types.items():
            lines.append(f"  {ft}: {count}")
        lines.append("")

    disc = data.get("matches_discovered", {})
    lines.append(f"MATCHES DISCOVERED: {disc.get('count', 0)}")
    for m in disc.get("recent", [])[:5]:
        lines.append(f"  {m['match_id']}  {m.get('event_name') or '?':<40}  {m.get('created_at', '')[:19]}")
    lines.append("")

    fin = data.get("matches_finalized", {})
    lines.append(f"MATCHES FINALIZED: {fin.get('count', 0)}")
    for m in fin.get("recent", [])[:5]:
        lines.append(f"  {m['match_id']}  {m.get('event_name') or '?':<40}  {m.get('completed_at', '')[:19]}")
    lines.append("")

    deferred = data.get("matches_deferred", {})
    if deferred:
        lines.append("DEFERRED / IN-PROGRESS")
        for status, count in deferred.items():
            lines.append(f"  {status}: {count}")
        lines.append("")

    bf = data.get("backfill", {})
    lines.append("BACKFILL")
    lines.append(f"  Page: {bf.get('next_page', '?')} (offset {bf.get('next_offset', '?')})")
    lines.append(f"  Empty pages: {bf.get('empty_pages', '?')}")
    lines.append(f"  Done: {'yes' if bf.get('done') else 'no'}")
    if bf.get("started_at"):
        lines.append(f"  Started: {bf['started_at'][:19]}")
    lines.append("")

    rankings = data.get("rankings_scraped", 0)
    entities = data.get("entities", {})
    fixtures = data.get("fixtures_written", 0)
    lines.append("FILES WRITTEN")
    lines.append(f"  Fixtures:  {fixtures}")
    lines.append(f"  Rankings:  {rankings}")
    lines.append(f"  Events:    {entities.get('events', 0)}")
    lines.append(f"  Teams:     {entities.get('teams', 0)}")
    lines.append(f"  Players:   {entities.get('players', 0)}")
    lines.append("")

    errors = data.get("errors_recent", [])
    if errors:
        lines.append(f"RECENT ERRORS ({len(errors)})")
        for e in errors[:10]:
            err_msg = e.get("last_error") or e.get("stats_error") or "?"
            if len(err_msg) > 80:
                err_msg = err_msg[:77] + "..."
            lines.append(f"  {e['match_id']}  retries={e.get('retry_count', 0)}  {err_msg}")
        lines.append("")

    return "\n".join(lines)
