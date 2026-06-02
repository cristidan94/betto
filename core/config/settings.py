from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    env: str
    project_root: Path
    data_dir: Path
    raw_store_dir: Path
    database_url: str
    redis_url: str
    polymarket_gamma_url: str
    polymarket_clob_url: str
    polymarket_snapshot_interval_sec: int
    default_timezone: str
    oddspapi_api_key: str
    oddspapi_base_url: str
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_api_passphrase: str = ""
    polymarket_private_key: str = ""
    polymarket_chain_id: int = 137
    polymarket_address: str = ""

    @property
    def polymarket_credentials_configured(self) -> bool:
        return bool(self.polymarket_api_key and self.polymarket_api_secret and self.polymarket_private_key)


def load_settings() -> Settings:
    project_root = Path(os.environ.get("BETTO_PROJECT_ROOT", Path.cwd())).resolve()
    data_dir = Path(os.environ.get("BETTO_DATA_DIR", project_root / ".betto")).resolve()
    raw_store_dir = Path(os.environ.get("BETTO_RAW_STORE_DIR", data_dir / "raw")).resolve()

    return Settings(
        env=os.environ.get("BETTO_ENV", "local"),
        project_root=project_root,
        data_dir=data_dir,
        raw_store_dir=raw_store_dir,
        database_url=os.environ.get("BETTO_DATABASE_URL", "postgresql://betto:betto@localhost:5432/betto"),
        redis_url=os.environ.get("BETTO_REDIS_URL", "redis://localhost:6379/0"),
        polymarket_gamma_url=os.environ.get("BETTO_POLYMARKET_GAMMA_URL", "https://gamma-api.polymarket.com"),
        polymarket_clob_url=os.environ.get("BETTO_POLYMARKET_CLOB_URL", "https://clob.polymarket.com"),
        polymarket_snapshot_interval_sec=int(os.environ.get("BETTO_POLYMARKET_SNAPSHOT_INTERVAL_SEC", "300")),
        polymarket_api_key=os.environ.get("BETTO_POLYMARKET_API_KEY", ""),
        polymarket_api_secret=os.environ.get("BETTO_POLYMARKET_API_SECRET", ""),
        polymarket_api_passphrase=os.environ.get("BETTO_POLYMARKET_API_PASSPHRASE", ""),
        polymarket_private_key=os.environ.get("BETTO_POLYMARKET_PRIVATE_KEY", ""),
        polymarket_chain_id=int(os.environ.get("BETTO_POLYMARKET_CHAIN_ID", "137")),
        polymarket_address=os.environ.get("BETTO_POLYMARKET_ADDRESS", ""),
        default_timezone=os.environ.get("BETTO_DEFAULT_TIMEZONE", "UTC"),
        oddspapi_api_key=os.environ.get("BETTO_ODDSPAPI_API_KEY", ""),
        oddspapi_base_url=os.environ.get("BETTO_ODDSPAPI_BASE_URL", "https://api.oddspapi.io/v4"),
    )
