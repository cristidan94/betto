from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sports.cs.ingestion.kaggle_hltv import (
    parse_kaggle_cs2_match_data_csv,
    kaggle_cs2_match_data_to_fixture_payload,
    write_kaggle_cs2_match_data_fixture_payloads,
    KAGGLE_CS2_MATCH_DATA_BETTING_SOURCE,
)


def _write_semicolon_csv(tmp_path: Path, rows: list[dict[str, str]], filename: str = "match_data.csv") -> Path:
    path = tmp_path / filename
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _sample_map_row(match_id: str = "2368924", team1: str = "NAVI", team2: str = "FaZe",
                     map_name: str = "Inferno", team1_win: str = "1", **overrides: str) -> dict[str, str]:
    base = {
        "matchID": match_id,
        "team1": team1,
        "team2": team2,
        "map": map_name,
        "team1_win": team1_win,
        "T1_mapwinrate": "65.0%",
        "T2_mapwinrate": "55.0%",
        "T1_player0_Total kills": "180.0",
        "T1_player0_Headshot %": "48.5%",
        "T1_player0_Total deaths": "160.0",
        "T1_player0_K/D Ratio": "1.12",
        "T1_player0_Damage / Round": "80.5",
        "T1_player0_Grenade dmg / Round": "4.2",
        "T1_player0_Maps played": "15.0",
        "T1_player0_Rounds played": "350.0",
        "T1_player0_Kills / round": "0.78",
        "T1_player0_Assists / round": "0.12",
        "T1_player0_Deaths / round": "0.62",
        "T1_player0_Saved by teammate / round": "0.08",
        "T1_player0_Saved teammates / round": "0.07",
        "T1_player0_Rating 1.0": "1.15",
        "T2_player0_Total kills": "170.0",
        "T2_player0_Headshot %": "45.0%",
        "T2_player0_Total deaths": "175.0",
        "T2_player0_K/D Ratio": "0.97",
        "T2_player0_Damage / Round": "72.3",
        "T2_player0_Grenade dmg / Round": "3.8",
        "T2_player0_Maps played": "12.0",
        "T2_player0_Rounds played": "290.0",
        "T2_player0_Kills / round": "0.65",
        "T2_player0_Assists / round": "0.14",
        "T2_player0_Deaths / round": "0.68",
        "T2_player0_Saved by teammate / round": "0.10",
        "T2_player0_Saved teammates / round": "0.06",
        "T2_player0_Rating 1.0": "0.98",
    }
    base.update(overrides)
    return base


class TestParseCS2MatchDataBetting:
    def test_single_map_match(self, tmp_path: Path) -> None:
        path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        matches, features = parse_kaggle_cs2_match_data_csv(path)
        assert len(matches) == 1
        m = matches[0]
        assert m.hltv_id == "2368924"
        assert m.team_a.name == "NAVI"
        assert m.team_b.name == "FaZe"
        assert len(m.maps) == 1
        assert m.maps[0].map_name == "Inferno"
        assert m.maps[0].winner_hltv_id == m.team_a.hltv_id

    def test_multi_map_match(self, tmp_path: Path) -> None:
        rows = [
            _sample_map_row(map_name="Inferno", team1_win="1"),
            _sample_map_row(map_name="Mirage", team1_win="0"),
            _sample_map_row(map_name="Nuke", team1_win="1"),
        ]
        path = _write_semicolon_csv(tmp_path, rows)
        matches, features = parse_kaggle_cs2_match_data_csv(path)
        assert len(matches) == 1
        m = matches[0]
        assert len(m.maps) == 3
        assert m.best_of == 3
        assert m.maps[0].winner_hltv_id == m.team_a.hltv_id
        assert m.maps[1].winner_hltv_id == m.team_b.hltv_id
        assert m.maps[2].winner_hltv_id == m.team_a.hltv_id

    def test_multiple_matches(self, tmp_path: Path) -> None:
        rows = [
            _sample_map_row(match_id="100", team1="A", team2="B"),
            _sample_map_row(match_id="200", team1="C", team2="D"),
        ]
        path = _write_semicolon_csv(tmp_path, rows)
        matches, _ = parse_kaggle_cs2_match_data_csv(path)
        assert len(matches) == 2
        assert {m.hltv_id for m in matches} == {"100", "200"}

    def test_epoch_sentinel_date(self, tmp_path: Path) -> None:
        path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        matches, _ = parse_kaggle_cs2_match_data_csv(path)
        assert matches[0].scheduled_at == datetime(2000, 1, 1, tzinfo=timezone.utc)

    def test_player_features_extracted(self, tmp_path: Path) -> None:
        path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        _, features = parse_kaggle_cs2_match_data_csv(path)
        f = list(features.values())[0]
        assert f["team_a_map_wins"] == 1
        assert f["team_b_map_wins"] == 0
        assert len(f["maps"]) == 1
        map_f = f["maps"][0]
        assert map_f["map_name"] == "Inferno"
        assert len(map_f["team_a_players"]) >= 1
        assert len(map_f["team_b_players"]) >= 1

    def test_mapwinrate_parsed(self, tmp_path: Path) -> None:
        path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        _, features = parse_kaggle_cs2_match_data_csv(path)
        map_f = list(features.values())[0]["maps"][0]
        assert map_f["t1_mapwinrate"] == 65.0
        assert map_f["t2_mapwinrate"] == 55.0

    def test_skips_unknown_maps(self, tmp_path: Path) -> None:
        rows = [
            _sample_map_row(match_id="500", map_name="Default"),
        ]
        path = _write_semicolon_csv(tmp_path, rows)
        matches, _ = parse_kaggle_cs2_match_data_csv(path)
        assert len(matches) == 0

    def test_limit(self, tmp_path: Path) -> None:
        rows = [
            _sample_map_row(match_id="100"),
            _sample_map_row(match_id="200"),
        ]
        path = _write_semicolon_csv(tmp_path, rows)
        matches, _ = parse_kaggle_cs2_match_data_csv(path, limit=1)
        assert len(matches) == 1


class TestCS2MatchDataPayload:
    def test_payload_source(self, tmp_path: Path) -> None:
        path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        matches, features = parse_kaggle_cs2_match_data_csv(path)
        payload = kaggle_cs2_match_data_to_fixture_payload(matches[0], features[matches[0].hltv_id])
        assert payload["source"]["name"] == KAGGLE_CS2_MATCH_DATA_BETTING_SOURCE
        assert "player_features" in payload

    def test_write_files(self, tmp_path: Path) -> None:
        csv_path = _write_semicolon_csv(tmp_path, [_sample_map_row()])
        matches, features = parse_kaggle_cs2_match_data_csv(csv_path)
        out_dir = tmp_path / "out"
        written = write_kaggle_cs2_match_data_fixture_payloads(matches, features, out_dir)
        assert len(written) == 1
        data = json.loads(written[0].read_text(encoding="utf-8"))
        assert data["hltv_id"] == "2368924"
        assert len(data["maps"]) == 1
        assert "player_features" in data
