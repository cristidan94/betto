from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.db import PostgresRepository
from core.edge import Recommendation
from core.entities import Competition, Contest, ContestUnit, Participant, ParticipantKind
from core.feature_store import FeatureValue
from core.markets import Market, MarketSnapshot
from core.modeling import ModelArtifact
from core.raw_store import RawObject


class FakeDb:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((sql, params))
        return []


class RepositoryTests(unittest.TestCase):
    def test_upserts_raw_market_and_snapshot(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        now = datetime.now(timezone.utc)

        repo.upsert_raw_object(
            RawObject(
                source="polymarket",
                source_id="gamma-1",
                url="https://example.test",
                content_hash="abc",
                content_type="application/json",
                fetched_at=now,
                body_path=Path("body.bin"),
                metadata_path=Path("body.json"),
            )
        )
        repo.upsert_market(
            Market(
                market_id="m1",
                source="polymarket",
                question="Will NAVI win?",
                market_type="match_winner",
                contest_id=None,
                outcomes=("Yes", "No"),
            )
        )
        repo.insert_market_snapshot(MarketSnapshot("m1", "Yes", now, 0.4, 0.42))
        repo.update_market_link("m1", "contest-1", {"Yes": "team_a", "No": "team_b"}, 0.91)
        repo.upsert_participant(Participant("p1", "counter_strike", ParticipantKind.TEAM, "NAVI", "hltv", "4608"))
        repo.upsert_competition(Competition("e1", "counter_strike", "IEM Dallas", tier="S"))
        repo.upsert_contest(
            Contest(
                "c1",
                "counter_strike",
                "e1",
                now,
                "p1",
                "p2",
                "bo3",
                "finished",
            )
        )
        repo.upsert_contest_unit(ContestUnit("u1", "c1", 1, "map", "Mirage", winner_id="p1"))
        repo.upsert_data_snapshot("snapshot-1", "fixture features")
        repo.insert_feature_value(FeatureValue("p1:map:Mirage", "cs.team.map_win_rate_90d", now, {"win_rate": 1.0}))
        repo.upsert_model_artifact(
            ModelArtifact(
                model_id="model-1",
                game_id="counter_strike",
                target="cs.map_winner",
                git_sha="unknown",
                data_snapshot_id="snapshot-1",
                config_hash="config",
                feature_names=("f1",),
                metrics={"brier_score": 0.2},
            )
        )
        repo.upsert_recommendation(
            Recommendation(
                market_id="m1",
                outcome="Yes",
                taken_at=now,
                model_prob=0.55,
                market_prob=0.45,
                edge=0.10,
                bankroll_fraction=0.02,
                passes_filter=True,
                reason="edge_pass",
            ),
            strategy_id="test_strategy",
            model_id="model-1",
        )

        self.assertEqual(len(db.calls), 12)
        self.assertIn("INSERT INTO raw_objects", db.calls[0][0])
        self.assertIn("INSERT INTO markets", db.calls[1][0])
        self.assertIn("INSERT INTO market_snapshots", db.calls[2][0])
        self.assertIn("UPDATE markets", db.calls[3][0])
        self.assertIn("INSERT INTO participants", db.calls[4][0])
        self.assertIn("INSERT INTO data_snapshots", db.calls[8][0])
        self.assertIn("INSERT INTO feature_values", db.calls[9][0])
        self.assertIn("INSERT INTO model_artifacts", db.calls[10][0])
        self.assertIn("INSERT INTO recommendations", db.calls[11][0])

    def test_lists_feature_summaries_with_filters(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_feature_summaries("cs.team.map_win_rate_90d", "cs:participant:hltv:1")

        sql, params = db.calls[0]

        self.assertIn("FROM feature_values", sql)
        self.assertIn("feature_name = %s", sql)
        self.assertIn("entity_id LIKE %s", sql)
        self.assertEqual(params, ("cs.team.map_win_rate_90d", "cs:participant:hltv:1%"))

    def test_lists_latest_feature_values_with_limit(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_latest_feature_values(limit=5)

        sql, params = db.calls[0]

        self.assertIn("ORDER BY as_of DESC", sql)
        self.assertEqual(params, (5,))

    def test_summarizes_raw_objects(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.summarize_raw_objects()

        sql, params = db.calls[0]

        self.assertIn("FROM raw_objects", sql)
        self.assertIn("MAX(fetched_at)", sql)
        self.assertIn("GROUP BY source", sql)
        self.assertEqual(params, ())

    def test_summarizes_market_snapshots(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.summarize_market_snapshots()

        sql, params = db.calls[0]

        self.assertIn("FROM market_snapshots", sql)
        self.assertIn("MAX(taken_at)", sql)
        self.assertEqual(params, ())

    def test_lists_model_artifacts_with_target_filter(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_model_artifacts(target="cs.map_winner", limit=3)

        sql, params = db.calls[0]

        self.assertIn("FROM model_artifacts", sql)
        self.assertIn("WHERE target = %s", sql)
        self.assertEqual(params, ("cs.map_winner", 3))

    def test_lists_recommendation_summaries_with_strategy_filter(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_recommendation_summaries(strategy_id="paper")

        sql, params = db.calls[0]

        self.assertIn("FROM recommendations", sql)
        self.assertIn("WHERE strategy_id = %s", sql)
        self.assertEqual(params, ("paper",))

    def test_lists_recommendations_with_strategy_and_pass_filters(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_recommendations(strategy_id="paper", passes_filter=True, limit=7)

        sql, params = db.calls[0]

        self.assertIn("FROM recommendations", sql)
        self.assertIn("strategy_id = %s", sql)
        self.assertIn("passes_filter = %s", sql)
        self.assertIn("ORDER BY taken_at DESC", sql)
        self.assertEqual(params, ("paper", True, 7))

    def test_lists_console_recommendations_with_market_joins(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_console_recommendations(identifier="market-1", limit=4)

        sql, params = db.calls[0]

        self.assertIn("FROM recommendations r", sql)
        self.assertIn("LEFT JOIN markets m", sql)
        self.assertIn("LEFT JOIN contests c", sql)
        self.assertIn("LEFT JOIN participants pa", sql)
        self.assertIn("r.market_id = %s OR r.recommendation_id::text = %s", sql)
        self.assertEqual(params, ("market-1", "market-1", 4))

    def test_lists_console_matches_with_exposure_rollup(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_console_matches(limit=12)

        sql, params = db.calls[0]

        self.assertIn("FROM contests c", sql)
        self.assertIn("COUNT(DISTINCT m.market_id)", sql)
        self.assertIn("SUM(r.bankroll_fraction)", sql)
        self.assertIn("WHERE c.game_id = 'counter_strike'", sql)
        self.assertEqual(params, (12,))

    def test_lists_console_match_markets(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.list_console_match_markets("contest-1", limit=8)

        sql, params = db.calls[0]

        self.assertIn("FROM markets m", sql)
        self.assertIn("LEFT JOIN recommendations r", sql)
        self.assertIn("WHERE m.contest_id = %s", sql)
        self.assertEqual(params, ("contest-1", 8))

    def test_upserts_and_lists_report_artifacts(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.upsert_report_artifact(
            report_id="report-1",
            strategy_id="strategy-1",
            report_type="baseline_strategy",
            artifact_uri=".betto/artifacts/reports/report-1.json",
            metrics={"brier_score": 0.2},
            readiness={"passed": True},
        )
        repo.list_report_artifacts(strategy_id="strategy-1", limit=2)

        upsert_sql, upsert_params = db.calls[0]
        list_sql, list_params = db.calls[1]

        self.assertIn("INSERT INTO report_artifacts", upsert_sql)
        self.assertEqual(upsert_params[0], "report-1")
        self.assertIn("FROM report_artifacts", list_sql)
        self.assertIn("WHERE strategy_id = %s", list_sql)
        self.assertEqual(list_params, ("strategy-1", 2))

    def test_upserts_and_lists_backtest_runs(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.upsert_backtest_run(
            backtest_run_id="backtest-1",
            strategy_id="strategy-1",
            game_id="counter_strike",
            target="cs.map_winner",
            data_snapshot_id="snapshot-1",
            run_config={"train_days": 30},
            metrics={"rows": 12, "brier_score": 0.26},
            window_results=[{"rows": 4}],
        )
        repo.list_backtest_runs(strategy_id="strategy-1", limit=3)

        upsert_sql, upsert_params = db.calls[0]
        list_sql, list_params = db.calls[1]

        self.assertIn("INSERT INTO backtest_runs", upsert_sql)
        self.assertEqual(upsert_params[0], "backtest-1")
        self.assertIn("FROM backtest_runs", list_sql)
        self.assertIn("WHERE strategy_id = %s", list_sql)
        self.assertEqual(list_params, ("strategy-1", 3))

    def test_upserts_and_lists_paper_bets(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        now = datetime.now(timezone.utc)

        repo.upsert_paper_bet_from_recommendation(
            {
                "recommendation_id": 11,
                "market_id": "m1",
                "outcome": "Yes",
                "taken_at": now,
                "model_id": "model-1",
                "model_prob": 0.55,
                "market_prob": 0.45,
                "edge": 0.10,
                "bankroll_fraction": 0.02,
                "strategy_id": "strategy-1",
            },
            bankroll_usd=1000.0,
        )
        repo.list_paper_bets(strategy_id="strategy-1", limit=5)

        upsert_sql, upsert_params = db.calls[0]
        list_sql, list_params = db.calls[1]

        self.assertIn("INSERT INTO bets", upsert_sql)
        self.assertIn("ON CONFLICT (recommendation_id, strategy_id)", upsert_sql)
        self.assertEqual(upsert_params[0], 11)
        self.assertEqual(upsert_params[8], 20.0)
        self.assertIn("FROM bets", list_sql)
        self.assertIn("WHERE strategy_id = %s", list_sql)
        self.assertEqual(list_params, ("strategy-1", 5))

    def test_updates_paper_bet_settlement_with_strategy_filter(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.update_paper_bet_settlement(
            market_id="fixture:2370001:1:cs:participant:hltv:4608",
            outcome="cs:participant:hltv:4608",
            price_close=0.52,
            resolved_outcome="cs:participant:hltv:4608",
            strategy_id="strategy-1",
        )

        sql, params = db.calls[0]

        self.assertIn("UPDATE bets", sql)
        self.assertIn("AND strategy_id = %s", sql)
        self.assertIn("pnl_usd = CASE", sql)
        self.assertEqual(params[-3:], ("fixture:2370001:1:cs:participant:hltv:4608", "cs:participant:hltv:4608", "strategy-1"))

    def test_summarizes_paper_bets_with_strategy_filter(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.summarize_paper_bets(strategy_id="strategy-1")

        sql, params = db.calls[0]

        self.assertIn("FROM bets", sql)
        self.assertIn("SUM(pnl_usd)", sql)
        self.assertIn("AVG(clv)", sql)
        self.assertIn("WHERE strategy_id = %s", sql)
        self.assertEqual(params, ("strategy-1",))

    def test_summarizes_paper_bets_by_day_with_limit(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)

        repo.summarize_paper_bets_by_day(strategy_id="strategy-1", limit=9)

        sql, params = db.calls[0]

        self.assertIn("placed_at::date", sql)
        self.assertIn("GROUP BY placed_at::date, strategy_id", sql)
        self.assertIn("ORDER BY placed_date DESC", sql)
        self.assertEqual(params, ("strategy-1", 9))


class ContestUpsertTests(unittest.TestCase):
    def test_upsert_contest_includes_match_stage_and_head_to_head(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        contest = Contest(
            contest_id="cs:contest:hltv:2394722",
            game_id="counter_strike",
            competition_id="cs:competition:hltv:9171",
            starts_at=datetime(2026, 5, 29, 17, 0, tzinfo=timezone.utc),
            participant_a_id="cs:participant:hltv:13644",
            participant_b_id="cs:participant:hltv:13403",
            format="bo3",
            status="finished",
            match_stage="Round of 16",
            head_to_head={"team_a_wins": 3, "team_b_wins": 2},
        )

        repo.upsert_contest(contest)

        self.assertEqual(len(db.calls), 1)
        sql, params = db.calls[0]
        self.assertIn("match_stage", sql)
        self.assertIn("head_to_head", sql)
        self.assertIn("Round of 16", params)
        self.assertIn('{"team_a_wins": 3, "team_b_wins": 2}', params)

    def test_upsert_contest_defaults_to_none(self) -> None:
        db = FakeDb()
        repo = PostgresRepository(db)
        contest = Contest(
            contest_id="c1",
            game_id="cs",
            competition_id=None,
            starts_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            participant_a_id="a",
            participant_b_id="b",
            format="bo1",
            status="finished",
        )

        repo.upsert_contest(contest)

        sql, params = db.calls[0]
        self.assertIn("match_stage", sql)
        self.assertIsNone(params[-2])
        self.assertIsNone(params[-1])


if __name__ == "__main__":
    unittest.main()
