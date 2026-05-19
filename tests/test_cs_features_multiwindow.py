from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sports.cs.features import (
    materialize_map_win_rate,
    materialize_map_win_rate_30d,
    materialize_map_win_rate_90d,
    materialize_map_win_rate_180d,
)
from sports.cs.models import build_map_winner_dataset
from sports.cs.normalization import parse_hltv_payload


def fixture(hltv_id: str, scheduled_at: str, winner_hltv_id: str) -> dict[str, object]:
    return {
        "hltv_id": hltv_id,
        "scheduled_at": scheduled_at,
        "best_of": 1,
        "status": "finished",
        "team_a": {"hltv_id": "1", "name": "NAVI"},
        "team_b": {"hltv_id": "2", "name": "Vitality"},
        "event": {"hltv_id": "100", "name": "Test Event"},
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


class CsFeature30dTests(unittest.TestCase):
    def test_materialize_map_win_rate_30d_excludes_matches_outside_30_days(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            # 35 days before as_of -- outside 30-day window
            parse_hltv_payload(fixture("old", "2026-04-15T00:00:00Z", "1")),
            # 10 days before as_of -- inside 30-day window
            parse_hltv_payload(fixture("recent", "2026-05-10T00:00:00Z", "2")),
        ]

        features = materialize_map_win_rate_30d(matches, as_of)
        values = {feature.entity_id: feature.value for feature in features}

        # Only the recent match should be counted.
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["maps_played"], 1)
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["wins"], 0)
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["win_rate"], 0.0)
        self.assertEqual(values["cs:participant:hltv:2:map:Mirage"]["wins"], 1)

    def test_materialize_map_win_rate_30d_includes_match_at_boundary(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            # Exactly 30 days before as_of -- should be included (window_start <= scheduled_at)
            parse_hltv_payload(fixture("boundary", "2026-04-20T00:00:00Z", "1")),
        ]

        features = materialize_map_win_rate_30d(matches, as_of)
        values = {feature.entity_id: feature.value for feature in features}

        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["maps_played"], 1)


class CsFeature180dTests(unittest.TestCase):
    def test_materialize_map_win_rate_180d_includes_matches_in_wider_window(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            # 150 days before as_of -- outside 90d window but inside 180d window
            parse_hltv_payload(fixture("old", "2025-12-22T00:00:00Z", "1")),
            # 10 days before as_of -- inside all windows
            parse_hltv_payload(fixture("recent", "2026-05-10T00:00:00Z", "2")),
        ]

        features_90d = materialize_map_win_rate_90d(matches, as_of)
        features_180d = materialize_map_win_rate_180d(matches, as_of)

        values_90d = {f.entity_id: f.value for f in features_90d}
        values_180d = {f.entity_id: f.value for f in features_180d}

        # 90d should only see the recent match
        self.assertEqual(values_90d["cs:participant:hltv:1:map:Mirage"]["maps_played"], 1)
        # 180d should see both matches
        self.assertEqual(values_180d["cs:participant:hltv:1:map:Mirage"]["maps_played"], 2)
        self.assertEqual(values_180d["cs:participant:hltv:1:map:Mirage"]["wins"], 1)

    def test_materialize_map_win_rate_180d_excludes_matches_outside_180_days(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            # ~200 days before as_of -- outside 180-day window
            parse_hltv_payload(fixture("very-old", "2025-11-01T00:00:00Z", "1")),
            # 10 days before as_of
            parse_hltv_payload(fixture("recent", "2026-05-10T00:00:00Z", "2")),
        ]

        features = materialize_map_win_rate_180d(matches, as_of)
        values = {f.entity_id: f.value for f in features}

        # Only the recent match should count
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["maps_played"], 1)
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["wins"], 0)


