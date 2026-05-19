from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sports.cs.features import materialize_map_win_rate_90d
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


class CsFeatureTests(unittest.TestCase):
    def test_materialize_map_win_rate_uses_only_prior_90_days(self) -> None:
        matches = [
            parse_hltv_payload(fixture("old", "2026-01-01T00:00:00Z", "2")),
            parse_hltv_payload(fixture("prior-win", "2026-05-01T00:00:00Z", "1")),
            parse_hltv_payload(fixture("prior-loss", "2026-05-10T00:00:00Z", "2")),
            parse_hltv_payload(fixture("future", "2026-06-01T00:00:00Z", "1")),
        ]

        features = materialize_map_win_rate_90d(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))
        values = {feature.entity_id: feature.value for feature in features}

        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["maps_played"], 2)
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["wins"], 1)
        self.assertEqual(values["cs:participant:hltv:1:map:Mirage"]["win_rate"], 0.5)
        self.assertEqual(values["cs:participant:hltv:2:map:Mirage"]["wins"], 1)

    def test_materialize_map_win_rate_ignores_unfinished_matches(self) -> None:
        payload = fixture("live", "2026-05-01T00:00:00Z", "1")
        payload["status"] = "scheduled"

        features = materialize_map_win_rate_90d([parse_hltv_payload(payload)], datetime(2026, 5, 20, tzinfo=timezone.utc))

        self.assertEqual(features, [])


if __name__ == "__main__":
    unittest.main()

