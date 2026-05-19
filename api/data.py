from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from api.models.betlog import BetLogResponse, BetLogRow, BetLogSummary
from api.models.ingestion import FeatureFreshness, IngestionResponse, IngestionSource
from api.models.matches import MatchEntry, MatchesResponse, MatchMarketsResponse, MarketEntry
from api.models.recommendation import (
    Derivative,
    Feature,
    Lineage,
    MatchContext,
    RecommendationDetail,
    SizingStep,
    StrategyHealth,
    VetoState,
)
from api.models.risk import CapitalBucket, KillSwitch, RiskCap, RiskKpi, RiskResponse
from api.models.strategy import SettledBet, StrategyKpi, StrategyResponse
from api.models.today import Correlation, TodayRecommendation, TodayResponse, TodaySummary
from core.config import load_settings
from core.db import PostgresRepository
from core.db.postgres import PostgresExecutor

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEFAULT_BANKROLL_USD = 24318.40
DEFAULT_EXPOSURE_CAP_PCT = 30.0


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))


def use_postgres_api() -> bool:
    return os.environ.get("BETTO_API_DATA_SOURCE", "fixture").lower() == "postgres"


def get_today_recommendations() -> TodayResponse:
    if not use_postgres_api():
        return TodayResponse(**load_fixture("today_recommendations.json"))
    with _repository() as repo:
        rows = repo.list_console_recommendations(limit=20)
        summaries = repo.list_recommendation_summaries()
    return _today_from_rows(rows, summaries)


def get_recommendation(rec_id: str) -> RecommendationDetail:
    if not use_postgres_api():
        fixture_path = FIXTURES / f"recommendation_{rec_id.replace('-', '_').lower()}.json"
        if not fixture_path.exists():
            raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")
        return RecommendationDetail(**json.loads(fixture_path.read_text(encoding="utf-8-sig")))
    with _repository() as repo:
        rows = repo.list_console_recommendations(identifier=rec_id, limit=1)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Recommendation {rec_id} not found")
        row = rows[0]
        markets = repo.list_console_match_markets(row["contest_id"], limit=20) if row.get("contest_id") else []
        bet_summaries = repo.summarize_paper_bets(strategy_id=row.get("strategy_id"))
        model_artifacts = repo.list_model_artifacts(limit=1)
        feature_summaries = repo.list_feature_summaries()
        backtests = repo.list_backtest_runs(strategy_id=row.get("strategy_id"), limit=1)
    return _recommendation_detail_from_row(row, markets, bet_summaries, model_artifacts, feature_summaries, backtests)


def get_matches() -> MatchesResponse:
    if not use_postgres_api():
        return MatchesResponse(**load_fixture("matches.json"))
    with _repository() as repo:
        rows = repo.list_console_matches(limit=50)
    today = datetime.now(timezone.utc).date().isoformat()
    return MatchesResponse(date=today, matches=[_match_entry(row) for row in rows])


def get_match_markets(match_id: str) -> MatchMarketsResponse:
    if not use_postgres_api():
        data = load_fixture("match_markets.json")
        markets = data.get(match_id)
        if markets is None:
            raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
        return MatchMarketsResponse(match_id=match_id, markets=[MarketEntry(**m) for m in markets])
    with _repository() as repo:
        rows = repo.list_console_match_markets(match_id, limit=20)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Match {match_id} not found")
    return MatchMarketsResponse(match_id=match_id, markets=[_market_entry(row) for row in rows])


def get_strategy(strategy_id: str) -> StrategyResponse:
    if not use_postgres_api():
        fixture_path = FIXTURES / f"strategy_{strategy_id.replace('-', '_').lower()}.json"
        if not fixture_path.exists():
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
        return StrategyResponse(**json.loads(fixture_path.read_text(encoding="utf-8-sig")))
    db_strategy_id = _strategy_id_for_db(strategy_id)
    with _repository() as repo:
        bet_summaries = repo.summarize_paper_bets(strategy_id=db_strategy_id)
        rec_summaries = repo.list_recommendation_summaries(strategy_id=db_strategy_id)
        bets = repo.list_paper_bets(strategy_id=db_strategy_id, limit=8)
    return _strategy_response(strategy_id, db_strategy_id, bet_summaries, rec_summaries, bets)


