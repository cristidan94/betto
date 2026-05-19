from __future__ import annotations

import math
from dataclasses import dataclass

from sports.cs.models.dataset import MapWinnerTrainingRow


@dataclass(frozen=True)
class BaselineScoreBreakdown:
    probability: float
    total_logit: float
    intercept_logit: float
    raw_map_win_rate_diff: float
    sample_confidence: float
    shrink_multiplier: float
    shrunk_map_win_rate_diff: float
    best_of_multiplier: float
    map_strength_logit: float
    rest_days_logit: float
    glicko_logit: float = 0.0


@dataclass(frozen=True)
class BaselineMapWinnerModel:
    intercept: float = 0.0
    win_rate_diff_weight: float = 1.2
    missing_prior_shrink: float = 0.35
    best_of_signal_bonus: float = 0.04
    rest_days_diff_weight: float = 0.10
    rest_days_diff_cap: float = 7.0
    glicko_diff_weight: float = 0.003
    glicko_rd_threshold: float = 300.0
    win_rate_30d_blend: float = 0.25
    win_rate_90d_blend: float = 0.50
    win_rate_180d_blend: float = 0.25

    def predict_one(self, row: MapWinnerTrainingRow) -> float:
        return self.score_one(row).probability

    def score_one(self, row: MapWinnerTrainingRow) -> BaselineScoreBreakdown:
        diff = self._blended_win_rate_diff(row)
        team_played = self._best_sample_count(row, "team")
        opponent_played = self._best_sample_count(row, "opponent")
        confidence = min(float(team_played), float(opponent_played), 10.0) / 10.0
        shrink_multiplier = self.missing_prior_shrink + (1 - self.missing_prior_shrink) * confidence
        shrunk_diff = diff * shrink_multiplier
        best_of_multiplier = self._best_of_signal_multiplier(row)
        context_scaled_diff = shrunk_diff * best_of_multiplier
        map_strength_logit = self.win_rate_diff_weight * context_scaled_diff
        rest_days_logit = self._rest_days_signal(row)
        glicko_logit = self._glicko_signal(row)
        total_logit = self.intercept + map_strength_logit + rest_days_logit + glicko_logit
        return BaselineScoreBreakdown(
            probability=_sigmoid(total_logit),
            total_logit=total_logit,
            intercept_logit=self.intercept,
            raw_map_win_rate_diff=diff,
            sample_confidence=confidence,
            shrink_multiplier=shrink_multiplier,
            shrunk_map_win_rate_diff=shrunk_diff,
            best_of_multiplier=best_of_multiplier,
            map_strength_logit=map_strength_logit,
            rest_days_logit=rest_days_logit,
            glicko_logit=glicko_logit,
        )

    def predict(self, rows: list[MapWinnerTrainingRow]) -> list[float]:
        return [self.predict_one(row) for row in rows]

    def score(self, rows: list[MapWinnerTrainingRow]) -> list[BaselineScoreBreakdown]:
        return [self.score_one(row) for row in rows]

    def _blended_win_rate_diff(self, row: MapWinnerTrainingRow) -> float:
        diff_30d = row.features.get("map_win_rate_diff_30d")
        diff_90d = row.features.get("map_win_rate_diff_90d")
        diff_180d = row.features.get("map_win_rate_diff_180d")

        available: list[tuple[float, float]] = []
        if isinstance(diff_30d, (int, float)):
            available.append((self.win_rate_30d_blend, float(diff_30d)))
        if isinstance(diff_90d, (int, float)):
            available.append((self.win_rate_90d_blend, float(diff_90d)))
        if isinstance(diff_180d, (int, float)):
            available.append((self.win_rate_180d_blend, float(diff_180d)))

        if not available:
            return 0.0
        total_weight = sum(w for w, _ in available)
        return sum(w * v for w, v in available) / total_weight

    def _best_sample_count(self, row: MapWinnerTrainingRow, prefix: str) -> int:
        best = 0
        for suffix in ("30d", "90d", "180d"):
            val = row.features.get(f"{prefix}_maps_played_{suffix}")
            if isinstance(val, (int, float)) and int(val) > best:
                best = int(val)
        return best

    def _best_of_signal_multiplier(self, row: MapWinnerTrainingRow) -> float:
        best_of = row.features.get("best_of")
        if not isinstance(best_of, (int, float)):
            return 1.0
        return 1.0 + max(0.0, min(float(best_of) - 1.0, 4.0)) * self.best_of_signal_bonus

    def _rest_days_signal(self, row: MapWinnerTrainingRow) -> float:
        rest_days_diff = row.features.get("rest_days_diff")
        if not isinstance(rest_days_diff, (int, float)):
            return 0.0
        capped_diff = max(-self.rest_days_diff_cap, min(float(rest_days_diff), self.rest_days_diff_cap))
        return self.rest_days_diff_weight * (capped_diff / self.rest_days_diff_cap)

    def _glicko_signal(self, row: MapWinnerTrainingRow) -> float:
        team_rating = row.features.get("team_map_glicko_rating")
        opponent_rating = row.features.get("opponent_map_glicko_rating")
        if not isinstance(team_rating, (int, float)) or not isinstance(opponent_rating, (int, float)):
            return 0.0
        rating_diff = float(team_rating) - float(opponent_rating)
        team_rd = row.features.get("team_map_glicko_rd")
        opponent_rd = row.features.get("opponent_map_glicko_rd")
        if isinstance(team_rd, (int, float)) and isinstance(opponent_rd, (int, float)):
            avg_rd = (float(team_rd) + float(opponent_rd)) / 2.0
            rd_confidence = max(0.0, 1.0 - avg_rd / self.glicko_rd_threshold)
        else:
            rd_confidence = 0.5
        return self.glicko_diff_weight * rating_diff * rd_confidence


def _sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-value))
