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


DEFAULT_TIER_OVERRIDES = {
    "PGL Major": 1,
    "BLAST.tv Major": 1,
    "Perfect World Major": 1,
    "FACEIT Major": 1,
    "StarLadder Major": 1,
    "IEM Katowice": 1,
    "IEM Cologne": 1,
    "BLAST Premier World Final": 1,
    "ESL Pro League": 1,
    "CS Asia Championships": 1,
    "CCT": 2,
    "YaLLa Compass": 2,
    "Roobet Cup": 2,
    "Thunderpick World Championship": 2,
}


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
    backfill_pages_per_run: int = 50
    backfill_matches_per_run: int = 100
    backfill_empty_pages_to_stop: int = 10
    backfill_start_page: int = 0
    backfill_max_page: int | None = None
    backfill_stop_date: str | None = None
    alert_webhook_url: str = ""
    unblocker_proxy: str = ""
    unblocker_user: str = ""
    unblocker_pass: str = ""
    tier_registry_path: Path | None = None
    event_tier_overrides: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TIER_OVERRIDES))
    event_allow_list: list[str] = field(default_factory=lambda: list(EVENT_ALLOW_LIST))


def load_config() -> ScraperConfig:
    if load_dotenv is not None:
        load_dotenv()
    regions_raw = os.environ.get("HLTV_PROXY_REGIONS", "us,eu,br")
    allow_list_raw = os.environ.get("HLTV_EVENT_ALLOW_LIST")
    tier_overrides_raw = os.environ.get("HLTV_EVENT_TIER_OVERRIDES")
    registry_path = _optional_path(os.environ.get("HLTV_TIER_REGISTRY_PATH"))
    tier_overrides, allow_list = _resolve_tier_config(registry_path, tier_overrides_raw, allow_list_raw)
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
        backfill_pages_per_run=int(os.environ.get("HLTV_BACKFILL_PAGES_PER_RUN", "50")),
        backfill_matches_per_run=int(os.environ.get("HLTV_BACKFILL_MATCHES_PER_RUN", "100")),
        backfill_empty_pages_to_stop=int(os.environ.get("HLTV_BACKFILL_EMPTY_PAGES_TO_STOP", "10")),
        backfill_start_page=int(os.environ.get("HLTV_BACKFILL_START_PAGE", "0")),
        backfill_max_page=_optional_int(os.environ.get("HLTV_BACKFILL_MAX_PAGE")),
        backfill_stop_date=_optional_str(os.environ.get("HLTV_BACKFILL_STOP_DATE")),
        alert_webhook_url=os.environ.get("HLTV_ALERT_WEBHOOK_URL", ""),
        unblocker_proxy=os.environ.get("HLTV_UNBLOCKER_PROXY", ""),
        unblocker_user=os.environ.get("HLTV_UNBLOCKER_USER", ""),
        unblocker_pass=os.environ.get("HLTV_UNBLOCKER_PASS", ""),
        tier_registry_path=registry_path,
        event_tier_overrides=tier_overrides,
        event_allow_list=allow_list,
    )


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    return int(value)


def _optional_str(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


def _optional_path(value: str | None) -> Path | None:
    if value is None or not value.strip():
        return None
    return Path(value.strip())


def _resolve_tier_config(
    registry_path: Path | None,
    tier_overrides_raw: str | None,
    allow_list_raw: str | None,
) -> tuple[dict[str, int], list[str]]:
    if tier_overrides_raw or allow_list_raw:
        overrides = _parse_tier_overrides(tier_overrides_raw) if tier_overrides_raw else dict(DEFAULT_TIER_OVERRIDES)
        allow_list = _split_csv(allow_list_raw) if allow_list_raw else list(EVENT_ALLOW_LIST)
        return overrides, allow_list
    if registry_path is not None and registry_path.exists():
        from scraper.tier_registry import allow_list_from_registry, load_tier_registry, tier_overrides_from_registry
        registry = load_tier_registry(registry_path)
        return tier_overrides_from_registry(registry), allow_list_from_registry(registry)
    return dict(DEFAULT_TIER_OVERRIDES), list(EVENT_ALLOW_LIST)


def _parse_tier_overrides(value: str) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        if "=" not in item:
            raise ValueError(f"invalid HLTV_EVENT_TIER_OVERRIDES item: {item!r}")
        pattern, tier = item.split("=", 1)
        parsed = int(tier.strip())
        if parsed < 1:
            raise ValueError(f"tier override must be >= 1: {item!r}")
        overrides[pattern.strip()] = parsed
    return overrides
