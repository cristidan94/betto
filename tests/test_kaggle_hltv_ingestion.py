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
    kaggle_hltv_match_to_fixture_payload,
    parse_kaggle_competitive_match_results_csv,
    parse_kaggle_hltv_results_csv,
)
from sports.cs.normalization import normalize_match


class KaggleHltvIngestionTests(unittest.TestCase):
    def test_parses_match_results_csv_with_synthetic_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cs2_results.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "team_won",
                        "team_lost",
                        "stars_of_tournament",
                        "shape",
                        "event_name",
                        "score",
                        "time",
                        "team1",
                        "team2",
                        "target",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "team_won": "NAVI",
                        "team_lost": "Vitality",
                        "stars_of_tournament": "5",
                        "shape": "bo3",
                        "event_name": "IEM Test",
                        "score": "2 - 1",
                        "time": "2024-10-24",
                        "team1": "NAVI",
                        "team2": "Vitality",
                        "target": "1",
                    }
                )

            matches = parse_kaggle_hltv_results_csv(path)

        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].hltv_id.startswith("kaggle-cs2-results-"))
        self.assertEqual(matches[0].best_of, 3)
        self.assertEqual(matches[0].event.tier, "5")
        self.assertEqual(matches[0].maps, ())

        normalized = normalize_match(matches[0])
        self.assertEqual(len(normalized["participants"]), 2)
        self.assertEqual(len(normalized["contest_units"]), 0)

    def test_converts_csv_to_fixture_payloads_from_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "cs2_results.csv"
            out_dir = Path(tmp) / "fixtures"
            csv_path.write_text(
                "\n".join(
                    [
                        "team_won,team_lost,stars_of_tournament,shape,event_name,score,time,team1,team2,target",
                        "NAVI,Vitality,5,bo3,IEM Test,2 - 1,2024-10-24,NAVI,Vitality,1",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["convert-cs-kaggle-hltv-results", "--path", str(csv_path), "--out-dir", str(out_dir)])

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1 :])
            fixtures = list(out_dir.glob("*.json"))
            payload = json.loads(fixtures[0].read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(output["matches_converted"], 1)
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(payload["source"]["name"], "kaggle-hltv-results-cs2")

    def test_fixture_payload_records_source_limitations(self) -> None:
        row = {
            "team_won": "Vitality",
            "team_lost": "NAVI",
            "stars_of_tournament": "5",
            "shape": "bo3",
            "event_name": "IEM Test",
            "score": "1 - 2",
            "time": "2024-10-24",
            "team1": "NAVI",
            "team2": "Vitality",
            "target": "0",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cs2_results.csv"
            path.write_text(",".join(row.keys()) + "\n" + ",".join(row.values()), encoding="utf-8")
            match = parse_kaggle_hltv_results_csv(path)[0]

        payload = kaggle_hltv_match_to_fixture_payload(match)

        self.assertEqual(payload["maps"], [])
        self.assertIn("no real HLTV IDs", payload["source"]["note"])

    def test_parses_competitive_match_results_as_map_level_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "match_results.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "data_unix",
                        "event_name",
                        "map",
                        "match_id",
                        "match_link",
                        "team_1_id",
                        "team_1_name",
                        "team_1_score",
                        "team_2_id",
                        "team_2_name",
                        "team_2_score",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "data_unix": "1716508800",
                        "event_name": "IEM Test",
                        "map": "de_cache",
                        "match_id": "2371001",
                        "match_link": "/matches/2371001/navi-vs-vitality",
                        "team_1_id": "4608",
                        "team_1_name": "NAVI",
                        "team_1_score": "13",
                        "team_2_id": "9565",
                        "team_2_name": "Vitality",
                        "team_2_score": "9",
                    }
                )
                writer.writerow(
                    {
                        "data_unix": "1716508800",
                        "event_name": "IEM Test",
                        "map": "Overpass",
                        "match_id": "2371001",
                        "match_link": "/matches/2371001/navi-vs-vitality",
                        "team_1_id": "4608",
                        "team_1_name": "NAVI",
                        "team_1_score": "10",
                        "team_2_id": "9565",
                        "team_2_name": "Vitality",
                        "team_2_score": "13",
                    }
                )

            matches = parse_kaggle_competitive_match_results_csv(path)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].hltv_id, "2371001")
        self.assertEqual(matches[0].team_a.hltv_id, "4608")
        self.assertEqual(matches[0].best_of, 3)
        self.assertEqual(matches[0].maps[0].map_name, "Cache")
        self.assertEqual(matches[0].maps[0].winner_hltv_id, "4608")
        self.assertEqual(matches[0].maps[1].map_name, "Overpass")
        self.assertEqual(matches[0].maps[1].winner_hltv_id, "9565")

        normalized = normalize_match(matches[0])
        self.assertEqual(len(normalized["contest_units"]), 2)

    def test_converts_competitive_results_from_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "match_results.csv"
            out_dir = Path(tmp) / "fixtures"
            csv_path.write_text(
                "\n".join(
                    [
                        "data_unix,event_name,map,match_id,match_link,team_1_id,team_1_name,team_1_score,team_2_id,team_2_name,team_2_score",
                        "1716508800,IEM Test,Mirage,2371001,/matches/2371001/navi-vs-vitality,4608,NAVI,13,9565,Vitality,9",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(["convert-cs-kaggle-competitive-results", "--path", str(csv_path), "--out-dir", str(out_dir)])

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1 :])
            fixtures = list(out_dir.glob("*.json"))
            payload = json.loads(fixtures[0].read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(output["matches_converted"], 1)
        self.assertEqual(output["maps_converted"], 1)
        self.assertEqual(payload["source"]["name"], "kaggle-counter-strike-competitive-data")
        self.assertEqual(payload["maps"][0]["winner_hltv_id"], "4608")

    def test_competitive_results_can_join_match_players(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "match_results.csv"
            players_path = Path(tmp) / "match_players.csv"
            results_path.write_text(
                "\n".join(
                    [
                        "data_unix,event_name,map,match_id,match_link,team_1_id,team_1_name,team_1_score,team_2_id,team_2_name,team_2_score",
                        "1716508800,IEM Test,Mirage,2371001,/matches/2371001/navi-vs-vitality,4608,NAVI,13,9565,Vitality,9",
                    ]
                ),
                encoding="utf-8",
            )
            players_path.write_text(
                "\n".join(
                    [
                        "match_id,match_link,player_id,player_nick,players_link,team_name,rating",
                        "2371001,/matches/2371001/navi-vs-vitality,7998,s1mple,/player/7998/s1mple,NAVI,1.23",
                        "2371001,/matches/2371001/navi-vs-vitality,11893,ZywOo,/player/11893/zywoo,Vitality,1.19",
                        "9999999,/matches/9999999/other,1,other,/player/1/other,Other,0.9",
                    ]
                ),
                encoding="utf-8",
            )

            matches = parse_kaggle_competitive_match_results_csv(results_path, players_path=players_path)

        self.assertEqual(len(matches[0].players), 2)
        self.assertEqual(matches[0].players[0].hltv_id, "7998")
        self.assertEqual(matches[0].players[0].team_hltv_id, "4608")
        self.assertEqual(matches[0].players[1].team_hltv_id, "9565")

        normalized = normalize_match(matches[0])
        self.assertEqual(len(normalized["participants"]), 4)

    def test_competitive_cli_can_write_players(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results_path = Path(tmp) / "match_results.csv"
            players_path = Path(tmp) / "match_players.csv"
            out_dir = Path(tmp) / "fixtures"
            results_path.write_text(
                "\n".join(
                    [
                        "data_unix,event_name,map,match_id,match_link,team_1_id,team_1_name,team_1_score,team_2_id,team_2_name,team_2_score",
                        "1716508800,IEM Test,Mirage,2371001,/matches/2371001/navi-vs-vitality,4608,NAVI,13,9565,Vitality,9",
                    ]
                ),
                encoding="utf-8",
            )
            players_path.write_text(
                "\n".join(
                    [
                        "match_id,player_id,player_nick,team_name",
                        "2371001,7998,s1mple,NAVI",
                        "2371001,11893,ZywOo,Vitality",
                    ]
                ),
                encoding="utf-8",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                code = main(
                    [
                        "convert-cs-kaggle-competitive-results",
                        "--path",
                        str(results_path),
                        "--players-path",
                        str(players_path),
                        "--out-dir",
                        str(out_dir),
                    ]
                )

            output = json.loads(stdout.getvalue()[stdout.getvalue().rfind("\n{") + 1 :])
            payload = json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(output["players_converted"], 2)
        self.assertEqual(payload["players"][0]["nickname"], "s1mple")
        self.assertEqual(payload["players"][1]["team_hltv_id"], "9565")


if __name__ == "__main__":
    unittest.main()
