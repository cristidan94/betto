import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from core.vendor import add_vendor_path

add_vendor_path()

try:
    from fastapi.testclient import TestClient

    from api import data as api_data
    from api.main import app
except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional dev install.
    TestClient = None  # type: ignore[assignment]
    app = None  # type: ignore[assignment]
    FASTAPI_IMPORT_ERROR = exc
else:
    FASTAPI_IMPORT_ERROR = None


@unittest.skipIf(TestClient is None, f"FastAPI test dependencies are unavailable: {FASTAPI_IMPORT_ERROR}")
class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_today_recommendations_endpoint(self) -> None:
        response = self.client.get("/api/today/recommendations")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["surfaced"], 14)
        self.assertEqual(payload["recommendations"][0]["id"], "PM-cs-2891")

    def test_recommendation_detail_endpoint(self) -> None:
        response = self.client.get("/api/recommendations/PM-cs-2891")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], "PM-cs-2891")
        self.assertGreater(len(payload["derivatives"]), 0)

    def test_unknown_recommendation_returns_404(self) -> None:
        response = self.client.get("/api/recommendations/not-real")

        self.assertEqual(response.status_code, 404)

    def test_matches_endpoint(self) -> None:
        response = self.client.get("/api/matches")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["matches"][0]["label"], "NAVI vs G2")

    def test_match_markets_endpoint(self) -> None:
        response = self.client.get("/api/matches/PM-cs-2891/markets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["match_id"], "PM-cs-2891")
        self.assertGreater(len(payload["markets"]), 0)

    def test_unknown_match_markets_returns_404(self) -> None:
        response = self.client.get("/api/matches/not-real/markets")

        self.assertEqual(response.status_code, 404)

    def test_strategy_endpoint(self) -> None:
        response = self.client.get("/api/strategies/map-winner")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["strategy_id"], "map-winner")
        self.assertGreater(len(payload["kpis"]), 0)

    def test_bet_log_endpoint(self) -> None:
        response = self.client.get("/api/bets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["bets"], 142)
        self.assertGreater(len(payload["rows"]), 0)

    def test_ingestion_endpoint(self) -> None:
        response = self.client.get("/api/ingestion")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["sources"][0]["name"], "Polymarket - markets")
        self.assertTrue(payload["schemas_ok"])

    def test_risk_endpoint(self) -> None:
        response = self.client.get("/api/risk")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["kpis"][0]["label"], "Bankroll")
        self.assertGreater(len(payload["kill_switches"]), 0)

    def test_postgres_today_mapper_uses_repository_rows(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        repo = FakeConsoleRepo(
            recommendations=[
                {
                    "recommendation_id": 7,
                    "market_id": "market-1",
                    "outcome": "NAVI",
                    "taken_at": datetime.now(timezone.utc),
                    "model_id": "model-1",
                    "model_prob": 0.58,
                    "market_prob": 0.52,
                    "edge": 0.06,
                    "bankroll_fraction": 0.02,
                    "passes_filter": True,
                    "reason": "edge_pass",
                    "strategy_id": "strategy-1",
                    "question": "NAVI to win",
                    "market_type": "match_winner",
                    "contest_id": "contest-1",
                    "starts_at": future,
                    "format": "bo3",
                    "status": "scheduled",
                    "participant_a": "NAVI",
                    "participant_b": "G2",
                    "tier": "S",
                }
            ],
            summaries=[
                {
                    "strategy_id": "strategy-1",
                    "candidates": 1,
                    "recommendations": 1,
                    "mean_edge": 0.06,
                    "total_bankroll_fraction": 0.02,
                }
            ],
        )

        with patch.dict("os.environ", {"BETTO_API_DATA_SOURCE": "postgres", "BETTO_BANKROLL_USD": "1000"}):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_today_recommendations()

        self.assertEqual(response.summary.surfaced, 1)
        self.assertEqual(response.summary.would_stake_usd, 20.0)
        self.assertEqual(response.recommendations[0].match, "NAVI vs G2")
        self.assertEqual(response.recommendations[0].confidence, "HIGH")

    def test_postgres_matches_mapper_uses_repository_rows(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        repo = FakeConsoleRepo(
            matches=[
                {
                    "contest_id": "contest-1",
                    "starts_at": future,
                    "format": "bo3",
                    "status": "scheduled",
                    "participant_a": "NAVI",
                    "participant_b": "G2",
                    "tier": "S",
                    "open_markets": 3,
                    "recommendations": 1,
                    "exposure_fraction": 0.025,
                    "best_edge": 0.07,
                }
            ]
        )

        with patch.dict("os.environ", {"BETTO_API_DATA_SOURCE": "postgres"}):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_matches()

        self.assertEqual(response.matches[0].id, "contest-1")
        self.assertEqual(response.matches[0].label, "NAVI vs G2")
        self.assertEqual(response.matches[0].exposure_pct, 2.5)

    def test_postgres_bet_log_mapper_uses_repository_rows(self) -> None:
        now = datetime.now(timezone.utc)
        repo = FakeConsoleRepo(
            bet_summaries=[
                {
                    "strategy_id": "strategy-1",
                    "bets": 1,
                    "settled_bets": 1,
                    "open_bets": 0,
                    "stake_usd": 100.0,
                    "pnl_usd": 12.0,
                    "roi": 0.12,
                    "mean_clv": 0.02,
                    "hit_rate": 1.0,
                }
            ],
            bets=[
                {
                    "bet_id": 1,
                    "market_id": "market-1",
                    "outcome": "NAVI",
                    "placed_at": now,
                    "model_prob": 0.58,
                    "market_prob": 0.52,
                    "edge": 0.06,
                    "kelly_fraction": 0.02,
                    "stake_usd": 100.0,
                    "resolved_outcome": "NAVI",
                    "pnl_usd": 12.0,
                    "clv": 0.02,
                    "strategy_id": "strategy-1",
                }
            ],
        )

        with patch.dict("os.environ", {"BETTO_API_DATA_SOURCE": "postgres"}):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_bet_log()

        self.assertEqual(response.summary.bets, 1)
        self.assertEqual(response.rows[0].result, "W")
        self.assertEqual(response.rows[0].market, "market-1 - NAVI")

    def test_postgres_strategy_mapper_uses_repository_rows(self) -> None:
        repo = FakeConsoleRepo(
            summaries=[
                {
                    "strategy_id": "strategy-1",
                    "candidates": 5,
                    "recommendations": 2,
                    "mean_edge": 0.04,
                    "total_bankroll_fraction": 0.03,
                }
            ],
            bet_summaries=[
                {
                    "strategy_id": "strategy-1",
                    "bets": 2,
                    "settled_bets": 2,
                    "open_bets": 0,
                    "stake_usd": 100.0,
                    "pnl_usd": 10.0,
                    "roi": 0.10,
                    "mean_clv": 0.01,
                    "hit_rate": 0.5,
                }
            ],
        )

        with patch.dict("os.environ", {"BETTO_API_DATA_SOURCE": "postgres", "BETTO_CONSOLE_STRATEGY_ID": "strategy-1"}):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_strategy("map-winner")

        self.assertEqual(response.strategy_id, "map-winner")
        self.assertEqual(response.version, "strategy-1")
        self.assertEqual(response.kpis[0].value, "5")

    def test_postgres_ingestion_mapper_uses_repository_rows(self) -> None:
        now = datetime.now(timezone.utc)
        repo = FakeConsoleRepo(
            raw_summaries=[
                {
                    "source": "polymarket",
                    "raw_objects": 12,
                    "latest_fetched_at": now,
                }
            ],
            features=[
                {
                    "feature_name": "cs.team.map_win_rate_90d",
                    "row_count": 8,
                    "latest_as_of": now,
                }
            ],
            snapshot_summaries=[
                {
                    "snapshots": 21,
                    "latest_taken_at": now,
                }
            ],
        )

        with patch.dict("os.environ", {"BETTO_API_DATA_SOURCE": "postgres"}):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_ingestion()

        self.assertEqual(response.sources[0].name, "polymarket")
        self.assertEqual(response.sources[0].rows, 12)
        self.assertEqual(response.features[0].rows, 8)
        self.assertEqual(response.snapshot_count, 21)

    def test_postgres_risk_mapper_uses_repository_rows(self) -> None:
        repo = FakeConsoleRepo(
            summaries=[
                {
                    "strategy_id": "strategy-1",
                    "candidates": 3,
                    "recommendations": 2,
                    "mean_edge": 0.04,
                    "total_bankroll_fraction": 0.07,
                }
            ],
            bet_summaries=[
                {
                    "strategy_id": "strategy-1",
                    "bets": 2,
                    "settled_bets": 2,
                    "open_bets": 0,
                    "stake_usd": 100.0,
                    "pnl_usd": 14.0,
                    "roi": 0.14,
                    "mean_clv": 0.01,
                    "hit_rate": 0.5,
                }
            ],
        )

        with patch.dict(
            "os.environ",
            {
                "BETTO_API_DATA_SOURCE": "postgres",
                "BETTO_BANKROLL_USD": "2000",
                "BETTO_CONSOLE_STRATEGY_ID": "strategy-1",
            },
        ):
            with patch.object(api_data, "_repository", return_value=FakeRepositoryContext(repo)):
                response = api_data.get_risk()

        self.assertEqual(response.kpis[0].value, "$2,000.00")
        self.assertEqual(response.buckets[0].name, "strategy-1")
        self.assertEqual(response.buckets[0].used, 7.0)


class FakeRepositoryContext:
    def __init__(self, repo: "FakeConsoleRepo") -> None:
        self.repo = repo

    def __enter__(self) -> "FakeConsoleRepo":
        return self.repo

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class FakeConsoleRepo:
    def __init__(
        self,
        recommendations: list[dict[str, object]] | None = None,
        summaries: list[dict[str, object]] | None = None,
        matches: list[dict[str, object]] | None = None,
        markets: list[dict[str, object]] | None = None,
        bet_summaries: list[dict[str, object]] | None = None,
        bets: list[dict[str, object]] | None = None,
        raw_summaries: list[dict[str, object]] | None = None,
        features: list[dict[str, object]] | None = None,
        snapshot_summaries: list[dict[str, object]] | None = None,
    ) -> None:
        self.recommendations = recommendations or []
        self.summaries = summaries or []
        self.matches = matches or []
        self.markets = markets or []
        self.bet_summaries = bet_summaries or []
        self.bets = bets or []
        self.raw_summaries = raw_summaries or []
        self.features = features or []
        self.snapshot_summaries = snapshot_summaries or []

    def list_console_recommendations(self, identifier: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        if identifier is None:
            return self.recommendations[:limit]
        return [
            row
            for row in self.recommendations
            if row.get("market_id") == identifier or str(row.get("recommendation_id")) == identifier
        ][:limit]

    def list_recommendation_summaries(self, strategy_id: str | None = None) -> list[dict[str, object]]:
        return self.summaries

    def list_console_matches(self, limit: int = 50) -> list[dict[str, object]]:
        return self.matches[:limit]

    def list_console_match_markets(self, contest_id: str, limit: int = 20) -> list[dict[str, object]]:
        return self.markets[:limit]

    def summarize_paper_bets(self, strategy_id: str | None = None) -> list[dict[str, object]]:
        return self.bet_summaries

    def list_paper_bets(self, strategy_id: str | None = None, limit: int = 20) -> list[dict[str, object]]:
        return self.bets[:limit]

    def list_model_artifacts(self, limit: int = 1) -> list[dict[str, object]]:
        return []

    def list_feature_summaries(self) -> list[dict[str, object]]:
        return self.features

    def list_backtest_runs(self, strategy_id: str | None = None, limit: int = 1) -> list[dict[str, object]]:
        return []

    def summarize_raw_objects(self) -> list[dict[str, object]]:
        return self.raw_summaries

    def summarize_market_snapshots(self) -> list[dict[str, object]]:
        return self.snapshot_summaries


if __name__ == "__main__":
    unittest.main()
