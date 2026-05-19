from __future__ import annotations

from pathlib import Path

from sports.cs.normalization import parse_hltv_fixture
from sports.cs.normalization.records import CsParsedMatch


def load_fixture_corpus(path: Path) -> list[CsParsedMatch]:
    if path.is_file():
        return [parse_hltv_fixture(path)]
    if not path.is_dir():
        raise ValueError(f"fixture corpus path does not exist: {path}")
    fixtures = sorted(item for item in path.glob("*.json") if item.is_file())
    if not fixtures:
        raise ValueError(f"fixture corpus has no JSON fixtures: {path}")
    return [parse_hltv_fixture(item) for item in fixtures]

