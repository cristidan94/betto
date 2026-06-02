from __future__ import annotations

from dataclasses import dataclass

from core.markets.models import MarketSnapshot
from core.markets.probability import market_mid_probability


@dataclass(frozen=True)
class SourceOdds:
    source: str
    prob: float
    best_bid: float | None
    best_ask: float | None
    bookmaker: str | None


@dataclass(frozen=True)
class EdgeComparisonRow:
    contest_id: str
    match_label: str
    market_type: str
    outcome: str
    model_prob: float | None
    sources: tuple[SourceOdds, ...]

    @property
    def best_source(self) -> SourceOdds | None:
        if not self.sources:
            return None
        return max(self.sources, key=lambda s: s.prob)

    @property
    def worst_source(self) -> SourceOdds | None:
        if not self.sources:
            return None
        return min(self.sources, key=lambda s: s.prob)

    def edge_for_source(self, source_name: str) -> float | None:
        if self.model_prob is None:
            return None
        for s in self.sources:
            if s.source == source_name:
                return round(self.model_prob - s.prob, 6)
        return None

    @property
    def edge_diff(self) -> float | None:
        """Polymarket edge minus best bookmaker edge (positive = PM has more value)."""
        pm_edge = self.edge_for_source("polymarket")
        odds_edge = self.edge_for_source("oddspapi")
        if pm_edge is not None and odds_edge is not None:
            return round(pm_edge - odds_edge, 6)
        return None


def snapshot_to_source_odds(
    snapshot: MarketSnapshot,
    source: str,
    bookmaker: str | None = None,
) -> SourceOdds:
    prob = market_mid_probability(snapshot)
    return SourceOdds(
        source=source,
        prob=prob,
        best_bid=snapshot.best_bid,
        best_ask=snapshot.best_ask,
        bookmaker=bookmaker,
    )


def build_comparison(
    contest_id: str,
    match_label: str,
    market_type: str,
    outcome: str,
    model_prob: float | None,
    snapshots_by_source: dict[str, MarketSnapshot],
    bookmaker_names: dict[str, str] | None = None,
) -> EdgeComparisonRow:
    sources: list[SourceOdds] = []
    for source_name, snap in snapshots_by_source.items():
        bk = (bookmaker_names or {}).get(source_name)
        try:
            sources.append(snapshot_to_source_odds(snap, source_name, bk))
        except ValueError:
            continue
    return EdgeComparisonRow(
        contest_id=contest_id,
        match_label=match_label,
        market_type=market_type,
        outcome=outcome,
        model_prob=model_prob,
        sources=tuple(sources),
    )
