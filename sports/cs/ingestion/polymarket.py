from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.http import JsonHttpClient
from core.ingestion import FetchResult
from core.markets import Market, MarketSnapshot


class PolymarketSeedAdapter:
    """Offline seed adapter used until CLOB and subgraph ingestion are wired."""

    source = "polymarket"

    def fetch_since(self, since: datetime) -> list[FetchResult]:
        payload = {
            "source": self.source,
            "note": "placeholder seed payload; replace with CLOB REST and GraphQL snapshots",
            "since": since.isoformat(),
        }
        return [
            FetchResult.from_text(
                source=self.source,
                source_id=f"seed-{since.date().isoformat()}",
                url="seed://polymarket",
                text=json.dumps(payload, sort_keys=True),
                content_type="application/json",
            )
        ]


@dataclass(frozen=True)
class PolymarketToken:
    token_id: str
    outcome: str


@dataclass(frozen=True)
class PolymarketMarketMeta:
    """Enriched Polymarket-specific fields not captured by the core Market model."""

    volume_usd: float | None
    liquidity_usd: float | None
    outcome_prices: tuple[float, ...] | None
    start_date: datetime | None
    end_date: datetime | None
    active: bool
    closed: bool
    archived: bool
    accepting_orders: bool
    neg_risk: bool
    spread: float | None
    description: str
    event_slug: str
    event_title: str


@dataclass(frozen=True)
class PolymarketMarket:
    market: Market
    tokens: tuple[PolymarketToken, ...]
    meta: PolymarketMarketMeta
    raw: dict[str, Any]


@dataclass(frozen=True)
class PolymarketDiscoveryResult:
    raw_payload: FetchResult
    markets: tuple[PolymarketMarket, ...]


@dataclass(frozen=True)
class PolymarketBookResult:
    raw_payload: FetchResult
    snapshot: MarketSnapshot


@dataclass(frozen=True)
class PolymarketPriceHistoryResult:
    raw_payload: FetchResult
    snapshots: tuple[MarketSnapshot, ...]


class PolymarketClient:
    """Public Polymarket market discovery and order-book client."""

    source = "polymarket"

    def __init__(
        self,
        gamma_url: str = "https://gamma-api.polymarket.com",
        clob_url: str = "https://clob.polymarket.com",
        http: JsonHttpClient | None = None,
    ) -> None:
        self.gamma_url = gamma_url
        self.clob_url = clob_url
        self.http = http or JsonHttpClient()

    def discover_cs_markets(self, limit: int = 100, offset: int = 0, include_closed: bool = False) -> PolymarketDiscoveryResult:
        params = {
            "limit": limit,
            "offset": offset,
            "closed": str(include_closed).lower(),
            "archived": "false",
        }
        response = self.http.get(self.gamma_url, "/markets", params=params)
        payload = response.json()
        rows = payload if isinstance(payload, list) else payload.get("markets", [])
        markets = tuple(
            parsed
            for row in rows
            if isinstance(row, dict) and is_counter_strike_market(row)
            for parsed in [parse_gamma_market(row)]
            if parsed is not None
        )
        raw = FetchResult(
            source=self.source,
            source_id=f"gamma-markets-{offset}-{limit}",
            url=response.url,
            content=response.body,
            content_type=response.headers.get("content-type", "application/json"),
            fetched_at=datetime.now(timezone.utc),
        )
        return PolymarketDiscoveryResult(raw_payload=raw, markets=markets)

    def get_order_book(self, market_id: str, token: PolymarketToken) -> PolymarketBookResult:
        response = self.http.get(self.clob_url, "/book", params={"token_id": token.token_id})
        payload = response.json()
        snapshot = parse_clob_book(market_id=market_id, outcome=token.outcome, payload=payload)
        raw = FetchResult(
            source=self.source,
            source_id=f"clob-book-{token.token_id}",
            url=response.url,
            content=response.body,
            content_type=response.headers.get("content-type", "application/json"),
            fetched_at=snapshot.taken_at,
        )
        return PolymarketBookResult(raw_payload=raw, snapshot=snapshot)

    def get_price_history(
        self,
        market_id: str,
        token: PolymarketToken,
        *,
        start_ts: int | None = None,
        end_ts: int | None = None,
        fidelity: int | str = 720,
    ) -> PolymarketPriceHistoryResult:
        params: dict[str, object] = {
            "market": token.token_id,
            "fidelity": fidelity,
        }
        if start_ts is not None:
            params["startTs"] = start_ts
        if end_ts is not None:
            params["endTs"] = end_ts

        response = self.http.get(self.clob_url, "/prices-history", params=params)
        payload = response.json()
        snapshots = parse_price_history(market_id=market_id, outcome=token.outcome, payload=payload)
        raw = FetchResult(
            source=self.source,
            source_id=f"clob-prices-history-{token.token_id}-{fidelity}",
            url=response.url,
            content=response.body,
            content_type=response.headers.get("content-type", "application/json"),
            fetched_at=datetime.now(timezone.utc),
        )
        return PolymarketPriceHistoryResult(raw_payload=raw, snapshots=snapshots)


