from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - dependency installed in scraper venv.
    load_dotenv = None  # type: ignore[assignment]


EVENT_ALLOW_LIST = [
    "PGL Major",
    "BLAST.tv Major",
    "Perfect World Major",
    "FACEIT Major",
    "StarLadder Major",
    "IEM Katowice",
    "IEM Cologne",
    "IEM Chengdu",
    "IEM Dallas",
    "IEM Sydney",
    "IEM Rio",
    "IEM Melbourne",
    "Intel Extreme Masters",
    "ESL Pro League",
    "BLAST Premier Spring",
    "BLAST Premier Fall",
    "BLAST Premier World Final",
    "Thunderpick World Championship",
    "CS Asia Championships",
    "YaLLa Compass",
    "Roobet Cup",
    "Betway Championship",
    "CCT Season",
    "CCT Global Finals",
    "PGL CS2 Major",
]


@dataclass(frozen=True)
class ScraperConfig:
    proxy_url: str = ""
    proxy_regions: list[str] = field(default_factory=lambda: ["us", "eu", "br"])
    raw_dir: Path = field(default_factory=lambda: Path("data/raw/hltv"))
    output_dir: Path = field(default_factory=lambda: Path("data/hltv_scraped"))
    db_path: Path = field(default_factory=lambda: Path("data/hltv_scraper.db"))
    daily_cap: int = 5000
    min_delay: int = 8
    max_delay: int = 15
    cooldown_every: int = 50
    cooldown_seconds: int = 120
    quiet_hours_start: int = 3
    quiet_hours_end: int = 6
    verify_tls: bool = True
    event_allow_list: list[str] = field(default_factory=lambda: list(EVENT_ALLOW_LIST))


def load_config() -> ScraperConfig:
    if load_dotenv is not None:
        load_dotenv()
    regions_raw = os.environ.get("HLTV_PROXY_REGIONS", "us,eu,br")
    return ScraperConfig(
        proxy_url=os.environ.get("HLTV_PROXY_URL", ""),
        proxy_regions=[r.strip() for r in regions_raw.split(",") if r.strip()],
        raw_dir=Path(os.environ.get("HLTV_RAW_DIR", "data/raw/hltv")),
        output_dir=Path(os.environ.get("HLTV_OUTPUT_DIR", "data/hltv_scraped")),
        db_path=Path(os.environ.get("HLTV_DB_PATH", "data/hltv_scraper.db")),
        daily_cap=int(os.environ.get("HLTV_DAILY_CAP", "5000")),
        min_delay=int(os.environ.get("HLTV_MIN_DELAY", "8")),
        max_delay=int(os.environ.get("HLTV_MAX_DELAY", "15")),
        cooldown_every=int(os.environ.get("HLTV_COOLDOWN_EVERY", "50")),
        cooldown_seconds=int(os.environ.get("HLTV_COOLDOWN_SECONDS", "120")),
        quiet_hours_start=int(os.environ.get("HLTV_QUIET_HOURS_START", "3")),
        quiet_hours_end=int(os.environ.get("HLTV_QUIET_HOURS_END", "6")),
        verify_tls=_bool_env("HLTV_VERIFY_TLS", True),
    )


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}
