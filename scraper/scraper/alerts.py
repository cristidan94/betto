from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


def send_webhook(webhook_url: str, title: str, payload: dict[str, Any], timeout_seconds: int = 10) -> dict[str, Any]:
    if not webhook_url:
        return {"sent": False, "reason": "not_configured"}
    body = json.dumps({"title": title, "payload": payload}, default=str).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": "betto-hltv-scraper"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return {"sent": True, "status": int(response.status)}
    except (OSError, urllib.error.URLError) as exc:
        return {"sent": False, "reason": str(exc)}
