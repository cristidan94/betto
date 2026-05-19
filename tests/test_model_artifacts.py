from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.modeling import ModelArtifact, write_model_artifact


class ModelArtifactTests(unittest.TestCase):
    def test_write_model_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_model_artifact(
                ModelArtifact(
                    model_id="model-1",
                    game_id="counter_strike",
                    target="cs.map_winner",
                    git_sha="abc",
                    data_snapshot_id="snapshot",
                    config_hash="config",
                    feature_names=("f1",),
                    metrics={"brier_score": 0.2},
                ),
                Path(tmp),
            )

            payload = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["model_id"], "model-1")
            self.assertEqual(payload["feature_names"], ["f1"])
            self.assertEqual(payload["metrics"]["brier_score"], 0.2)


if __name__ == "__main__":
    unittest.main()

