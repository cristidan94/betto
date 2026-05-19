from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sports.cs.features import materialize_map_glicko
from sports.cs.features.glicko import (
    INITIAL_RATING,
    INITIAL_RD,
    INITIAL_VOLATILITY,
    GlickoState,
    apply_rd_decay,
    update_glicko,
)
from sports.cs.normalization import parse_hltv_payload


def fixture(
    hltv_id: str,
    scheduled_at: str,
    winner_hltv_id: str,
    *,
    map_name: str = "Mirage",
    status: str = "finished",
    team_a_id: str = "1",
    team_b_id: str = "2",
) -> dict[str, object]:
    return {
        "hltv_id": hltv_id,
        "scheduled_at": scheduled_at,
        "best_of": 1,
        "status": status,
        "team_a": {"hltv_id": team_a_id, "name": "NAVI"},
        "team_b": {"hltv_id": team_b_id, "name": "Vitality"},
        "event": {"hltv_id": "100", "name": "Test Event"},
        "players": [],
        "maps": [
            {
                "map_index": 1,
                "map_name": map_name,
                "team_a_score": 13 if winner_hltv_id == team_a_id else 9,
                "team_b_score": 9 if winner_hltv_id == team_a_id else 13,
                "winner_hltv_id": winner_hltv_id,
            }
        ],
    }


class GlickoUnitTests(unittest.TestCase):
    """Tests for the core Glicko-2 update functions."""

    def test_initial_state_defaults(self) -> None:
        state = GlickoState()
        self.assertEqual(state.rating, INITIAL_RATING)
        self.assertEqual(state.rd, INITIAL_RD)
        self.assertEqual(state.volatility, INITIAL_VOLATILITY)
        self.assertIsNone(state.last_updated)

    def test_win_increases_rating(self) -> None:
        state = GlickoState()
        updated = update_glicko(state, INITIAL_RATING, INITIAL_RD, 1.0)
        self.assertGreater(updated.rating, INITIAL_RATING)

    def test_loss_decreases_rating(self) -> None:
        state = GlickoState()
        updated = update_glicko(state, INITIAL_RATING, INITIAL_RD, 0.0)
        self.assertLess(updated.rating, INITIAL_RATING)

    def test_rd_decreases_after_game(self) -> None:
        state = GlickoState()
        updated = update_glicko(state, INITIAL_RATING, INITIAL_RD, 1.0)
        self.assertLess(updated.rd, INITIAL_RD)

    def test_rd_increases_with_inactivity(self) -> None:
        state = GlickoState(rating=1600, rd=100, volatility=0.06, last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc))
        decayed = apply_rd_decay(state, days_inactive=60)
        self.assertGreater(decayed.rd, 100)

    def test_rd_capped_at_initial(self) -> None:
        state = GlickoState(rating=1600, rd=340, volatility=0.06, last_updated=datetime(2026, 1, 1, tzinfo=timezone.utc))
        decayed = apply_rd_decay(state, days_inactive=10000)
        self.assertLessEqual(decayed.rd, INITIAL_RD)

    def test_beating_higher_rated_gives_bigger_gain(self) -> None:
        state = GlickoState()
        gain_vs_equal = update_glicko(state, INITIAL_RATING, 200, 1.0).rating - INITIAL_RATING
        gain_vs_strong = update_glicko(state, 1800, 200, 1.0).rating - INITIAL_RATING
        self.assertGreater(gain_vs_strong, gain_vs_equal)


