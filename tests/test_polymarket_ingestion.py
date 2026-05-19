from __future__ import annotations

import json
import unittest

from core.http import HttpResponse
from sports.cs.ingestion.polymarket import PolymarketClient, is_counter_strike_market, parse_clob_book, parse_gamma_market


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

    def test_client_discovers_cs_markets_and_fetches_books(self) -> None:
        client = PolymarketClient("https://gamma.test", "https://clob.test", http=FakeHttp())  # type: ignore[arg-type]

        discovery = client.discover_cs_markets(limit=10)
        book = client.get_order_book(discovery.markets[0].market.market_id, discovery.markets[0].tokens[0])

        self.assertEqual(len(discovery.markets), 1)
        self.assertEqual(book.snapshot.best_bid, 0.41)
        self.assertEqual(book.raw_payload.source_id, "clob-book-token-a")


if __name__ == "__main__":
    unittest.main()

