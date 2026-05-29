from __future__ import annotations

from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.status import collect_status


def collect_health(
    config: ScraperConfig | None = None,
    recent_limit: int = 25,
    max_recent_failure_rate: float = 0.5,
    max_failed_queue_ratio: float = 0.25,
) -> dict[str, Any]:
    if config is None:
        config = load_config()
    status = collect_status(config, recent_limit=recent_limit)
    checks = {
        "queue_exists": _queue_exists(status),
        "request_failure_rate": _request_failure_rate_ok(status, max_recent_failure_rate),
        "failed_queue_ratio": _failed_queue_ratio_ok(status, max_failed_queue_ratio),
        "backfill_state": _backfill_state_ok(status),
    }
    return {
        "ok": all(check["ok"] for check in checks.values()),
        "checks": checks,
        "summary": {
            "queue": status["queue"],
            "backfill": status["backfill"],
            "requests_today": status["requests"]["today"],
        },
    }


def _queue_exists(status: dict[str, Any]) -> dict[str, Any]:
    total = int(status["queue"].get("total", 0))
    return {"ok": total > 0, "total": total}


def _request_failure_rate_ok(status: dict[str, Any], threshold: float) -> dict[str, Any]:
    recent = status["requests"].get("recent", [])
    if not recent:
        return {"ok": True, "rate": 0.0, "sample": 0, "threshold": threshold}
    failures = sum(1 for item in recent if int(item.get("status") or 0) >= 400 or int(item.get("status") or 0) == 0)
    rate = failures / len(recent)
    return {"ok": rate <= threshold, "rate": round(rate, 4), "sample": len(recent), "threshold": threshold}


def _failed_queue_ratio_ok(status: dict[str, Any], threshold: float) -> dict[str, Any]:
    queue = status["queue"]
    total = max(int(queue.get("total", 0)), 1)
    failed = int(queue.get("failed", 0))
    ratio = failed / total
    return {"ok": ratio <= threshold, "ratio": round(ratio, 4), "failed": failed, "threshold": threshold}


def _backfill_state_ok(status: dict[str, Any]) -> dict[str, Any]:
    backfill = status["backfill"]
    return {
        "ok": bool(backfill.get("done")) or int(backfill.get("next_page", 0)) >= 0,
        "done": bool(backfill.get("done")),
        "next_page": int(backfill.get("next_page", 0)),
        "empty_pages": int(backfill.get("empty_pages", 0)),
    }