class MaterializeMapGlickoTests(unittest.TestCase):
    """Tests for the materialize_map_glicko materializer."""

    def test_unknown_team_not_in_output(self) -> None:
        """A team that has never played before as_of does not appear in output."""
        features = materialize_map_glicko([], datetime(2026, 5, 20, tzinfo=timezone.utc))
        self.assertEqual(features, [])

    def test_single_match_updates_both_teams(self) -> None:
        matches = [parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1"))]
        features = materialize_map_glicko(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))

        values = {f.entity_id: f.value for f in features}
        navi = values["cs:participant:hltv:1:map:Mirage"]
        vitality = values["cs:participant:hltv:2:map:Mirage"]

        self.assertGreater(navi["rating"], INITIAL_RATING)
        self.assertLess(vitality["rating"], INITIAL_RATING)

    def test_point_in_time_correctness(self) -> None:
        """Future matches must not affect ratings."""
        matches = [
            parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1")),
            parse_hltv_payload(fixture("m2", "2026-06-01T00:00:00Z", "2")),
        ]

        features_before = materialize_map_glicko(matches, datetime(2026, 5, 10, tzinfo=timezone.utc))
        features_after = materialize_map_glicko(matches, datetime(2026, 7, 1, tzinfo=timezone.utc))

        values_before = {f.entity_id: f.value for f in features_before}
        values_after = {f.entity_id: f.value for f in features_after}

        navi_before = values_before["cs:participant:hltv:1:map:Mirage"]["rating"]
        navi_after = values_after["cs:participant:hltv:1:map:Mirage"]["rating"]

        # After m2 (which NAVI loses), their rating should decrease vs the snapshot before m2
        self.assertGreater(navi_before, INITIAL_RATING)
        self.assertLess(navi_after, navi_before)

    def test_ignores_unfinished_matches(self) -> None:
        matches = [parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1", status="scheduled"))]
        features = materialize_map_glicko(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))
        self.assertEqual(features, [])

    def test_per_map_isolation(self) -> None:
        """Ratings are tracked per-map, not shared across maps."""
        matches = [
            parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1", map_name="Mirage")),
            parse_hltv_payload(fixture("m2", "2026-05-02T00:00:00Z", "2", map_name="Inferno")),
        ]
        features = materialize_map_glicko(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))
        values = {f.entity_id: f.value for f in features}

        # NAVI won on Mirage, lost on Inferno - ratings should differ
        navi_mirage = values["cs:participant:hltv:1:map:Mirage"]["rating"]
        navi_inferno = values["cs:participant:hltv:1:map:Inferno"]["rating"]
        self.assertGreater(navi_mirage, INITIAL_RATING)
        self.assertLess(navi_inferno, INITIAL_RATING)

    def test_rating_convergence_after_many_games(self) -> None:
        """After many games between teams with different strengths, ratings should separate."""
        matches = []
        for i in range(20):
            # Team 1 wins 75% of games
            winner = "1" if i % 4 != 0 else "2"
            matches.append(
                parse_hltv_payload(
                    fixture(f"m{i}", f"2026-05-{(i + 1):02d}T00:00:00Z", winner)
                )
            )

        features = materialize_map_glicko(matches, datetime(2026, 6, 1, tzinfo=timezone.utc))
        values = {f.entity_id: f.value for f in features}

        navi = values["cs:participant:hltv:1:map:Mirage"]
        vitality = values["cs:participant:hltv:2:map:Mirage"]

        # Team 1 (winning 75%) should have higher rating
        self.assertGreater(navi["rating"], vitality["rating"])
        # Both RDs should be well below initial (many games played)
        self.assertLess(navi["rd"], INITIAL_RD)
        self.assertLess(vitality["rd"], INITIAL_RD)

    def test_feature_name_is_correct(self) -> None:
        matches = [parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1"))]
        features = materialize_map_glicko(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))
        for f in features:
            self.assertEqual(f.name, "cs.team.map_glicko")

    def test_value_contains_expected_keys(self) -> None:
        matches = [parse_hltv_payload(fixture("m1", "2026-05-01T00:00:00Z", "1"))]
        features = materialize_map_glicko(matches, datetime(2026, 5, 20, tzinfo=timezone.utc))
        for f in features:
            self.assertIn("rating", f.value)
            self.assertIn("rd", f.value)
            self.assertIn("volatility", f.value)
            self.assertIn("map_name", f.value)

    def test_rd_increases_for_inactive_teams(self) -> None:
        """A team that played long ago should have higher RD than one that played recently."""
        matches = [
            parse_hltv_payload(fixture("m1", "2026-01-01T00:00:00Z", "1")),
            parse_hltv_payload(fixture("m2", "2026-05-01T00:00:00Z", "1", team_a_id="1", team_b_id="3")),
        ]

        features = materialize_map_glicko(matches, datetime(2026, 5, 10, tzinfo=timezone.utc))
        values = {f.entity_id: f.value for f in features}

        # Team 2 last played on Jan 1, team 1 last played on May 1
        # Team 2 RD should be higher because they haven't played in months
        navi_rd = values["cs:participant:hltv:1:map:Mirage"]["rd"]
        vitality_rd = values["cs:participant:hltv:2:map:Mirage"]["rd"]
        self.assertGreater(vitality_rd, navi_rd)


if __name__ == "__main__":
    unittest.main()
