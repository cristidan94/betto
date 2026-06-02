from __future__ import annotations

import json
import unittest
from datetime import timezone

from core.http import HttpResponse
from sports.cs.ingestion.polymarket import (
    PolymarketClient,
    PolymarketMarketMeta,
    PolymarketToken,
    is_counter_strike_market,
    parse_clob_book,
    parse_gamma_market,
    parse_price_history,
)


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object] | None]] = []

    def get(self, base_url: str, path: str, params: dict[str, object] | None = None) -> HttpResponse:
        self.calls.append((base_url, path, params))
        if path == "/markets":
            body = json.dumps(
                [
                    {
                        "id": "market-1",
                        "question": "Will NAVI beat Vitality in Counter-Strike 2?",
                        "outcomes": "[\"NAVI\", \"Vitality\"]",
                        "clobTokenIds": "[\"token-a\", \"token-b\"]",
                        "createdAt": "2026-05-16T10:00:00Z",
                        "volumeNum": 45200.50,
                        "liquidityNum": 12000.0,
                        "outcomePrices": "[\"0.62\", \"0.38\"]",
                        "active": True,
                        "closed": False,
                        "archived": False,
                        "acceptingOrders": True,
                        "negRisk": False,
                        "description": "Will NAVI win vs Vitality at IEM Dallas?",
                        "eventSlug": "iem-dallas-2026",
                        "eventTitle": "IEM Dallas 2026",
                        "startDate": "2026-05-20T18:00:00Z",
                        "endDate": "2026-05-20T22:00:00Z",
                    },
                    {
                        "id": "market-2",
                        "question": "Will it rain tomorrow?",
                        "outcomes": "[\"Yes\", \"No\"]",
                        "clobTokenIds": "[\"token-c\", \"token-d\"]",
                    },
                ]
            ).encode("utf-8")
            return HttpResponse("https://gamma.test/markets", 200, body, {"content-type": "application/json"})
        if path == "/prices-history":
            body = json.dumps(
                {
                    "history": [
                        {"t": 1_710_000_000, "p": "0.42"},
                        {"timestamp": 1_710_003_600_000, "price": 0.44},
                    ]
                }
            ).encode("utf-8")
            return HttpResponse("https://clob.test/prices-history", 200, body, {"content-type": "application/json"})
        body = json.dumps(
            {
                "bids": [{"price": "0.41", "size": "100"}, {"price": "0.40", "size": "75"}],
                "asks": [{"price": "0.44", "size": "50"}, {"price": "0.45", "size": "25"}],
            }
        ).encode("utf-8")
        return HttpResponse("https://clob.test/book", 200, body, {"content-type": "application/json"})