class CsGenericMaterializerTests(unittest.TestCase):
    def test_materialize_map_win_rate_generic_delegates_correctly(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            parse_hltv_payload(fixture("m1", "2026-05-10T00:00:00Z", "1")),
        ]

        features_generic = materialize_map_win_rate(matches, as_of, days=90)
        features_90d = materialize_map_win_rate_90d(matches, as_of)

        # The generic function with days=90 should produce the same values as the 90d wrapper.
        generic_values = {f.entity_id: f.value for f in features_generic}
        wrapper_values = {f.entity_id: f.value for f in features_90d}

        self.assertEqual(generic_values, wrapper_values)

    def test_materialize_map_win_rate_feature_name_includes_day_count(self) -> None:
        as_of = datetime(2026, 5, 20, tzinfo=timezone.utc)
        matches = [
            parse_hltv_payload(fixture("m1", "2026-05-10T00:00:00Z", "1")),
        ]

        features_30d = materialize_map_win_rate_30d(matches, as_of)
        features_90d = materialize_map_win_rate_90d(matches, as_of)
        features_180d = materialize_map_win_rate_180d(matches, as_of)

        self.assertTrue(all(f.name == "cs.team.map_win_rate_30d" for f in features_30d))
        self.assertTrue(all(f.name == "cs.team.map_win_rate_90d" for f in features_90d))
        self.assertTrue(all(f.name == "cs.team.map_win_rate_180d" for f in features_180d))


class CsDatasetMultiwindowTests(unittest.TestCase):
    def test_dataset_includes_30d_and_180d_feature_columns(self) -> None:
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(fixture("m2", "2026-05-10T00:00:00Z", "2")),
            ]
        )

        # m2 rows should have features from m1 as prior data.
        m2_rows = [row for row in rows if row.contest_hltv_id == "m2"]
        self.assertGreater(len(m2_rows), 0)

        expected_keys = {
            "team_map_win_rate_30d",
            "team_maps_played_30d",
            "opponent_map_win_rate_30d",
            "opponent_maps_played_30d",
            "map_win_rate_diff_30d",
            "team_map_win_rate_90d",
            "team_maps_played_90d",
            "opponent_map_win_rate_90d",
            "opponent_maps_played_90d",
            "map_win_rate_diff_90d",
            "team_map_win_rate_180d",
            "team_maps_played_180d",
            "opponent_map_win_rate_180d",
            "opponent_maps_played_180d",
            "map_win_rate_diff_180d",
        }

        for row in m2_rows:
            self.assertTrue(expected_keys.issubset(row.features.keys()), f"Missing keys: {expected_keys - row.features.keys()}")

    def test_dataset_30d_and_180d_values_are_correct(self) -> None:
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(fixture("m2", "2026-05-10T00:00:00Z", "2")),
            ]
        )

        navi_m2 = next(row for row in rows if row.contest_hltv_id == "m2" and row.team_id == "cs:participant:hltv:1")

        # m1 is 9 days before m2, so it falls within all windows (30d, 90d, 180d).
        self.assertEqual(navi_m2.features["team_map_win_rate_30d"], 1.0)
        self.assertEqual(navi_m2.features["team_maps_played_30d"], 1)
        self.assertEqual(navi_m2.features["opponent_map_win_rate_30d"], 0.0)
        self.assertEqual(navi_m2.features["opponent_maps_played_30d"], 1)
        self.assertEqual(navi_m2.features["map_win_rate_diff_30d"], 1.0)

        self.assertEqual(navi_m2.features["team_map_win_rate_180d"], 1.0)
        self.assertEqual(navi_m2.features["team_maps_played_180d"], 1)
        self.assertEqual(navi_m2.features["opponent_map_win_rate_180d"], 0.0)
        self.assertEqual(navi_m2.features["opponent_maps_played_180d"], 1)
        self.assertEqual(navi_m2.features["map_win_rate_diff_180d"], 1.0)

    def test_dataset_preserves_existing_90d_features(self) -> None:
        """Ensure that the existing 90d features are still present and unchanged."""
        rows = build_map_winner_dataset(
            [
                parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1")),
                parse_hltv_payload(fixture("m2", "2026-05-10T00:00:00Z", "2")),
            ]
        )

        navi_m2 = next(row for row in rows if row.contest_hltv_id == "m2" and row.team_id == "cs:participant:hltv:1")
        self.assertEqual(navi_m2.features["team_maps_played_90d"], 1)
        self.assertEqual(navi_m2.features["team_map_win_rate_90d"], 1.0)
        self.assertEqual(navi_m2.features["opponent_map_win_rate_90d"], 0.0)
        self.assertEqual(navi_m2.features["map_win_rate_diff_90d"], 1.0)


if __name__ == "__main__":
    unittest.main()
