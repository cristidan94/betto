from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from core.entities import Contest
from core.ingestion import FetchResult, SourceAdapter


class FeatureBuilder(Protocol):
    feature_names: tuple[str, ...]

    def materialize(self, as_of: datetime) -> int:
        """Build feature values up to the supplied timestamp and return rows written."""


class MarketResolver(Protocol):
    def resolve(self, question: str, contests: list[Contest]) -> tuple[str | None, float]:
        """Return best contest ID and confidence for an external market question."""


class Simulator(Protocol):
    def price(self, market_type: str, inputs: dict[str, object]) -> dict[str, float]:
        """Return fair probabilities by outcome label."""


@dataclass(frozen=True)
class GamePlugin:
    game_id: str
    source_adapters: tuple[SourceAdapter, ...]
    feature_names: tuple[str, ...]
    supported_targets: tuple[str, ...]

    def fetch_seed_payloads(self, since: datetime) -> list[FetchResult]:
        payloads: list[FetchResult] = []
        for adapter in self.source_adapters:
            payloads.extend(adapter.fetch_since(since))
        return payloads

