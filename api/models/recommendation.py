from __future__ import annotations

from pydantic import BaseModel


class Derivative(BaseModel):
    market: str
    model_prob: float
    market_prob: float
    edge: float
    size: float
    state: str


class Feature(BaseModel):
    label: str
    value: float


class SizingStep(BaseModel):
    label: str
    value: float
    applied: bool


class VetoState(BaseModel):
    state: str
    vetoed: int
    total: int
    maps: list[str]


class MatchContext(BaseModel):
    roster_a: str
    roster_b: str
    stand_ins: str
    timezone_gap: str
    schedule: str
    news_24h: str


class StrategyHealth(BaseModel):
    clv_30d: float
    paper_roi_30d: float
    calibration_ece: float
    drift_ece: float
    days_since_refit: int


class Lineage(BaseModel):
    model: str
    model_hash: str
    feature_snapshot: str
    market_snapshot: str
    backtest_run: int


class RecommendationDetail(BaseModel):
    id: str
    match: str
    market: str
    strategy: str
    model_prob: float
    market_prob: float
    edge: float
    size: float
    confidence: str
    stake_usd: float
    close: str
    format: str
    regime: str
    veto: VetoState
    derivatives: list[Derivative]
    features: list[Feature]
    sizing_trace: list[SizingStep]
    context: MatchContext
    strategy_health: StrategyHealth
    lineage: Lineage