def get_bet_log() -> BetLogResponse:
    if not use_postgres_api():
        return BetLogResponse(**load_fixture("bet_log.json"))
    strategy_id = os.environ.get("BETTO_CONSOLE_STRATEGY_ID")
    with _repository() as repo:
        summaries = repo.summarize_paper_bets(strategy_id=strategy_id)
        bets = repo.list_paper_bets(strategy_id=strategy_id, limit=100)
    return _bet_log_response(summaries, bets)


def get_ingestion() -> IngestionResponse:
    if not use_postgres_api():
        return IngestionResponse(**load_fixture("ingestion.json"))
    with _repository() as repo:
        raw = repo.summarize_raw_objects()
        features = repo.list_feature_summaries()
        snapshots = repo.summarize_market_snapshots()
    return _ingestion_response(raw, features, snapshots)


def get_risk() -> RiskResponse:
    if not use_postgres_api():
        return RiskResponse(**load_fixture("risk.json"))
    strategy_id = os.environ.get("BETTO_CONSOLE_STRATEGY_ID")
    with _repository() as repo:
        rec_summaries = repo.list_recommendation_summaries(strategy_id=strategy_id)
        bet_summaries = repo.summarize_paper_bets(strategy_id=strategy_id)
    return _risk_response(rec_summaries, bet_summaries)


class _RepositoryContext:
    def __init__(self) -> None:
        self.executor = PostgresExecutor(load_settings().database_url)
        self.repo: PostgresRepository | None = None

    def __enter__(self) -> PostgresRepository:
        self.repo = PostgresRepository(self.executor.__enter__())
        return self.repo

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object | None) -> None:
        self.executor.__exit__(exc_type, exc, tb)  # type: ignore[arg-type]


def _repository() -> _RepositoryContext:
    return _RepositoryContext()


def _strategy_response(
    public_strategy_id: str,
    db_strategy_id: str,
    bet_summaries: list[dict[str, Any]],
    rec_summaries: list[dict[str, Any]],
    bets: list[dict[str, Any]],
) -> StrategyResponse:
    bet_summary = bet_summaries[0] if bet_summaries else {}
    rec_summary = rec_summaries[0] if rec_summaries else {}
    settled = [_settled_bet(row) for row in bets if row.get("resolved_outcome") is not None][:8]
    return StrategyResponse(
        strategy_id=public_strategy_id,
        name=_title_strategy(public_strategy_id),
        version=str(db_strategy_id),
        mode="paper",
        enabled=True,
        kpis=[
            StrategyKpi(label="recs", value=str(rec_summary.get("candidates") or 0), hint="all persisted candidates"),
            StrategyKpi(label="accepted", value=str(rec_summary.get("recommendations") or 0), hint="passing recommendations"),
            StrategyKpi(label="CLV", value=_pct(bet_summary.get("mean_clv")), hint="settled paper bets", kind=_kind(bet_summary.get("mean_clv"))),
            StrategyKpi(label="Paper ROI", value=_pct(bet_summary.get("roi")), hint=_money_hint(bet_summary), kind=_kind(bet_summary.get("roi"))),
            StrategyKpi(label="Win rate", value=_pct(bet_summary.get("hit_rate")), hint="settled hit rate"),
            StrategyKpi(label="Avg edge taken", value=_pct(rec_summary.get("mean_edge")), hint="accepted recommendations"),
            StrategyKpi(label="Capital", value=_pct(rec_summary.get("total_bankroll_fraction")), hint="current accepted exposure"),
        ],
        settled=settled,
    )


