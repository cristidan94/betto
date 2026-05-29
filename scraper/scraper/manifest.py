from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scraper.config import ScraperConfig, load_config
from scraper.models import SCHEMA_VERSION
from scraper.quality import collect_quality_report


def build_manifest(config: ScraperConfig | None = None, include_files: bool = False) -> dict[str, Any]:
    if config is None:
        config = load_config()
    files = _fixture_files(config.output_dir)
    file_rows = [_file_row(path, config.output_dir) for path in files]
    snapshot_hash = _snapshot_hash(file_rows)
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_snapshot_id": snapshot_hash,
        "output_dir": str(config.output_dir),
        "file_count": len(files),
        "quality": collect_quality_report(config, sample_limit=10),
    }
    if include_files:
        manifest["files"] = file_rows
    return manifest


def write_manifest(path: Path, config: ScraperConfig | None = None, include_files: bool = False) -> Path:
    manifest = build_manifest(config, include_files=include_files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _file_row(path: Path, root: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": str(path.relative_to(root)),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _snapshot_hash(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(str(item["path"]).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(item["sha256"]).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _fixture_files(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and item.name != "manifest.json")