def is_counter_strike_market(row: dict[str, Any]) -> bool:
    haystack_parts: list[str] = []
    for key in ("question", "slug", "description", "title", "eventTitle"):
        value = row.get(key)
        if isinstance(value, str):
            haystack_parts.append(value)
    tags = row.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                haystack_parts.extend(str(tag.get(key, "")) for key in ("label", "name", "slug"))
            elif isinstance(tag, str):
                haystack_parts.append(tag)
    haystack = " ".join(haystack_parts).lower()
    terms = ("counter-strike", "counter strike", "counterstrike", "cs2", "cs:go", "csgo")
    return any(term in haystack for term in terms)


def parse_gamma_market(row: dict[str, Any]) -> PolymarketMarket | None:
    market_id = str(row.get("id") or row.get("conditionId") or row.get("marketId") or "")
    question = str(row.get("question") or row.get("title") or "")
    if not market_id or not question:
        return None

    outcomes = _parse_jsonish_list(row.get("outcomes"))
    token_ids = _parse_jsonish_list(row.get("clobTokenIds"))
    if not outcomes:
        outcomes = ["Yes", "No"]
    tokens = tuple(
        PolymarketToken(token_id=str(token_id), outcome=str(outcome))
        for token_id, outcome in zip(token_ids, outcomes, strict=False)
        if token_id
    )
    market = Market(
        market_id=market_id,
        source="polymarket",
        question=question,
        market_type=infer_market_type(question, row),
        contest_id=None,
        outcomes=tuple(str(outcome) for outcome in outcomes),
        created_at=_parse_optional_datetime(row.get("createdAt") or row.get("created_at")),
        resolved_at=_parse_optional_datetime(row.get("resolvedAt") or row.get("resolved_at")),
        resolved_outcome=row.get("resolvedOutcome") or row.get("resolved_outcome"),
    )

    outcome_prices = _parse_jsonish_floats(row.get("outcomePrices"))
    spread: float | None = None
    if outcome_prices and len(outcome_prices) >= 2:
        spread = round(abs(outcome_prices[0] - outcome_prices[1]), 6)

    meta = PolymarketMarketMeta(
        volume_usd=_parse_float(row.get("volumeNum") or row.get("volume")),
        liquidity_usd=_parse_float(row.get("liquidityNum") or row.get("liquidity")),
        outcome_prices=tuple(outcome_prices) if outcome_prices else None,
        start_date=_parse_optional_datetime(row.get("startDate") or row.get("start_date")),
        end_date=_parse_optional_datetime(row.get("endDate") or row.get("end_date")),
        active=bool(row.get("active", False)),
        closed=bool(row.get("closed", False)),
        archived=bool(row.get("archived", False)),
        accepting_orders=bool(row.get("acceptingOrders", row.get("accepting_orders", False))),
        neg_risk=bool(row.get("negRisk", row.get("neg_risk", False))),
        spread=spread,
        description=str(row.get("description") or ""),
        event_slug=str(row.get("eventSlug") or row.get("event_slug") or ""),
        event_title=str(row.get("eventTitle") or row.get("event_title") or ""),
    )
    return PolymarketMarket(market=market, tokens=tokens, meta=meta, raw=row)


