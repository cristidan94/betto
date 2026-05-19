from __future__ import annotations

import json
from datetime import datetime

from core.ingestion import FetchResult


class HltvSeedAdapter:
    """Offline seed adapter used until the live HLTV scraper is implemented."""

    source = "hltv"

    def fetch_since(self, since: datetime) -> list[FetchResult]:
        payload = {
            "source": self.source,
            "note": "placeholder seed payload; replace with cached HLTV HTML/API fetches",
            "since": since.isoformat(),
        }
        return [
            FetchResult.from_text(
                source=self.source,
                source_id=f"seed-{since.date().isoformat()}",
                url="seed://hltv",
                text=json.dumps(payload, sort_keys=True),
                content_type="application/json",
            )
        ]

