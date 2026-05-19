from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


@dataclass(frozen=True)
class FetchResult:
    source: str
    source_id: str
    url: str
    content: bytes
    content_type: str
    fetched_at: datetime

    @classmethod
    def from_text(cls, source: str, source_id: str, url: str, text: str, content_type: str = "text/plain") -> "FetchResult":
        return cls(
            source=source,
            source_id=source_id,
            url=url,
            content=text.encode("utf-8"),
            content_type=content_type,
            fetched_at=datetime.now(timezone.utc),
        )


class SourceAdapter(Protocol):
    source: str

    def fetch_since(self, since: datetime) -> list[FetchResult]:
        """Fetch raw payloads changed since the supplied timestamp."""

