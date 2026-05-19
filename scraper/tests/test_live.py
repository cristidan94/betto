from __future__ import annotations

from pathlib import Path

from scraper.live_test import run_live_test as _run_live_test

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def run_live_test() -> int:
    return _run_live_test(FIXTURES_DIR)
