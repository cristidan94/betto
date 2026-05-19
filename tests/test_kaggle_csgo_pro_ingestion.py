from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from core.cli.main import main
from sports.cs.ingestion import (
    kaggle_csgo_pro_match_to_fixture_payload,
    parse_kaggle_csgo_pro_results_csv,
)
from sports.cs.normalization import normalize_match


def _write_results_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sample_results_row(**overrides: str) -> dict[str, str]:
    base = {
        "date": "2019-03-01",
        "team_1": "Astralis",
        "team_2": "ENCE",
        "map": "Inferno",
        "result": "16-8",
        "event_name": "IEM Katowice 2019",
        "best_of": "3",
        "match_id": "99001",
    }
    base.update(overrides)
    return base


class KaggleCsgoProResultsParsingTests(unittest.TestCase):
    """Tests for parse_kaggle_csgo_pro_results_csv from results.csv."""

    def test_parses_single_map_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [_sample_results_row(best_of="1")])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match.hltv_id, "99001")
        self.assertEqual(match.team_a.name, "Astralis")
        self.assertEqual(match.team_b.name, "ENCE")
        self.assertEqual(match.best_of, 1)
        self.assertEqual(match.status, "finished")
        self.assertEqual(len(match.maps), 1)
        self.assertEqual(match.maps[0].map_name, "Inferno")
        self.assertEqual(match.maps[0].team_a_score, 16)
        self.assertEqual(match.maps[0].team_b_score, 8)

    def test_groups_multi_map_match_by_match_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(map="Inferno", result="16-8"),
                _sample_results_row(map="Overpass", result="10-16"),
                _sample_results_row(map="Nuke", result="16-14"),
            ])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        self.assertEqual(len(matches), 1)
        self.assertEqual(len(matches[0].maps), 3)
        self.assertEqual(matches[0].maps[0].map_name, "Inferno")
        self.assertEqual(matches[0].maps[1].map_name, "Overpass")
        self.assertEqual(matches[0].maps[2].map_name, "Nuke")
        # Map winners
        self.assertEqual(matches[0].maps[0].winner_hltv_id, matches[0].team_a.hltv_id)  # 16-8
        self.assertEqual(matches[0].maps[1].winner_hltv_id, matches[0].team_b.hltv_id)  # 10-16
        self.assertEqual(matches[0].maps[2].winner_hltv_id, matches[0].team_a.hltv_id)  # 16-14

    def test_different_match_ids_produce_separate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(match_id="99001", map="Inferno", result="16-8"),
                _sample_results_row(match_id="99002", team_1="FaZe", team_2="Liquid", map="Mirage", result="16-12"),
            ])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].hltv_id, "99001")
        self.assertEqual(matches[1].hltv_id, "99002")

    def test_unknown_map_name_is_skipped_with_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(map="Inferno", result="16-8"),
                _sample_results_row(match_id="99002", map="de_zoo", result="16-5"),
                _sample_results_row(match_id="99003", map="Mirage", result="16-10"),
            ])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        # The row with unknown map "de_zoo" should be skipped
        match_ids = {m.hltv_id for m in matches}
        self.assertIn("99001", match_ids)
        self.assertIn("99003", match_ids)
        self.assertNotIn("99002", match_ids)

    def test_normalizes_map_name_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(match_id="100", map="de_inferno", result="16-8"),
                _sample_results_row(match_id="101", map="de_dust2", result="16-12"),
                _sample_results_row(match_id="102", map="de_cache", result="13-16"),
                _sample_results_row(match_id="103", map="de_cbble", result="16-5"),
            ])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        map_names = {m.maps[0].map_name for m in matches}
        self.assertEqual(map_names, {"Inferno", "Dust2", "Cache", "Cobblestone"})

    def test_synthetic_ids_when_no_match_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            row = _sample_results_row()
            del row["match_id"]
            _write_results_csv(path, [row])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].hltv_id.startswith("kaggle-csgo-pro-"))

    def test_limit_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(match_id="1"),
                _sample_results_row(match_id="2"),
                _sample_results_row(match_id="3"),
            ])

            matches = parse_kaggle_csgo_pro_results_csv(path, limit=2)

        self.assertEqual(len(matches), 2)

    def test_best_of_inferred_from_map_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            row1 = _sample_results_row(map="Inferno", result="16-8")
            row2 = _sample_results_row(map="Overpass", result="16-10")
            # Remove best_of so it gets inferred
            del row1["best_of"]
            del row2["best_of"]
            _write_results_csv(path, [row1, row2])

            matches = parse_kaggle_csgo_pro_results_csv(path)

        # 2 maps played => best_of should be 3
        self.assertEqual(matches[0].best_of, 3)


