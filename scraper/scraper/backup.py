from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path

from scraper.config import ScraperConfig, load_config


def create_backup(config: ScraperConfig | None = None, out_dir: Path | str = "backups") -> Path:
    if config is None:
        config = load_config()
    backup_dir = Path(out_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"hltv-scraper-{timestamp}.tar.gz"

    with tarfile.open(target, "w:gz") as archive:
        _add_if_exists(archive, config.db_path, "data/hltv_scraper.db")
        _add_if_exists(archive, config.raw_dir, "data/raw/hltv")
        _add_if_exists(archive, config.output_dir, "data/hltv_scraped")
    return target


def _add_if_exists(archive: tarfile.TarFile, path: Path, arcname: str) -> None:
    if path.exists():
        archive.add(path, arcname=arcname)