class PolymarketIngestionTests(unittest.TestCase):
    def test_counter_strike_filter_matches_cs_terms(self) -> None:
        self.assertTrue(is_counter_strike_market({"question": "Counter-Strike 2 final winner"}))
        self.assertTrue(is_counter_strike_market({"slug": "csgo-navi-vs-g2"}))
        self.assertFalse(is_counter_strike_market({"question": "NBA finals winner"}))

    def test_parse_gamma_market_maps_outcomes_to_tokens(self) -> None:
        parsed = parse_gamma_market(
            {
                "id": "market-1",
                "question": "Will NAVI win map 1?",
                "outcomes": "[\"Yes\", \"No\"]",
                "clobTokenIds": "[\"token-yes\", \"token-no\"]",
            }
        )

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.market.market_type, "map_winner")
        self.assertEqual(parsed.tokens[0].token_id, "token-yes")
        self.assertEqual(parsed.tokens[0].outcome, "Yes")

    def test_parse_gamma_market_extracts_enriched_meta(self) -> None:
        parsed = parse_gamma_market(
            {
                "id": "market-1",
                "question": "Will NAVI beat Vitality in Counter-Strike 2?",
                "outcomes": "[\"NAVI\", \"Vitality\"]",
                "clobTokenIds": "[\"token-a\", \"token-b\"]",
                "volumeNum": 45200.50,
                "liquidityNum": 12000.0,
                "outcomePrices": "[\"0.62\", \"0.38\"]",
                "active": True,
                "acceptingOrders": True,
                "eventSlug": "iem-dallas-2026",
                "eventTitle": "IEM Dallas 2026",
                "description": "NAVI vs Vitality match",
                "startDate": "2026-05-20T18:00:00Z",
            }
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        meta = parsed.meta
        self.assertAlmostEqual(meta.volume_usd, 45200.50)
        self.assertAlmostEqual(meta.liquidity_usd, 12000.0)
        self.assertEqual(meta.outcome_prices, (0.62, 0.38))
        self.assertAlmostEqual(meta.spread, 0.24)
        self.assertTrue(meta.active)
        self.assertTrue(meta.accepting_orders)
        self.assertEqual(meta.event_slug, "iem-dallas-2026")
        self.assertEqual(meta.event_title, "IEM Dallas 2026")
        self.assertIsNotNone(meta.start_date)

    def test_parse_clob_book_computes_best_prices_and_depth(self) -> None:
        snapshot = parse_clob_book(
            "market-1",
            "YES",
            {
                "bids": [{"price": "0.41", "size": "100"}, {"price": "0.405", "size": "75"}],
                "asks": [{"price": "0.44", "size": "50"}, {"price": "0.448", "size": "25"}],
            },
        )

        self.assertEqual(snapshot.best_bid, 0.41)
        self.assertEqual(snapshot.best_ask, 0.44)
        self.assertEqual(snapshot.depth_bid_1pct, 175)
        self.assertEqual(snapshot.depth_ask_1pct, 75)

    def test_parse_price_history_maps_rows_to_snapshots(self) -> None:
        snapshots = parse_price_history(
            "market-1",
            "YES",
            {
                "history": [
                    {"t": 1_710_000_000, "p": "0.42"},
                    {"timestamp": 1_710_003_600_000, "price": 0.44},
                    {"time": "2024-03-09T17:00:00Z", "lastTradePrice": "0.46"},
                    {"time": "bad", "price": "0.50"},
                ]
            },
        )

        self.assertEqual(len(snapshots), 3)
        self.assertEqual(snapshots[0].market_id, "market-1")
        self.assertEqual(snapshots[0].outcome, "YES")
        self.assertEqual(snapshots[0].taken_at.tzinfo, timezone.utc)
        self.assertEqual(snapshots[0].last_trade_price, 0.42)
        self.assertIsNone(snapshots[0].best_bid)
        self.assertIsNone(snapshots[0].best_ask)

    def test_client_discovers_cs_markets_and_fetches_books(self) -> None:
        client = PolymarketClient("https://gamma.test", "https://clob.test", http=FakeHttp())  # type: ignore[arg-type]

        discovery = client.discover_cs_markets(limit=10)
        book = client.get_order_book(discovery.markets[0].market.market_id, discovery.markets[0].tokens[0])

        self.assertEqual(len(discovery.markets), 1)
        self.assertEqual(book.snapshot.best_bid, 0.41)
        self.assertEqual(book.raw_payload.source_id, "clob-book-token-a")

    def test_client_fetches_price_history(self) -> None:
        http = FakeHttp()
        client = PolymarketClient("https://gamma.test", "https://clob.test", http=http)  # type: ignore[arg-type]

        result = client.get_price_history(
            "market-1",
            PolymarketToken(token_id="token-a", outcome="YES"),
            start_ts=1_710_000_000,
            end_ts=1_710_010_000,
            fidelity=60,
        )

        self.assertEqual(len(result.snapshots), 2)
        self.assertEqual(result.snapshots[1].last_trade_price, 0.44)
        self.assertEqual(result.raw_payload.source_id, "clob-prices-history-token-a-60")
        self.assertEqual(
            http.calls[-1],
            (
                "https://clob.test",
                "/prices-history",
                {"market": "token-a", "fidelity": 60, "startTs": 1_710_000_000, "endTs": 1_710_010_000},
            ),
        )


if __name__ == "__main__":
    unittest.main()