class KaggleCsgoProPicksTests(unittest.TestCase):
    """Tests for joining picks.csv veto sequences."""

    def test_joins_picks_as_vetoes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            picks_path = Path(tmp) / "picks.csv"

            _write_results_csv(results_path, [_sample_results_row()])

            with picks_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "team", "pick_type", "map"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "team": "Astralis", "pick_type": "ban", "map": "Vertigo"})
                writer.writerow({"match_id": "99001", "team": "ENCE", "pick_type": "ban", "map": "Nuke"})
                writer.writerow({"match_id": "99001", "team": "Astralis", "pick_type": "pick", "map": "Inferno"})

            matches = parse_kaggle_csgo_pro_results_csv(results_path, picks_path=picks_path)

        self.assertEqual(len(matches[0].vetoes), 3)
        self.assertEqual(matches[0].vetoes[0].action, "ban")
        self.assertEqual(matches[0].vetoes[0].map_name, "Vertigo")
        self.assertEqual(matches[0].vetoes[0].team_hltv_id, matches[0].team_a.hltv_id)
        self.assertEqual(matches[0].vetoes[1].team_hltv_id, matches[0].team_b.hltv_id)
        self.assertEqual(matches[0].vetoes[2].action, "pick")

    def test_unknown_map_in_picks_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            picks_path = Path(tmp) / "picks.csv"

            _write_results_csv(results_path, [_sample_results_row()])

            with picks_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "team", "pick_type", "map"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "team": "Astralis", "pick_type": "ban", "map": "de_zoo"})
                writer.writerow({"match_id": "99001", "team": "ENCE", "pick_type": "ban", "map": "Nuke"})

            matches = parse_kaggle_csgo_pro_results_csv(results_path, picks_path=picks_path)

        # Only the Nuke ban should survive
        self.assertEqual(len(matches[0].vetoes), 1)
        self.assertEqual(matches[0].vetoes[0].map_name, "Nuke")


class KaggleCsgoProPlayersTests(unittest.TestCase):
    """Tests for joining players.csv."""

    def test_joins_players_to_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            players_path = Path(tmp) / "players.csv"

            _write_results_csv(results_path, [_sample_results_row()])

            with players_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "player_name", "team", "player_id"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "player_name": "device", "team": "Astralis", "player_id": "7592"})
                writer.writerow({"match_id": "99001", "player_name": "dupreeh", "team": "Astralis", "player_id": "7398"})
                writer.writerow({"match_id": "99001", "player_name": "sergej", "team": "ENCE", "player_id": "13202"})

            matches = parse_kaggle_csgo_pro_results_csv(results_path, players_path=players_path)

        self.assertEqual(len(matches[0].players), 3)
        nicknames = {p.nickname for p in matches[0].players}
        self.assertEqual(nicknames, {"device", "dupreeh", "sergej"})
        # Team assignment
        team_a_players = [p for p in matches[0].players if p.team_hltv_id == matches[0].team_a.hltv_id]
        team_b_players = [p for p in matches[0].players if p.team_hltv_id == matches[0].team_b.hltv_id]
        self.assertEqual(len(team_a_players), 2)
        self.assertEqual(len(team_b_players), 1)

    def test_deduplicates_player_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            players_path = Path(tmp) / "players.csv"

            _write_results_csv(results_path, [
                _sample_results_row(map="Inferno", result="16-8"),
                _sample_results_row(map="Mirage", result="16-10"),
            ])

            # Same player appears twice (once per map)
            with players_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "player_name", "team", "player_id"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "player_name": "device", "team": "Astralis", "player_id": "7592"})
                writer.writerow({"match_id": "99001", "player_name": "device", "team": "Astralis", "player_id": "7592"})

            matches = parse_kaggle_csgo_pro_results_csv(results_path, players_path=players_path)

        # Should be deduplicated to 1
        self.assertEqual(len(matches[0].players), 1)

    def test_players_without_team_match_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            players_path = Path(tmp) / "players.csv"

            _write_results_csv(results_path, [_sample_results_row()])

            with players_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "player_name", "team", "player_id"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "player_name": "device", "team": "Astralis", "player_id": "7592"})
                writer.writerow({"match_id": "99001", "player_name": "unknown", "team": "OtherTeam", "player_id": "9999"})

            matches = parse_kaggle_csgo_pro_results_csv(results_path, players_path=players_path)

        # "OtherTeam" doesn't match either team_a or team_b
        self.assertEqual(len(matches[0].players), 1)


