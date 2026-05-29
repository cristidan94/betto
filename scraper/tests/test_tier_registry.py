from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scraper.tier_registry import (
    allow_list_from_registry,
    describe_registry,
    load_tier_registry,
    tier_overrides_from_registry,
)


SAMPLE_YAML = """\
events:
  - pattern: "IEM Cologne"
    tier: 1
    tags: ["lan", "elite"]
  - pattern: "CCT"
    tier: 2
    tags: ["online"]

allow_list:
  - "IEM Cologne"
  - "CCT"
"""


class TierRegistryTests(unittest.TestCase):
    def test_load_from_yaml(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_YAML)
            f.flush()
            registry = load_tier_registry(Path(f.name))

        self.assertEqual(len(registry["events"]), 2)
        self.assertEqual(registry["events"][0]["pattern"], "IEM Cologne")
        self.assertEqual(registry["events"][0]["tier"], 1)

    def test_load_missing_file_returns_defaults(self) -> None:
        registry = load_tier_registry(Path("nonexistent.yaml"))
        self.assertIn("events", registry)
        self.assertTrue(len(registry["events"]) > 0)

    def test_load_none_returns_defaults(self) -> None:
        registry = load_tier_registry(None)
        self.assertIn("events", registry)

    def test_tier_overrides_from_registry(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_YAML)
            f.flush()
            registry = load_tier_registry(Path(f.name))

        overrides = tier_overrides_from_registry(registry)
        self.assertEqual(overrides["IEM Cologne"], 1)
        self.assertEqual(overrides["CCT"], 2)

    def test_allow_list_from_registry(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_YAML)
            f.flush()
            registry = load_tier_registry(Path(f.name))

        allow_list = allow_list_from_registry(registry)
        self.assertEqual(allow_list, ["IEM Cologne", "CCT"])

    def test_describe_registry(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(SAMPLE_YAML)
            f.flush()
            registry = load_tier_registry(Path(f.name))

        description = describe_registry(registry)
        self.assertEqual(description["event_count"], 2)
        self.assertEqual(description["allow_list_count"], 2)
        self.assertIn(1, description["by_tier"])
        self.assertIn(2, description["by_tier"])

    def test_malformed_yaml_returns_defaults(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("not a dict")
            f.flush()
            registry = load_tier_registry(Path(f.name))

        self.assertIn("events", registry)
        self.assertTrue(len(registry["events"]) > 0)


if __name__ == "__main__":
    unittest.main()
