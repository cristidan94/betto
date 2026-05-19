from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ModelArtifact:
    model_id: str
    game_id: str
    target: str
    git_sha: str
    data_snapshot_id: str
    config_hash: str
    feature_names: tuple[str, ...]
    metrics: dict[str, float]
    artifact_uri: str | None = None
    created_at: datetime | None = None


def write_model_artifact(artifact: ModelArtifact, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "model_id": artifact.model_id,
        "game_id": artifact.game_id,
        "target": artifact.target,
        "git_sha": artifact.git_sha,
        "data_snapshot_id": artifact.data_snapshot_id,
        "config_hash": artifact.config_hash,
        "feature_names": list(artifact.feature_names),
        "metrics": artifact.metrics,
        "artifact_uri": artifact.artifact_uri,
        "created_at": (artifact.created_at or datetime.now(timezone.utc)).isoformat(),
    }
    path = output_dir / f"{artifact.model_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path
