from __future__ import annotations

import unittest
from datetime import datetime

from sports.cs.models import BaselineMapWinnerModel, MapWinnerTrainingRow


def row(
    diff: float | None,
    team_played: int = 10,
    opponent_played: int = 10,
    best_of: int | None = None,
    rest_days_diff: float | None = None,
    **extra_features: float | int | None,
) -> MapWinnerTrainingRow:
    features: dict[str, float | int | None] = {
        "map_win_rate_diff_90d": diff,
        "team_maps_played_90d": team_played,
        "opponent_maps_played_90d": opponent_played,
    }
    if best_of is not None:
        features["best_of"] = best_of
    if rest_days_diff is not None:
        features["rest_days_diff"] = rest_days_diff
    features.update(extra_features)
    return MapWinnerTrainingRow(
        contest_hltv_id="m1",
        map_index=1,
        map_name="Mirage",
        as_of=datetime(2026, 5, 1),
        team_id="team-a",
        opponent_id="team-b",
        target=1,
        features=features,
    )


class BaselineModelTests(unittest.TestCase):
    def test_positive_diff_increases_probability(self) -> None:
        model = BaselineMapWinnerModel()

        self.assertGreater(model.predict_one(row(0.4)), model.predict_one(row(-0.4)))

    def test_missing_diff_returns_neutral_probability(self) -> None:
        model = BaselineMapWinnerModel()

        self.assertAlmostEqual(model.predict_one(row(None)), 0.5)

    def test_low_sample_size_shrinks_toward_neutral(self) -> None:
        model = BaselineMapWinnerModel()

        mature = model.predict_one(row(0.5, 10, 10))
        sparse = model.predict_one(row(0.5, 1, 1))

        self.assertGreater(mature, sparse)
        self.assertGreater(sparse, 0.5)

    def test_best_of_context_amplifies_existing_map_signal(self) -> None:
        model = BaselineMapWinnerModel()

        bo1 = model.predict_one(row(0.4, best_of=1))
        bo3 = model.predict_one(row(0.4, best_of=3))

        self.assertGreater(bo3, bo1)

    def test_rest_days_context_adjusts_probability_conservatively(self) -> None:
        model = BaselineMapWinnerModel()

        rested = model.predict_one(row(0.0, rest_days_diff=5.0))
        tired = model.predict_one(row(0.0, rest_days_diff=-5.0))

        self.assertGreater(rested, 0.5)
        self.assertLess(tired, 0.5)
        self.assertLess(rested - tired, 0.1)

    def test_rest_days_context_is_capped(self) -> None:
        model = BaselineMapWinnerModel()

        moderate_rest = model.predict_one(row(0.0, rest_days_diff=7.0))
        extreme_rest = model.predict_one(row(0.0, rest_days_diff=30.0))

        self.assertEqual(moderate_rest, extreme_rest)

    def test_score_breakdown_matches_prediction(self) -> None:
        model = BaselineMapWinnerModel()
        sample = row(0.4, best_of=3, rest_days_diff=2.0)

        score = model.score_one(sample)

        self.assertEqual(score.probability, model.predict_one(sample))
        self.assertGreater(score.best_of_multiplier, 1.0)
        self.assertGreater(score.map_strength_logit, 0.0)
        self.assertGreater(score.rest_days_logit, 0.0)


    def test_glicko_positive_diff_increases_probability(self) -> None:
        model = BaselineMapWinnerModel()
        strong = row(None, team_map_glicko_rating=1700.0, opponent_map_glicko_rating=1400.0,
                      team_map_glicko_rd=80.0, opponent_map_glicko_rd=80.0)
        weak = row(None, team_map_glicko_rating=1400.0, opponent_map_glicko_rating=1700.0,
                    team_map_glicko_rd=80.0, opponent_map_glicko_rd=80.0)
        self.assertGreater(model.predict_one(strong), 0.5)
        self.assertLess(model.predict_one(weak), 0.5)

    def test_glicko_high_rd_reduces_signal(self) -> None:
        model = BaselineMapWinnerModel()
        low_rd = row(None, team_map_glicko_rating=1700.0, opponent_map_glicko_rating=1400.0,
                      team_map_glicko_rd=50.0, opponent_map_glicko_rd=50.0)
        high_rd = row(None, team_map_glicko_rating=1700.0, opponent_map_glicko_rating=1400.0,
                       team_map_glicko_rd=250.0, opponent_map_glicko_rd=250.0)
        self.assertGreater(model.predict_one(low_rd), model.predict_one(high_rd))

    def test_glicko_missing_returns_neutral(self) -> None:
        model = BaselineMapWinnerModel()
        no_glicko = row(None)
        self.assertAlmostEqual(model.predict_one(no_glicko), 0.5)

    def test_multi_window_blending(self) -> None:
        model = BaselineMapWinnerModel()
        only_90 = row(0.3, 10, 10)
        all_windows = row(0.3, 10, 10,
                          map_win_rate_diff_30d=0.6,
                          team_maps_played_30d=5,
                          opponent_maps_played_30d=5,
                          map_win_rate_diff_180d=0.1,
                          team_maps_played_180d=20,
                          opponent_maps_played_180d=20)
        p_90_only = model.predict_one(only_90)
        p_blended = model.predict_one(all_windows)
        self.assertGreater(p_blended, 0.5)
        self.assertNotAlmostEqual(p_90_only, p_blended, places=3)

    def test_glicko_combined_with_win_rate(self) -> None:
        model = BaselineMapWinnerModel()
        wr_only = row(0.3, 10, 10)
        wr_plus_glicko = row(0.3, 10, 10,
                              team_map_glicko_rating=1650.0,
                              opponent_map_glicko_rating=1450.0,
                              team_map_glicko_rd=100.0,
                              opponent_map_glicko_rd=100.0)
        self.assertGreater(model.predict_one(wr_plus_glicko), model.predict_one(wr_only))

    def test_score_breakdown_includes_glicko(self) -> None:
        model = BaselineMapWinnerModel()
        r = row(0.3, 10, 10,
                team_map_glicko_rating=1600.0,
                opponent_map_glicko_rating=1500.0,
                team_map_glicko_rd=100.0,
                opponent_map_glicko_rd=100.0)
        score = model.score_one(r)
        self.assertGreater(score.glicko_logit, 0.0)
        self.assertEqual(score.probability, model.predict_one(r))


if __name__ == "__main__":
    unittest.main()