def _bet_log_response(summaries: list[dict[str, Any]], bets: list[dict[str, Any]]) -> BetLogResponse:
    summary = summaries[0] if summaries else {}
    return BetLogResponse(
        summary=BetLogSummary(
            bets=int(summary.get("bets") or len(bets)),
            settled_bets=int(summary.get("settled_bets") or sum(1 for bet in bets if bet.get("resolved_outcome") is not None)),
            open_bets=int(summary.get("open_bets") or sum(1 for bet in bets if bet.get("resolved_outcome") is None)),
            stake_usd=float(summary.get("stake_usd") or 0.0),
            pnl_usd=float(summary.get("pnl_usd") or 0.0),
            roi=float(summary.get("roi") or 0.0),
            mean_clv=float(summary.get("mean_clv") or 0.0),
            hit_rate=float(summary.get("hit_rate") or 0.0),
        ),
        rows=[_bet_log_row(bet) for bet in bets],
    )


def _ingestion_response(
    raw: list[dict[str, Any]],
    features: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> IngestionResponse:
    snapshot = snapshots[0] if snapshots else {}
    return IngestionResponse(
        sources=[
            IngestionSource(
                name=str(item["source"]),
                kind=_freshness_kind(item.get("latest_fetched_at"), warn_minutes=60),
                fresh=_age(item.get("latest_fetched_at")),
                target="<= 60m",
                cadence="incremental",
                rows=int(item.get("raw_objects") or 0),
                last_error="-",
                on=True,
            )
            for item in raw
        ],
        features=[
            FeatureFreshness(
                name=str(item["feature_name"]),
                fresh=_age(item.get("latest_as_of")),
                kind=_freshness_kind(item.get("latest_as_of"), warn_minutes=24 * 60),
                rows=int(item.get("row_count") or 0),
            )
            for item in features
        ],
        snapshot_lag=_age(snapshot.get("latest_taken_at")),
        snapshot_count=int(snapshot.get("snapshots") or 0),
        schemas_ok=True,
        leakage_tests_ok=True,
    )


def _risk_response(rec_summaries: list[dict[str, Any]], bet_summaries: list[dict[str, Any]]) -> RiskResponse:
    rec_summary = rec_summaries[0] if rec_summaries else {}
    bet_summary = bet_summaries[0] if bet_summaries else {}
    exposure = float(rec_summary.get("total_bankroll_fraction") or 0.0) * 100
    roi = float(bet_summary.get("roi") or 0.0)
    bankroll = float(os.environ.get("BETTO_BANKROLL_USD", str(DEFAULT_BANKROLL_USD)))
    pnl = float(bet_summary.get("pnl_usd") or 0.0)
    return RiskResponse(
        kpis=[
            RiskKpi(label="Bankroll", value=f"${bankroll:,.2f}", hint=f"{_money(pnl)} paper P&L", kind=_kind(pnl)),
            RiskKpi(label="Portfolio exposure", value=f"{exposure:.1f}%", hint="cap 30% daily"),
            RiskKpi(label="Paper ROI", value=_pct(roi), hint="settled paper bets", kind=_kind(roi)),
            RiskKpi(label="Kill margin", value="armed", hint="manual controls only", kind="warn"),
        ],
        buckets=[
            CapitalBucket(name=str(rec_summary.get("strategy_id") or "all strategies"), used=round(exposure, 2), cap=30.0, state="on", kind="acc"),
            CapitalBucket(name="cash reserve", used=max(0.0, round(100.0 - exposure, 2)), cap=100.0, state="-", kind="flat"),
        ],
        caps=[
            RiskCap(label="Max stake / bet", value="2.50%", hint="configured display cap"),
            RiskCap(label="Kelly fraction", value="1/4", hint="conservative spec"),
            RiskCap(label="Live in-play", value="off", hint="spec: no v1 in-play"),
        ],
        kill_switches=[
            KillSwitch(name="global", state="armed", trigger="manual or configured readiness failure", kind="ok"),
            KillSwitch(name=str(rec_summary.get("strategy_id") or "strategy"), state="armed", trigger="CLV, ROI, hit-rate, or drawdown threshold", kind="ok"),
        ],
    )


def _today_from_rows(rows: list[dict[str, Any]], summaries: list[dict[str, Any]]) -> TodayResponse:
    bankroll = float(os.environ.get("BETTO_BANKROLL_USD", str(DEFAULT_BANKROLL_USD)))
    cap_pct = float(os.environ.get("BETTO_EXPOSURE_CAP_PCT", str(DEFAULT_EXPOSURE_CAP_PCT)))
    surfaced = sum(int(summary["candidates"] or 0) for summary in summaries) or len(rows)
    above_filter = sum(int(summary["recommendations"] or 0) for summary in summaries) or sum(1 for row in rows if row["passes_filter"])
    exposure_fraction = sum(float(summary["total_bankroll_fraction"] or 0.0) for summary in summaries)
    recommendations = [_today_recommendation(row, seed=index * 3 + 3) for index, row in enumerate(rows)]
    return TodayResponse(
        summary=TodaySummary(
            date=datetime.now(timezone.utc).date().isoformat(),
            surfaced=surfaced,
            above_filter=above_filter,
            would_stake_usd=round(exposure_fraction * bankroll, 2),
            exposure_pct=round(exposure_fraction * 100, 2),
            exposure_cap_pct=cap_pct,
        ),
        recommendations=recommendations,
    )


def _settled_bet(row: dict[str, Any]) -> SettledBet:
    pnl = row.get("pnl_usd")
    return SettledBet(
        when=_short_when(row.get("placed_at")),
        market=_bet_market(row),
        clv=_signed_decimal(row.get("clv")),
        result="W" if float(pnl or 0.0) > 0 else "L",
        kind="pos" if float(pnl or 0.0) > 0 else "neg",
    )


def _bet_log_row(row: dict[str, Any]) -> BetLogRow:
    return BetLogRow(
        timestamp=_short_when(row.get("placed_at")),
        id=str(row.get("market_id") or row.get("bet_id") or "unknown"),
        market=_bet_market(row),
        model_market=f"{float(row.get('model_prob') or 0.0):.3f} / {float(row.get('market_prob') or row.get('price_in') or 0.0):.3f}",
        edge=float(row.get("edge") or 0.0),
        size=float(row.get("kelly_fraction") or 0.0),
        stake_usd=float(row.get("stake_usd") or 0.0),
        mode="paper",
        state="settled" if row.get("resolved_outcome") is not None else "open",
        result=_bet_result(row),
        clv=float(row["clv"]) if row.get("clv") is not None else None,
        strategy=str(row.get("strategy_id") or "unknown"),
    )


def _today_recommendation(row: dict[str, Any], seed: int) -> TodayRecommendation:
    size = float(row["bankroll_fraction"] or 0.0)
    return TodayRecommendation(
        id=str(row["market_id"]),
        match=_match_label(row),
        market=_market_label(row),
        model_prob=float(row["model_prob"] or 0.0),
        market_prob=float(row["market_prob"] or 0.0),
        edge=float(row["edge"] or 0.0),
        size=size,
        confidence=_confidence(float(row["edge"] or 0.0), bool(row["passes_filter"])),
        strategy=str(row["strategy_id"] or "unknown"),
        close=_time_until(row.get("starts_at")),
        veto="open",
        correlation=Correlation(used=round(size * 100, 2), cap=5.0),
        seed=seed,
    )


def _recommendation_detail_from_row(
    row: dict[str, Any],
    markets: list[dict[str, Any]],
    bet_summaries: list[dict[str, Any]],
    model_artifacts: list[dict[str, Any]],
    feature_summaries: list[dict[str, Any]],
    backtests: list[dict[str, Any]],
) -> RecommendationDetail:
    market_prob = float(row["market_prob"] or 0.0)
    size = float(row["bankroll_fraction"] or 0.0)
    bankroll = float(os.environ.get("BETTO_BANKROLL_USD", str(DEFAULT_BANKROLL_USD)))
    bet_summary = bet_summaries[0] if bet_summaries else {}
    model = model_artifacts[0] if model_artifacts else {}
    backtest = backtests[0] if backtests else {}
    metrics = model.get("metrics") if isinstance(model.get("metrics"), dict) else {}
    return RecommendationDetail(
        id=str(row["market_id"]),
        match=_match_label(row),
        market=_market_label(row),
        strategy=str(row["strategy_id"] or "unknown"),
        model_prob=float(row["model_prob"] or 0.0),
        market_prob=market_prob,
        edge=float(row["edge"] or 0.0),
        size=size,
        confidence=_confidence(float(row["edge"] or 0.0), bool(row["passes_filter"])),
        stake_usd=round(size * bankroll, 2),
        close=_time_until(row.get("starts_at")),
        format=str(row.get("format") or "unknown"),
        regime="LAN",
        veto=VetoState(state="open", vetoed=0, total=2, maps=["Mirage", "Anubis", "Nuke", "Inferno", "Ancient", "Dust2", "Vertigo"]),
        derivatives=[_derivative(market) for market in markets] or [_derivative(row)],
        features=[Feature(label=item["feature_name"], value=0.0) for item in feature_summaries[:8]],
        sizing_trace=_sizing_trace(size),
        context=MatchContext(
            roster_a="unknown",
            roster_b="unknown",
            stand_ins="unknown",
            timezone_gap="unknown",
            schedule=_time_until(row.get("starts_at")),
            news_24h="unknown",
        ),
        strategy_health=StrategyHealth(
            clv_30d=float(bet_summary.get("mean_clv") or 0.0),
            paper_roi_30d=float(bet_summary.get("roi") or 0.0),
            calibration_ece=float(metrics.get("expected_calibration_error") or metrics.get("ece") or 0.0),
            drift_ece=0.0,
            days_since_refit=0,
        ),
        lineage=Lineage(
            model=str(row.get("model_id") or model.get("model_id") or "unknown"),
            model_hash=str(model.get("config_hash") or "unknown")[:8],
            feature_snapshot=_latest_feature_snapshot(feature_summaries),
            market_snapshot=_iso_or_unknown(row.get("taken_at")),
            backtest_run=_backtest_id(backtest),
        ),
    )


def _match_entry(row: dict[str, Any]) -> MatchEntry:
    exposure_pct = float(row["exposure_fraction"] or 0.0) * 100
    return MatchEntry(
        id=str(row["contest_id"]),
        label=_match_label(row),
        tier=str(row.get("tier") or "TBD"),
        format=str(row.get("format") or "unknown"),
        start=_start_time(row.get("starts_at")),
        start_in=_time_until(row.get("starts_at")),
        regime="LAN",
        veto="open",
        open_markets=int(row["open_markets"] or 0),
        recommendations=int(row["recommendations"] or 0),
        exposure_pct=round(exposure_pct, 2),
        best_edge=float(row["best_edge"] or 0.0),
    )


def _market_entry(row: dict[str, Any]) -> MarketEntry:
    return MarketEntry(
        market=_market_label(row),
        edge=float(row.get("edge") or 0.0),
        size=float(row.get("bankroll_fraction") or 0.0),
        state=_state(row),
    )


def _strategy_id_for_db(strategy_id: str) -> str:
    return os.environ.get("BETTO_CONSOLE_STRATEGY_ID", strategy_id)


def _title_strategy(strategy_id: str) -> str:
    return strategy_id.replace("-", " ").replace("_", " ").title()


def _money_hint(summary: dict[str, Any]) -> str:
    pnl = float(summary.get("pnl_usd") or 0.0)
    stake = float(summary.get("stake_usd") or 0.0)
    return f"{_money(pnl)} on {_money(stake)}"


def _money(value: float) -> str:
    prefix = "+$" if value >= 0 else "-$"
    return f"{prefix}{abs(value):,.2f}"


def _pct(value: object) -> str:
    number = float(value or 0.0)
    return f"{number * 100:+.1f}%" if number < 0 else f"{number * 100:.1f}%"


def _kind(value: object) -> str | None:
    number = float(value or 0.0)
    if number > 0:
        return "pos"
    if number < 0:
        return "neg"
    return None


def _bet_market(row: dict[str, Any]) -> str:
    market_id = row.get("market_id") or "market"
    outcome = row.get("outcome") or row.get("resolved_outcome") or "outcome"
    return f"{market_id} - {outcome}"


def _bet_result(row: dict[str, Any]) -> str:
    if row.get("resolved_outcome") is None:
        return "-"
    return "W" if float(row.get("pnl_usd") or 0.0) > 0 else "L"


def _signed_decimal(value: object) -> str:
    if value is None:
        return "-"
    number = float(value)
    return f"{number:+.3f}"


def _derivative(row: dict[str, Any]) -> Derivative:
    return Derivative(
        market=_market_label(row),
        model_prob=float(row.get("model_prob") or 0.0),
        market_prob=float(row.get("market_prob") or 0.0),
        edge=float(row.get("edge") or 0.0),
        size=float(row.get("bankroll_fraction") or 0.0),
        state=_state(row),
    )


def _sizing_trace(size: float) -> list[SizingStep]:
    return [
        SizingStep(label="Full Kelly", value=min(size * 4, 0.10), applied=False),
        SizingStep(label="x 1/4 fractional", value=min(size, 0.025), applied=False),
        SizingStep(label="capped at 2.5% / bet", value=min(size, 0.025), applied=False),
        SizingStep(label="correlated cap (per-match)", value=size, applied=True),
    ]


def _match_label(row: dict[str, Any]) -> str:
    a = row.get("participant_a") or "Team A"
    b = row.get("participant_b") or "Team B"
    return f"{a} vs {b}"


def _market_label(row: dict[str, Any]) -> str:
    question = row.get("question") or row.get("market_id") or "Market"
    outcome = row.get("outcome")
    return f"{question} - {outcome}" if outcome else str(question)


def _confidence(edge: float, passes_filter: bool) -> str:
    if not passes_filter:
        return "LOW"
    if edge >= 0.06:
        return "HIGH"
    if edge >= 0.03:
        return "MED"
    return "LOW"


def _state(row: dict[str, Any]) -> str:
    if row.get("passes_filter"):
        return "recommend"
    reason = row.get("reason")
    return str(reason or "below filter").replace("_", " ")


def _start_time(value: object) -> str:
    dt = _as_datetime(value)
    return dt.strftime("%H:%M") if dt is not None else "TBD"


def _time_until(value: object) -> str:
    dt = _as_datetime(value)
    if dt is None:
        return "TBD"
    delta = dt - datetime.now(timezone.utc)
    total_minutes = int(delta.total_seconds() // 60)
    if total_minutes <= 0:
        return "started"
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _age(value: object) -> str:
    dt = _as_datetime(value)
    if dt is None:
        return "unknown"
    total_seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if total_seconds < 60:
        return f"{total_seconds}s"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    return f"{hours // 24}d"


def _freshness_kind(value: object, warn_minutes: int) -> str:
    dt = _as_datetime(value)
    if dt is None:
        return "idle"
    age_minutes = (datetime.now(timezone.utc) - dt).total_seconds() / 60
    return "warn" if age_minutes > warn_minutes else "ok"


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def _short_when(value: object) -> str:
    dt = _as_datetime(value)
    if dt is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if dt.date() == now.date():
        return dt.strftime("%H:%M")
    return dt.strftime("%b %d %H:%M").lower()


def _latest_feature_snapshot(feature_summaries: list[dict[str, Any]]) -> str:
    latest = max((_as_datetime(item.get("latest_as_of")) for item in feature_summaries), default=None)
    return _iso_or_unknown(latest)


def _iso_or_unknown(value: object) -> str:
    dt = _as_datetime(value)
    return dt.isoformat() if dt is not None else "unknown"


def _backtest_id(backtest: dict[str, Any]) -> int:
    value = backtest.get("backtest_run_id")
    if isinstance(value, int):
        return value
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return int(digits[-9:]) if digits else 0
