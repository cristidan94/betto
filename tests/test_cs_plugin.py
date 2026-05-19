from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sports.cs import GAME_ID
from sports.cs.maps import normalize_map_name
from sports.cs.plugin import build_plugin
from sports.cs.simulation import best_of_series_probability


class CounterStrikePluginTests(unittest.TestCase):
    def test_plugin_declares_sources_features_and_targets(self) -> None:
        plugin = build_plugin()

        self.assertEqual(plugin.game_id, GAME_ID)
        self.assertIn("cs.map_winner", plugin.supported_targets)
        self.assertIn("cs.team.map_win_rate_90d", plugin.feature_names)
        self.assertEqual(len(plugin.fetch_seed_payloads(datetime(2026, 1, 1, tzinfo=timezone.utc))), 2)

    def test_map_name_normalization(self) -> None:
        self.assertEqual(normalize_map_name("de_dust2"), "Dust2")

    def test_best_of_three_probability(self) -> None:
        probability = best_of_series_probability([0.6, 0.6, 0.6])

        self.assertAlmostEqual(probability, 0.648)


if __name__ == "__main__":
    unittest.main()

