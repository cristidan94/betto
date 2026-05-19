from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from core.modeling import ModelArtifact, brier_score, calibration_buckets, expected_calibration_error, log_loss, write_model_artifact
from sports.cs import GAME_ID
from sports.cs.models.baseline import BaselineMapWinnerModel
from sports.cs.models.dataset import build_map_winner_dataset
from sports.cs.normalization import parse_hltv_fixture


@dataclass(frozen=True)
class BaselineEvaluationResult:
    rows: int
    metrics: dict[str, float]
    artifact: ModelArtifact
    artifact_path: Path | None


def evaluate_baseline_from_fixtures(fixture_paths: list[Path], artifact_dir: Path | None = None) -> BaselineEvaluationResult:
    matches = [parse_hltv_fixture(path) for path in fixture_paths]
    rows = build_map_winner_dataset(matches)
    if not rows:
        raise ValueError("no training rows could be built from fixtures")
    model = BaselineMapWinnerModel()
    predictions = model.predict(rows)
    targets = [row.target for row in rows]
    metrics = {
        "brier_score": brier_score(predictions, targets),
        "log_loss": log_loss(predictions, targets),
        "expected_calibration_error": expected_calibration_error(predictions, targets),
    }
    artifact = build_baseline_model_artifact(fixture_paths, metrics)
    artifact_path = None
    if artifact_dir is not None:
        artifact_path = write_model_artifact(artifact, artifact_dir)
        artifact = ModelArtifact(
            model_id=artifact.model_id,
            game_id=artifact.game_id,
            target=artifact.target,
            git_sha=artifact.git_sha,
            data_snapshot_id=artifact.data_snapshot_id,
            config_hash=artifact.config_hash,
            feature_names=artifact.feature_names,
            metrics=artifact.metrics,
            artifact_uri=str(artifact_path),
            created_at=artifact.created_at,
        )
    return BaselineEvaluationResult(rows=len(rows), metrics=metrics, artifact=artifact, artifact_path=artifact_path)


def build_baseline_model_artifact(fixture_paths: list[Path], metrics: dict[str, float]) -> ModelArtifact:
    model = BaselineMapWinnerModel()
    return ModelArtifact(
        model_id=f"cs-baseline-map-winner-{_fingerprint(fixture_paths, metrics)}",
        game_id=GAME_ID,
        target="cs.map_winner",
        git_sha="unknown",
        data_snapshot_id=_fingerprint(fixture_paths, {}),
        config_hash=_fingerprint([], asdict(model)),
        feature_names=(
            "best_of",
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
            "team_map_glicko_rating",
            "team_map_glicko_rd",
            "opponent_map_glicko_rating",
            "opponent_map_glicko_rd",
            "map_glicko_rating_diff",
            "team_rest_days",
            "opponent_rest_days",
            "rest_days_diff",
        ),
        metrics=metrics,
    )


def calibration_payload_from_fixtures(fixture_paths: list[Path]) -> list[dict[str, object]]:
    matches = [parse_hltv_fixture(path) for path in fixture_paths]
    rows = build_map_winner_dataset(matches)
    predictions = BaselineMapWinnerModel().predict(rows)
    targets = [row.target for row in rows]
    return [asdict(bucket) for bucket in calibration_buckets(predictions, targets)]


def _fingerprint(paths: list[Path], payload: object) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(str(path).encode("utf-8"))
        if path.exists():
            digest.update(path.read_bytes())
    digest.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
    return digest.hexdigest()[:16]
