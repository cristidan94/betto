from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Callable

from scraper.config import ScraperConfig, load_config


ImportChecker = Callable[[str], bool]
BrowserChecker = Callable[[], bool]


DEPENDENCIES = {
    "curl_cffi": "curl_cffi fast fetcher",
    "playwright": "Playwright fallback fetcher",
    "bs4": "BeautifulSoup parser",
    "lxml": "lxml parser backend",
    "dotenv": ".env loader",
}


def collect_preflight(
    config: ScraperConfig | None = None,
    import_checker: ImportChecker | None = None,
    browser_checker: BrowserChecker | None = None,
    create_dirs: bool = False,
) -> dict:
    if config is None:
        config = load_config()
    if import_checker is None:
        import_checker = _module_available
    if browser_checker is None:
        browser_checker = _playwright_browser_available

    dependency_checks = {
        name: {"ok": import_checker(name), "purpose": purpose}
        for name, purpose in DEPENDENCIES.items()
    }
    path_checks = {
        "raw_dir": _path_check(config.raw_dir, create_dirs),
        "output_dir": _path_check(config.output_dir, create_dirs),
        "db_parent": _path_check(config.db_path.parent, create_dirs),
    }
    proxy_configured = bool(config.proxy_url and "password" not in config.proxy_url.lower())
    checks = {
        "python": {
            "ok": sys.version_info >= (3, 11),
            "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        },
        "dependencies": dependency_checks,
        "browser": {
            "ok": browser_checker() if dependency_checks["playwright"]["ok"] else False,
            "engine": "chromium",
        },
        "proxy": {
            "ok": proxy_configured,
            "regions": config.proxy_regions,
            "configured": bool(config.proxy_url),
        },
        "paths": path_checks,
        "limits": {
            "daily_cap": config.daily_cap,
            "min_delay": config.min_delay,
            "max_delay": config.max_delay,
            "quiet_hours_utc": [config.quiet_hours_start, config.quiet_hours_end],
            "verify_tls": config.verify_tls,
        },
    }
    ok = (
        checks["python"]["ok"]
        and all(item["ok"] for item in dependency_checks.values())
        and checks["browser"]["ok"]
        and checks["proxy"]["ok"]
        and all(item["ok"] for item in path_checks.values())
    )
    return {"ok": ok, "checks": checks}


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _playwright_browser_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        try:
            return Path(playwright.chromium.executable_path).exists()
        finally:
            playwright.stop()
    except Exception:
        return False


def _path_check(path: Path, create_dirs: bool) -> dict:
    if create_dirs:
        path.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    target = path if exists else path.parent
    writable = target.exists() and _is_writable(target)
    return {"ok": exists and writable, "path": str(path), "exists": exists, "writable": writable}


def _is_writable(path: Path) -> bool:
    try:
        probe = path / ".hltv_preflight_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True