def parse_clob_book(market_id: str, outcome: str, payload: dict[str, Any]) -> MarketSnapshot:
    bids = _parse_orders(payload.get("bids"))
    asks = _parse_orders(payload.get("asks"))
    best_bid = max((price for price, _ in bids), default=None)
    best_ask = min((price for price, _ in asks), default=None)
    return MarketSnapshot(
        market_id=market_id,
        outcome=outcome,
        taken_at=datetime.now(timezone.utc),
        best_bid=best_bid,
        best_ask=best_ask,
        last_trade_price=_parse_float(payload.get("last_trade_price") or payload.get("lastTradePrice")),
        depth_bid_1pct=_depth_within(best_bid, bids, side="bid"),
        depth_ask_1pct=_depth_within(best_ask, asks, side="ask"),
    )


def parse_price_history(market_id: str, outcome: str, payload: Any) -> tuple[MarketSnapshot, ...]:
    rows = _price_history_rows(payload)
    snapshots: list[MarketSnapshot] = []
    for row in rows:
        timestamp = _parse_history_timestamp(_first_present(row, ("t", "timestamp", "time", "date", "created_at")))
        price = _parse_float(_first_present(row, ("p", "price", "last", "last_trade_price", "lastTradePrice")))
        if timestamp is None or price is None:
            continue
        snapshots.append(
            MarketSnapshot(
                market_id=market_id,
                outcome=outcome,
                taken_at=timestamp,
                best_bid=None,
                best_ask=None,
                last_trade_price=price,
            )
        )
    return tuple(snapshots)


def infer_market_type(question: str, row: dict[str, Any]) -> str:
    explicit = row.get("sportsMarketType") or row.get("marketType")
    if isinstance(explicit, str) and explicit:
        return explicit
    lowered = question.lower()
    if "correct score" in lowered:
        return "correct_score"
    if "handicap" in lowered or "+1.5" in lowered or "-1.5" in lowered:
        return "map_handicap"
    if "total maps" in lowered or "over" in lowered or "under" in lowered:
        return "total_maps"
    if "map" in lowered and "win" in lowered:
        return "map_winner"
    return "match_winner"


def _parse_jsonish_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [part.strip() for part in value.split(",") if part.strip()]
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_jsonish_floats(value: Any) -> list[float]:
    raw = _parse_jsonish_list(value)
    result: list[float] = []
    for item in raw:
        f = _parse_float(item)
        if f is not None:
            result.append(f)
    return result


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _parse_history_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        numeric = _parse_float(stripped)
        if numeric is not None:
            return _parse_history_timestamp(numeric)
        return _parse_optional_datetime(stripped)
    return None


def _price_history_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("history", "prices", "data"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _first_present(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _parse_orders(value: Any) -> list[tuple[float, float]]:
    if not isinstance(value, list):
        return []
    orders: list[tuple[float, float]] = []
    for row in value:
        if not isinstance(row, dict):
            continue
        price = _parse_float(row.get("price"))
        size = _parse_float(row.get("size"))
        if price is not None and size is not None:
            orders.append((price, size))
    return orders


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _depth_within(anchor: float | None, orders: list[tuple[float, float]], side: str) -> float | None:
    if anchor is None:
        return None
    if side == "bid":
        return sum(size for price, size in orders if price >= anchor - 0.01)
    if side == "ask":
        return sum(size for price, size in orders if price <= anchor + 0.01)
    raise ValueError("side must be bid or ask")