class KaggleCsgoProFixturePayloadTests(unittest.TestCase):
    """Tests for JSON serialisation of parsed matches."""

    def test_payload_records_correct_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [_sample_results_row()])

            match = parse_kaggle_csgo_pro_results_csv(path)[0]

        payload = kaggle_csgo_pro_match_to_fixture_payload(match)

        self.assertEqual(payload["source"]["name"], "kaggle-csgo-pro-matches")
        self.assertIn("kaggle", payload["source"]["url"])
        self.assertEqual(len(payload["maps"]), 1)
        self.assertEqual(payload["maps"][0]["map_name"], "Inferno")

    def test_payload_includes_vetoes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "results.csv"
            picks_path = Path(tmp) / "picks.csv"

            _write_results_csv(results_path, [_sample_results_row()])

            with picks_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "team", "pick_type", "map"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "team": "Astralis", "pick_type": "ban", "map": "Vertigo"})

            match = parse_kaggle_csgo_pro_results_csv(results_path, picks_path=picks_path)[0]

        payload = kaggle_csgo_pro_match_to_fixture_payload(match)

        self.assertEqual(len(payload["vetoes"]), 1)
        self.assertEqual(payload["vetoes"][0]["action"], "ban")
        self.assertEqual(payload["vetoes"][0]["map_name"], "Vertigo")

    def test_normalization_produces_contest_units(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.csv"
            _write_results_csv(path, [
                _sample_results_row(map="Inferno", result="16-8"),
                _sample_results_row(map="Mirage", result="16-10"),
            ])

            match = parse_kaggle_csgo_pro_results_csv(path)[0]

        normalized = normalize_match(match)
        self.assertEqual(len(normalized["contest_units"]), 2)
        self.assertEqual(len(normalized["participants"]), 2)


class KaggleCsgoProCLITests(unittest.TestCase):
    """Tests for the convert-cs-kaggle-pro-matches CLI command."""

    def test_cli_converts_results_to_fixture_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "results.csv"
            out_dir = Path(tmp) / "fixtures"
            _write_results_csv(csv_path, [_sample_results_row()])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["convert-cs-kaggle-pro-matches", "--path", str(csv_path), "--out-dir", str(out_dir)])

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1:])
            fixtures = list(out_dir.glob("*.json"))
            payload = json.loads(fixtures[0].read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(output["matches_converted"], 1)
        self.assertEqual(output["maps_converted"], 1)
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(payload["source"]["name"], "kaggle-csgo-pro-matches")

    def test_cli_with_picks_and_players(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "results.csv"
            picks_path = Path(tmp) / "picks.csv"
            players_path = Path(tmp) / "players.csv"
            out_dir = Path(tmp) / "fixtures"

            _write_results_csv(csv_path, [_sample_results_row()])

            with picks_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "team", "pick_type", "map"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "team": "Astralis", "pick_type": "ban", "map": "Vertigo"})

            with players_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=["match_id", "player_name", "team", "player_id"])
                writer.writeheader()
                writer.writerow({"match_id": "99001", "player_name": "device", "team": "Astralis", "player_id": "7592"})

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main([
                    "convert-cs-kaggle-pro-matches",
                    "--path", str(csv_path),
                    "--picks-path", str(picks_path),
                    "--players-path", str(players_path),
                    "--out-dir", str(out_dir),
                ])

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1:])

        self.assertEqual(code, 0)
        self.assertEqual(output["vetoes_converted"], 1)
        self.assertEqual(output["players_converted"], 1)

    def test_cli_limit_parameter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "results.csv"
            out_dir = Path(tmp) / "fixtures"
            _write_results_csv(csv_path, [
                _sample_results_row(match_id="1"),
                _sample_results_row(match_id="2"),
                _sample_results_row(match_id="3"),
            ])

            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main([
                    "convert-cs-kaggle-pro-matches",
                    "--path", str(csv_path),
                    "--out-dir", str(out_dir),
                    "--limit", "2",
                ])

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1:])

        self.assertEqual(code, 0)
        self.assertEqual(output["matches_converted"], 2)


if __name__ == "__main__":
    unittest.main()
