from __future__ import annotations

import unittest

from sports.cs.models import build_map_winner_dataset
from sports.cs.normalization import parse_hltv_payload


def match(hltv_id: str, scheduled_at: str, winner_hltv_id: str) -> dict[str, object]:
    return {
        "hltv_id": hltv_id,
        "scheduled_at": scheduled_at,
        "best_of": 1,
        "status": "finished",
        "team_a": {"hltv_id": "1", "name": "NAVI"},
        "team_b": {"hltv_id": "2", "name": "Vitality"},
        "event": {"hltv_id": "100", "name": "Fixture Cup"},
        "players": [],
        "maps": [
            {
                "map_index": 1,
                "map_name": "Mirage",
                "team_a_score": 13 if winner_hltv_id == "1" else 9,
                "team_b_score": 9 if winner_hltv_id == "1" else 13,
                "winner_hltv_id": winner_hltv_id,
            }
        ],
    }


class CsDatasetTests(unittest.TestCase):
    def test_build_map_winner_dataset_creates_swapped_rows(self) -> None:
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(match("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(match("m2", "2026-05-10T00:00:00Z", "2")),
            ]
        )

        self.assertEqual(len(rows), 4)
        second_match_rows = [row for row in rows if row.contest_hltv_id == "m2"]
        self.assertEqual({row.target for row in second_match_rows}, {0, 1})

    def test_build_map_winner_dataset_uses_only_prior_matches_for_features(self) -> None:
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(match("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(match("m2", "2026-05-10T00:00:00Z", "2")),
                parse_hltv_payload(match("future", "2026-05-20T00:00:00Z", "2")),
            ]
        )

        navi_m2 = next(row for row in rows if row.contest_hltv_id == "m2" and row.team_id == "cs:participant:hltv:1")
        self.assertEqual(navi_m2.features["team_maps_played_90d"], 1)
        self.assertEqual(navi_m2.features["team_map_win_rate_90d"], 1.0)
        self.assertEqual(navi_m2.features["opponent_map_win_rate_90d"], 0.0)
        self.assertEqual(navi_m2.features["map_win_rate_diff_90d"], 1.0)

    def test_build_map_winner_dataset_adds_match_context_features(self) -> None:
        opening = match("m1", "2026-05-01T00:00:00Z", "1")
        prior_for_navi = match("m2", "2026-05-05T00:00:00Z", "1")
        prior_for_navi["team_b"] = {"hltv_id": "3", "name": "Spirit"}
        featured = match("m3", "2026-05-10T12:00:00Z", "2")
        featured["best_of"] = 3

        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(opening),
                parse_hltv_payload(prior_for_navi),
                parse_hltv_payload(featured),
            ]
        )

        navi_row = next(row for row in rows if row.contest_hltv_id == "m3" and row.team_id == "cs:participant:hltv:1")

        self.assertEqual(navi_row.features["best_of"], 3)
        self.assertEqual(navi_row.features["team_rest_days"], 5.5)
        self.assertEqual(navi_row.features["opponent_rest_days"], 9.5)
        self.assertEqual(navi_row.features["rest_days_diff"], -4.0)

    def test_build_map_winner_dataset_context_features_do_not_use_future_matches(self) -> None:
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(match("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(match("m2", "2026-05-10T00:00:00Z", "2")),
                parse_hltv_payload(match("future", "2026-05-11T00:00:00Z", "1")),
            ]
        )

        navi_m2 = next(row for row in rows if row.contest_hltv_id == "m2" and row.team_id == "cs:participant:hltv:1")

        self.assertEqual(navi_m2.features["team_rest_days"], 9.0)
        self.assertEqual(navi_m2.features["opponent_rest_days"], 9.0)

    def test_build_map_winner_dataset_ignores_unfinished_matches(self) -> None:
        payload = match("m1", "2026-05-01T00:00:00Z", "1")
        payload["status"] = "scheduled"

        rows = build_map_winner_dataset([parse_hltv_payload(payload)])

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
