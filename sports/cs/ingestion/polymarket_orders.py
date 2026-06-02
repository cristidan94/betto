from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.request
from urllib.parse import urlencode
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class PolymarketOrder:
    order_id: str
    market_id: str
    token_id: str
    side: str
    size: float
    price: float
    order_type: str
    status: str
    filled_size: float
    created_at: datetime
    raw: dict[str, Any]


@dataclass(frozen=True)
class PolymarketOrderResult:
    success: bool
    order: PolymarketOrder | None
    error: str | None


@dataclass(frozen=True)
class PolymarketBalance:
    available: float
    locked: float
    total: float


class PolymarketOrderClient:
    """Authenticated Polymarket CLOB API client for order management."""

    def __init__(
        self,
        clob_url: str,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        private_key: str,
        chain_id: int = 137,
        address: str = "",
    ) -> None:
        self.clob_url = clob_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.private_key = private_key
        self.chain_id = chain_id
        self.address = address

    def _auth_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        timestamp = str(int(time.time()))
        message = timestamp + method.upper() + path + body
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "POLY_API_KEY": self.api_key,
            "POLY_SIGNATURE": signature,
            "POLY_TIMESTAMP": timestamp,
            "POLY_PASSPHRASE": self.api_passphrase,
        }
        if self.address:
            headers["POLY_ADDRESS"] = self.address
        return headers

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        body_str = json.dumps(body) if body else ""
        headers = self._auth_headers(method, path, body_str)
        headers["Content-Type"] = "application/json"
        url = self.clob_url + path
        data = body_str.encode("utf-8") if body_str else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())

    def place_market_order(
        self,
        token_id: str,
        side: str,
        size: float,
    ) -> PolymarketOrderResult:
        """Place a market order (immediate execution at best available price)."""
        return self._place_order(token_id, side, size, price=None, order_type="FOK")

    def place_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> PolymarketOrderResult:
        """Place a GTC limit order."""
        return self._place_order(token_id, side, size, price=price, order_type="GTC")

    def _place_order(
        self,
        token_id: str,
        side: str,
        size: float,
        price: float | None,
        order_type: str,
    ) -> PolymarketOrderResult:
        payload: dict[str, Any] = {
            "tokenID": token_id,
            "side": side.upper(),
            "size": str(size),
            "type": order_type,
        }
        if price is not None:
            payload["price"] = str(price)

        try:
            result = self._request("POST", "/order", payload)
        except Exception as exc:
            return PolymarketOrderResult(success=False, order=None, error=str(exc))

        if result.get("errorMsg"):
            return PolymarketOrderResult(success=False, order=None, error=result["errorMsg"])

        order = _parse_order(result)
        return PolymarketOrderResult(success=True, order=order, error=None)

    def cancel_order(self, order_id: str) -> bool:
        try:
            result = self._request("DELETE", f"/order/{order_id}")
            return not result.get("errorMsg")
        except Exception:
            return False

    def cancel_all_orders(self) -> bool:
        try:
            result = self._request("DELETE", "/orders")
            return not result.get("errorMsg")
        except Exception:
            return False

    def get_open_orders(self, market_id: str | None = None) -> list[PolymarketOrder]:
        path = "/orders"
        if market_id:
            path = f"/orders?market={market_id}"
        try:
            result = self._request("GET", path)
        except Exception:
            return []
        rows = result if isinstance(result, list) else result.get("orders", [])
        return [_parse_order(row) for row in rows if isinstance(row, dict)]

    def get_user_orders(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if status:
            params["status"] = status
        path = "/data/orders?" + urlencode(params)
        try:
            result = self._request("GET", path)
        except Exception as exc:
            return {"data": [], "error": str(exc)}
        return result if isinstance(result, dict) else {"data": result}

    def get_trades(
        self,
        *,
        limit: int = 100,
        cursor: str | None = None,
        market: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if market:
            params["market"] = market
        path = "/trades?" + urlencode(params)
        try:
            result = self._request("GET", path)
        except Exception as exc:
            return {"data": [], "error": str(exc)}
        return result if isinstance(result, dict) else {"data": result}

    def get_order(self, order_id: str) -> PolymarketOrder | None:
        try:
            result = self._request("GET", f"/order/{order_id}")
        except Exception:
            return None
        if not isinstance(result, dict) or result.get("errorMsg"):
            return None
        return _parse_order(result)

    def get_balance(self) -> PolymarketBalance | None:
        try:
            result = self._request("GET", "/balance")
        except Exception:
            return None
        if not isinstance(result, dict):
            return None
        return PolymarketBalance(
            available=float(result.get("available", 0)),
            locked=float(result.get("locked", 0)),
            total=float(result.get("total", result.get("available", 0))),
        )


def _parse_order(raw: dict[str, Any]) -> PolymarketOrder:
    return PolymarketOrder(
        order_id=str(raw.get("id") or raw.get("orderID") or ""),
        market_id=str(raw.get("market") or raw.get("asset_id") or ""),
        token_id=str(raw.get("tokenID") or raw.get("token_id") or ""),
        side=str(raw.get("side", "")).upper(),
        size=float(raw.get("original_size") or raw.get("size") or 0),
        price=float(raw.get("price") or 0),
        order_type=str(raw.get("type") or raw.get("order_type") or ""),
        status=str(raw.get("status") or "unknown"),
        filled_size=float(raw.get("size_matched") or raw.get("filled_size") or 0),
        created_at=_parse_ts(raw.get("created_at") or raw.get("createdAt")),
        raw=raw,
    )


def _parse_ts(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)
