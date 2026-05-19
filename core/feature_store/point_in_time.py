from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FeatureValue:
    entity_id: str
    name: str
    as_of: datetime
    value: Any


class PointInTimeFeatureStore:
    """Small in-memory implementation that encodes the production feature-store contract."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], list[FeatureValue]] = {}

    def put(self, feature: FeatureValue) -> None:
        key = (feature.entity_id, feature.name)
        self._values.setdefault(key, []).append(feature)
        self._values[key].sort(key=lambda item: item.as_of)

    def get(self, entity_id: str, feature_name: str, as_of: datetime) -> FeatureValue | None:
        values = self._values.get((entity_id, feature_name), [])
        result: FeatureValue | None = None
        for value in values:
            if value.as_of <= as_of:
                result = value
            else:
                break
        return result

    def get_many(self, entity_ids: list[str], feature_names: list[str], as_of: datetime) -> dict[tuple[str, str], FeatureValue | None]:
        return {
            (entity_id, feature_name): self.get(entity_id, feature_name, as_of)
            for entity_id in entity_ids
            for feature_name in feature_names
        }

