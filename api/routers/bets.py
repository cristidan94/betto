from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from api.data import get_orders as list_persisted_orders
from api.data import place_bet as execute_bet, cancel_bet as execute_cancel

router = APIRouter()


class PlaceBetRequest(BaseModel):
    market_id: str
    outcome: str
    token_id: str = ""
    model_prob: float
    market_prob: float
    size_fraction: float = 0.02
    mode: str = "paper"
    strategy_id: str = "api_execution"


class PlaceBetResponse(BaseModel):
    success: bool
    order_id: str
    mode: str
    market_id: str
    outcome: str
    size_usd: float
    fill_price: float | None = None
    error: str | None = None


class CancelBetRequest(BaseModel):
    order_id: str


class CancelBetResponse(BaseModel):
    cancelled: bool
    order_id: str


class OrderEntry(BaseModel):
    order_id: str
    bet_id: int | None = None
    market_id: str
    outcome: str
    mode: str
    order_type: str
    side: str
    limit_price: float | None = None
    fill_price: float | None = None
    size_usd: float
    fill_size_usd: float | None = None
    order_status: str
    polymarket_token_id: str | None = None
    polymarket_order_id: str | None = None
    tx_hash: str | None = None
    created_at: str
    updated_at: str


class OrdersResponse(BaseModel):
    orders: list[OrderEntry]


@router.post("/bets", response_model=PlaceBetResponse)
async def place_bet(
    req: PlaceBetRequest,
    mode: str | None = Query(default=None, pattern="^(paper|live)$"),
) -> PlaceBetResponse:
    if mode is not None:
        req.mode = mode
    result = execute_bet(req)
    return PlaceBetResponse(**result)


@router.get("/orders", response_model=OrdersResponse)
async def orders() -> OrdersResponse:
    rows = list_persisted_orders()
    return OrdersResponse(orders=[OrderEntry(**_order_entry(row)) for row in rows])


@router.delete("/bets/{order_id}", response_model=CancelBetResponse)
async def cancel_bet(order_id: str) -> CancelBetResponse:
    result = execute_cancel(order_id)
    return CancelBetResponse(**result)


def _order_entry(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "limit_price": float(row["limit_price"]) if row.get("limit_price") is not None else None,
        "fill_price": float(row["fill_price"]) if row.get("fill_price") is not None else None,
        "size_usd": float(row.get("size_usd") or 0.0),
        "fill_size_usd": float(row["fill_size_usd"]) if row.get("fill_size_usd") is not None else None,
    }
