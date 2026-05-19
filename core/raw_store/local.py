from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from core.ingestion.base import FetchResult


@dataclass(frozen=True)
class RawObject:
    source: str
    source_id: str
    url: str
    content_hash: str
    content_type: str
    fetched_at: datetime
    body_path: Path
    metadata_path: Path


class LocalRawStore:
    """Filesystem-backed raw payload store for development and tests."""

    def __init__(self, root: Path):
        self.root = root

    def put(self, result: FetchResult) -> RawObject:
        digest = hashlib.sha256(result.content).hexdigest()
        safe_source_id = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in result.source_id)
        folder = self.root / result.source / safe_source_id
        folder.mkdir(parents=True, exist_ok=True)

        body_path = folder / f"{digest}.bin"
        metadata_path = folder / f"{digest}.json"
        body_path.write_bytes(result.content)

        obj = RawObject(
            source=result.source,
            source_id=result.source_id,
            url=result.url,
            content_hash=digest,
            content_type=result.content_type,
            fetched_at=result.fetched_at,
            body_path=body_path,
            metadata_path=metadata_path,
        )
        metadata = asdict(obj)
        metadata["fetched_at"] = result.fetched_at.isoformat()
        metadata["body_path"] = str(body_path)
        metadata["metadata_path"] = str(metadata_path)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return obj

    def read_bytes(self, obj: RawObject) -> bytes:
        return obj.body_path.read_bytes()

