from __future__ import annotations

import csv
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sports.cs.ingestion.kaggle_hltv import (
    parse_kaggle_rolling_stats_csv,
    kaggle_rolling_stats_match_to_fixture_payload,
    write_kaggle_rolling_stats_fixture_payloads,
    KAGGLE_CS2_ROLLING_STATS_SOURCE,
)


def _write_csv(tmp_path: Path, rows: list[dict[str, str]], filename: str = "rolling.csv") -> Path:
    path = tmp_path / filename
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _sample_row(**overrides: str) -> dict[str, str]:
    base = {
        "date": "2025-03-10T12:00:00Z",
        "event_name": "IEM Katowice 2025",
        "winner_side": "team1",
        "team1_score": "2",
        "team2_score": "1",
        "detailed_stats_url": "https://www.hltv.org/stats/matches/112345/navi-vs-faze",
        "team1_opening_kills": "30",
        "team1_opening_deaths": "25",
        "team1_multi_kill_rounds": "40",
        "team1_kast_pct": "72.5",
        "team1_clutches_won": "5",
        "team1_kills": "200",
        "team1_assists": "80",
        "team1_deaths": "190",
        "team1_adr": "78.3",
        "team1_swing_pct": "0.5",
        "team1_rating_3": "1.12",
        "team2_opening_kills": "25",
        "team2_opening_deaths": "30",
        "team2_multi_kill_rounds": "35",
        "team2_kast_pct": "68.0",
        "team2_clutches_won": "3",
        "team2_kills": "190",
        "team2_assists": "70",
        "team2_deaths": "200",
        "team2_adr": "74.1",
        "team2_swing_pct": "-0.3",
        "team2_rating_3": "0.98",
        "team1_name": "navi",
        "team2_name": "faze",
        "team1_roll5_adr": "76.2",
        "team1_roll5_assists": "78.4",
        "team1_roll5_clutches_won": "4.2",
        "team1_roll5_deaths": "188.0",
        "team1_roll5_kast_pct": "73.1",
        "team1_roll5_kills": "198.0",
        "team1_roll5_multi_kill_rounds": "38.8",
        "team1_roll5_opening_deaths": "24.6",
        "team1_roll5_opening_kills": "29.2",
        "team1_roll5_rating_3": "1.10",
        "team1_roll5_swing_pct": "0.42",
        "team2_roll5_adr": "73.5",
        "team2_roll5_assists": "68.0",
        "team2_roll5_clutches_won": "3.0",
        "team2_roll5_deaths": "195.0",
        "team2_roll5_kast_pct": "69.5",
        "team2_roll5_kills": "185.0",
        "team2_roll5_multi_kill_rounds": "33.0",
        "team2_roll5_opening_deaths": "28.0",
        "team2_roll5_opening_kills": "24.0",
        "team2_roll5_rating_3": "0.96",
        "team2_roll5_swing_pct": "-0.28",
    }
    base.update(overrides)
    return base


class TestParseRollingStats:
    def test_basic_parse(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        matches, features = parse_kaggle_rolling_stats_csv(path)
        assert len(matches) == 1
        match = matches[0]
        assert match.hltv_id == "hltv-stats-112345"
        assert match.team_a.name == "navi"
        assert match.team_b.name == "faze"
        assert match.best_of == 3
        assert match.status == "finished"
        assert match.scheduled_at == datetime(2025, 3, 10, 12, 0, tzinfo=timezone.utc)

    def test_extracts_hltv_stats_id(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        matches, features = parse_kaggle_rolling_stats_csv(path)
        f = features[matches[0].hltv_id]
        assert f["hltv_stats_id"] == "112345"
        assert "hltv.org" in f["detailed_stats_url"]

    def test_rolling_features_present(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        _, features = parse_kaggle_rolling_stats_csv(path)
        f = list(features.values())[0]
        assert "team_a_rolling_5" in f
        assert "team_b_rolling_5" in f
        assert f["team_a_rolling_5"]["roll5_adr"] == 76.2
        assert f["team_b_rolling_5"]["roll5_rating_3"] == 0.96

    def test_match_stats_present(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        _, features = parse_kaggle_rolling_stats_csv(path)
        f = list(features.values())[0]
        assert f["team_a_match_stats"]["adr"] == 78.3
        assert f["team_b_match_stats"]["opening_kills"] == 25.0

    def test_winner_side_team2(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row(winner_side="team2", team1_score="1", team2_score="2")])
        matches, _ = parse_kaggle_rolling_stats_csv(path)
        assert matches[0].best_of == 3

    def test_fallback_synthetic_id_no_url(self, tmp_path: Path) -> None:
        row = _sample_row(detailed_stats_url="")
        path = _write_csv(tmp_path, [row])
        matches, _ = parse_kaggle_rolling_stats_csv(path)
        assert matches[0].hltv_id.startswith("kaggle-rolling-")

    def test_limit(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row(), _sample_row(team1_name="spirit", detailed_stats_url="https://www.hltv.org/stats/matches/99999/spirit-vs-faze")])
        matches, features = parse_kaggle_rolling_stats_csv(path, limit=1)
        assert len(matches) == 1
        assert len(features) == 1

    def test_empty_rolling_values_become_none(self, tmp_path: Path) -> None:
        row = _sample_row(team1_roll5_adr="", team2_roll5_rating_3="")
        path = _write_csv(tmp_path, [row])
        _, features = parse_kaggle_rolling_stats_csv(path)
        f = list(features.values())[0]
        assert f["team_a_rolling_5"]["roll5_adr"] is None
        assert f["team_b_rolling_5"]["roll5_rating_3"] is None

    def test_maps_empty(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        matches, _ = parse_kaggle_rolling_stats_csv(path)
        assert matches[0].maps == ()


class TestRollingStatsPayload:
    def test_payload_source(self, tmp_path: Path) -> None:
        path = _write_csv(tmp_path, [_sample_row()])
        matches, features = parse_kaggle_rolling_stats_csv(path)
        payload = kaggle_rolling_stats_match_to_fixture_payload(matches[0], features[matches[0].hltv_id])
        assert payload["source"]["name"] == KAGGLE_CS2_ROLLING_STATS_SOURCE
        assert "rolling_features" in payload
        assert "team_a_rolling_5" in payload["rolling_features"]

    def test_write_files(self, tmp_path: Path) -> None:
        csv_path = _write_csv(tmp_path, [_sample_row()])
        matches, features = parse_kaggle_rolling_stats_csv(csv_path)
        out_dir = tmp_path / "out"
        written = write_kaggle_rolling_stats_fixture_payloads(matches, features, out_dir)
        assert len(written) == 1
        assert written[0].exists()
        data = json.loads(written[0].read_text(encoding="utf-8"))
        assert data["hltv_id"] == "hltv-stats-112345"
        assert "rolling_features" in data
