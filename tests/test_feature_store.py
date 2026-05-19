from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.feature_store import FeatureValue, PointInTimeFeatureStore


class PointInTimeFeatureStoreTests(unittest.TestCase):
    def test_get_returns_latest_value_at_or_before_query_time(self) -> None:
        store = PointInTimeFeatureStore()
        store.put(FeatureValue("team-a", "rating", datetime(2026, 1, 1, tzinfo=timezone.utc), 1200))
        store.put(FeatureValue("team-a", "rating", datetime(2026, 1, 10, tzinfo=timezone.utc), 1250))

        value = store.get("team-a", "rating", datetime(2026, 1, 5, tzinfo=timezone.utc))

        self.assertIsNotNone(value)
        self.assertEqual(value.value, 1200)

    def test_get_does_not_leak_future_value(self) -> None:
        store = PointInTimeFeatureStore()
        store.put(FeatureValue("team-a", "rating", datetime(2026, 1, 10, tzinfo=timezone.utc), 1250))

        value = store.get("team-a", "rating", datetime(2026, 1, 5, tzinfo=timezone.utc))

        self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()

