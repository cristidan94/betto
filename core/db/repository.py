from __future__ import annotations

import json
from typing import Any, Protocol

from core.entities import Competition, Contest, ContestUnit, Participant, ParticipantKind
from core.edge import Recommendation
from core.feature_store import FeatureValue
from core.markets import Market, MarketSnapshot
from core.modeling import ModelArtifact
from core.raw_store import RawObject


class DbExecutor(Protocol):
    def execute(self, sql: str, params: tuple[Any, ...]) -> Any:
        """Execute SQL with DB-API style positional parameters."""


class PostgresRepository:
    """Thin persistence adapter.

    It is intentionally driver-agnostic so the project can use psycopg in production
    without making local tests depend on a database driver.
    """

    def __init__(self, db: DbExecutor):
        self.db = db

    def upsert_data_snapshot(self, data_snapshot_id: str, description: str | None = None) -> None:
        self.db.execute(
            """
            INSERT INTO data_snapshots (data_snapshot_id, description)
            VALUES (%s, %s)
            ON CONFLICT (data_snapshot_id) DO UPDATE SET
              description = COALESCE(EXCLUDED.description, data_snapshots.description)
            """,
            (
                data_snapshot_id,
                description,
            ),
        )

    def upsert_raw_object(self, obj: RawObject) -> None:
        self.db.execute(
            """
            INSERT INTO raw_objects (source, source_id, url, content_hash, content_type, fetched_at, storage_uri)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source, source_id, content_hash) DO UPDATE SET
              fetched_at = EXCLUDED.fetched_at,
              storage_uri = EXCLUDED.storage_uri
            """,
            (
                obj.source,
                obj.source_id,
                obj.url,
                obj.content_hash,
                obj.content_type,
                obj.fetched_at,
                str(obj.body_path),
            ),
        )

    def upsert_participant(self, participant: Participant) -> None:
        self.db.execute(
            """
            INSERT INTO participants (participant_id, game_id, kind, display_name, source, source_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (participant_id) DO UPDATE SET
              display_name = EXCLUDED.display_name
            """,
            (
                participant.participant_id,
                participant.game_id,
                str(participant.kind),
                participant.display_name,
                participant.source,
                participant.source_id,
            ),
        )

    def upsert_competition(self, competition: Competition) -> None:
        self.db.execute(
            """
            INSERT INTO competitions (competition_id, game_id, name, tier, starts_at, ends_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (competition_id) DO UPDATE SET
              name = EXCLUDED.name,
              tier = EXCLUDED.tier,
              starts_at = EXCLUDED.starts_at,
              ends_at = EXCLUDED.ends_at
            """,
            (
                competition.competition_id,
                competition.game_id,
                competition.name,
                competition.tier,
                competition.starts_at,
                competition.ends_at,
            ),
        )

    def upsert_contest(self, contest: Contest) -> None:
        self.db.execute(
            """
            INSERT INTO contests
              (contest_id, game_id, competition_id, starts_at, participant_a_id, participant_b_id, format, status, match_stage, head_to_head)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (contest_id) DO UPDATE SET
              starts_at = EXCLUDED.starts_at,
              format = EXCLUDED.format,
              status = EXCLUDED.status,
              match_stage = EXCLUDED.match_stage,
              head_to_head = EXCLUDED.head_to_head
            """,
            (
                contest.contest_id,
                contest.game_id,
                contest.competition_id,
                contest.starts_at,
                contest.participant_a_id,
                contest.participant_b_id,
                contest.format,
                contest.status,
                contest.match_stage,
                json.dumps(contest.head_to_head) if contest.head_to_head is not None else None,
            ),
        )

    def upsert_contest_unit(self, unit: ContestUnit) -> None:
        self.db.execute(
            """
            INSERT INTO contest_units (unit_id, contest_id, sequence_number, unit_type, name, winner_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id) DO UPDATE SET
              name = EXCLUDED.name,
              winner_id = EXCLUDED.winner_id
            """,
            (
                unit.unit_id,
                unit.contest_id,
                unit.sequence_number,
                unit.unit_type,
                unit.name,
                unit.winner_id,
            ),
        )

    def insert_feature_value(self, feature: FeatureValue, data_snapshot_id: str | None = None) -> None:
        self.db.execute(
            """
            INSERT INTO feature_values (entity_id, feature_name, as_of, value, metadata, data_snapshot_id)
            VALUES (%s, %s, %s, %s::jsonb, '{}'::jsonb, %s)
            ON CONFLICT (entity_id, feature_name, as_of) DO UPDATE SET
              value = EXCLUDED.value,
              metadata = EXCLUDED.metadata,
              data_snapshot_id = EXCLUDED.data_snapshot_id
            """,
            (
                feature.entity_id,
                feature.name,
                feature.as_of,
                json.dumps(feature.value),
                data_snapshot_id,
            ),
        )

    def list_feature_summaries(self, feature_name: str | None = None, entity_prefix: str | None = None) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if feature_name is not None:
            where.append("feature_name = %s")
            params.append(feature_name)
        if entity_prefix is not None:
            where.append("entity_id LIKE %s")
            params.append(f"{entity_prefix}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        rows = self.db.execute(
            f"""
            SELECT feature_name, COUNT(*)::INT AS row_count, MIN(as_of) AS first_as_of, MAX(as_of) AS latest_as_of
            FROM feature_values
            {where_sql}
            GROUP BY feature_name
            ORDER BY feature_name
            """,
            tuple(params),
        )
        return [
            {
                "feature_name": row[0],
                "row_count": row[1],
                "first_as_of": row[2],
                "latest_as_of": row[3],
            }
            for row in rows
        ]

    def list_latest_feature_values(
        self,
        feature_name: str | None = None,
        entity_prefix: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if feature_name is not None:
            where.append("feature_name = %s")
            params.append(feature_name)
        if entity_prefix is not None:
            where.append("entity_id LIKE %s")
            params.append(f"{entity_prefix}%")
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        rows = self.db.execute(
            f"""
            SELECT entity_id, feature_name, as_of, value, data_snapshot_id
            FROM feature_values
            {where_sql}
            ORDER BY as_of DESC, entity_id, feature_name
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            {
                "entity_id": row[0],
                "feature_name": row[1],
                "as_of": row[2],
                "value": row[3],
                "data_snapshot_id": row[4],
            }
            for row in rows
        ]

    def summarize_raw_objects(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT source,
                   COUNT(*)::INT AS raw_objects,
                   MAX(fetched_at) AS latest_fetched_at
            FROM raw_objects
            GROUP BY source
            ORDER BY source
            """,
            (),
        )
        return [
            {
                "source": row[0],
                "raw_objects": row[1],
                "latest_fetched_at": row[2],
            }
            for row in rows
        ]

    def summarize_market_snapshots(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT COUNT(*)::INT AS snapshots,
                   MAX(taken_at) AS latest_taken_at
            FROM market_snapshots
            """,
            (),
        )
        return [
            {
                "snapshots": row[0],
                "latest_taken_at": row[1],
            }
            for row in rows
        ]

    def upsert_model_artifact(self, artifact: ModelArtifact) -> None:
        self.db.execute(
            """
            INSERT INTO model_artifacts
              (model_id, game_id, target, git_sha, data_snapshot_id, config_hash, feature_names, metrics, artifact_uri)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (model_id) DO UPDATE SET
              metrics = EXCLUDED.metrics,
              artifact_uri = EXCLUDED.artifact_uri
            """,
            (
                artifact.model_id,
                artifact.game_id,
                artifact.target,
                artifact.git_sha,
                artifact.data_snapshot_id,
                artifact.config_hash,
                json.dumps(list(artifact.feature_names)),
                json.dumps(artifact.metrics),
                artifact.artifact_uri,
            ),
        )

    def list_model_artifacts(self, target: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where_sql = "WHERE target = %s" if target is not None else ""
        params: tuple[Any, ...] = (target, limit) if target is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT model_id, game_id, target, data_snapshot_id, config_hash, feature_names, metrics, artifact_uri, created_at
            FROM model_artifacts
            {where_sql}
            ORDER BY created_at DESC, model_id
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "model_id": row[0],
                "game_id": row[1],
                "target": row[2],
                "data_snapshot_id": row[3],
                "config_hash": row[4],
                "feature_names": row[5],
                "metrics": row[6],
                "artifact_uri": row[7],
                "created_at": row[8],
            }
            for row in rows
        ]

    def upsert_recommendation(
        self,
        recommendation: Recommendation,
        strategy_id: str,
        model_id: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO recommendations
              (market_id, outcome, taken_at, model_id, model_prob, market_prob, edge, bankroll_fraction, passes_filter, reason, strategy_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id, outcome, taken_at, strategy_id) DO UPDATE SET
              model_id = EXCLUDED.model_id,
              model_prob = EXCLUDED.model_prob,
              market_prob = EXCLUDED.market_prob,
              edge = EXCLUDED.edge,
              bankroll_fraction = EXCLUDED.bankroll_fraction,
              passes_filter = EXCLUDED.passes_filter,
              reason = EXCLUDED.reason
            """,
            (
                recommendation.market_id,
                recommendation.outcome,
                recommendation.taken_at,
                model_id,
                recommendation.model_prob,
                recommendation.market_prob,
                recommendation.edge,
                recommendation.bankroll_fraction,
                recommendation.passes_filter,
                recommendation.reason,
                strategy_id,
            ),
        )

    def list_recommendation_summaries(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id,) if strategy_id is not None else ()
        rows = self.db.execute(
            f"""
            SELECT strategy_id, COUNT(*)::INT AS candidates, COUNT(*) FILTER (WHERE passes_filter)::INT AS recommendations,
                   AVG(edge) FILTER (WHERE passes_filter) AS mean_edge,
                   SUM(bankroll_fraction) FILTER (WHERE passes_filter) AS total_bankroll_fraction
            FROM recommendations
            {where_sql}
            GROUP BY strategy_id
            ORDER BY strategy_id
            """,
            params,
        )
        return [
            {
                "strategy_id": row[0],
                "candidates": row[1],
                "recommendations": row[2],
                "mean_edge": row[3],
                "total_bankroll_fraction": row[4],
            }
            for row in rows
        ]

    def list_recommendations(
        self,
        strategy_id: str | None = None,
        passes_filter: bool | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where: list[str] = []
        params: list[Any] = []
        if strategy_id is not None:
            where.append("strategy_id = %s")
            params.append(strategy_id)
        if passes_filter is not None:
            where.append("passes_filter = %s")
            params.append(passes_filter)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        rows = self.db.execute(
            f"""
            SELECT recommendation_id, market_id, outcome, taken_at, model_id, model_prob, market_prob, edge,
                   bankroll_fraction, passes_filter, reason, strategy_id
            FROM recommendations
            {where_sql}
            ORDER BY taken_at DESC, recommendation_id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return [
            {
                "recommendation_id": row[0],
                "market_id": row[1],
                "outcome": row[2],
                "taken_at": row[3],
                "model_id": row[4],
                "model_prob": row[5],
                "market_prob": row[6],
                "edge": row[7],
                "bankroll_fraction": row[8],
                "passes_filter": row[9],
                "reason": row[10],
                "strategy_id": row[11],
            }
            for row in rows
        ]

    def list_console_recommendations(
        self,
        identifier: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        where_sql = "WHERE r.market_id = %s OR r.recommendation_id::text = %s" if identifier is not None else ""
        params: tuple[Any, ...] = (identifier, identifier, limit) if identifier is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT r.recommendation_id, r.market_id, r.outcome, r.taken_at, r.model_id,
                   r.model_prob, r.market_prob, r.edge, r.bankroll_fraction, r.passes_filter,
                   r.reason, r.strategy_id, m.question, m.market_type, c.contest_id,
                   c.starts_at, c.format, c.status, pa.display_name AS participant_a,
                   pb.display_name AS participant_b, comp.tier, m.polymarket_meta
            FROM recommendations r
            LEFT JOIN markets m ON m.market_id = r.market_id
            LEFT JOIN contests c ON c.contest_id = m.contest_id
            LEFT JOIN participants pa ON pa.participant_id = c.participant_a_id
            LEFT JOIN participants pb ON pb.participant_id = c.participant_b_id
            LEFT JOIN competitions comp ON comp.competition_id = c.competition_id
            {where_sql}
            ORDER BY r.taken_at DESC, r.recommendation_id DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "recommendation_id": row[0],
                "market_id": row[1],
                "outcome": row[2],
                "taken_at": row[3],
                "model_id": row[4],
                "model_prob": row[5],
                "market_prob": row[6],
                "edge": row[7],
                "bankroll_fraction": row[8],
                "passes_filter": row[9],
                "reason": row[10],
                "strategy_id": row[11],
                "question": row[12],
                "market_type": row[13],
                "contest_id": row[14],
                "starts_at": row[15],
                "format": row[16],
                "status": row[17],
                "participant_a": row[18],
                "participant_b": row[19],
                "tier": row[20],
                "polymarket_meta": row[21],
            }
            for row in rows
        ]

    def list_console_matches(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT c.contest_id, c.starts_at, c.format, c.status,
                   pa.display_name AS participant_a, pb.display_name AS participant_b,
                   comp.tier,
                   COUNT(DISTINCT m.market_id)::INT AS open_markets,
                   COUNT(DISTINCT r.recommendation_id) FILTER (WHERE r.passes_filter)::INT AS recommendations,
                   COALESCE(SUM(r.bankroll_fraction) FILTER (WHERE r.passes_filter), 0) AS exposure_fraction,
                   COALESCE(MAX(r.edge), 0) AS best_edge
            FROM contests c
            LEFT JOIN participants pa ON pa.participant_id = c.participant_a_id
            LEFT JOIN participants pb ON pb.participant_id = c.participant_b_id
            LEFT JOIN competitions comp ON comp.competition_id = c.competition_id
            LEFT JOIN markets m ON m.contest_id = c.contest_id
            LEFT JOIN recommendations r ON r.market_id = m.market_id
            WHERE c.game_id = 'counter_strike'
            GROUP BY c.contest_id, c.starts_at, c.format, c.status, pa.display_name, pb.display_name, comp.tier
            -- Surface contests that actually have markets first, then the most recent,
            -- so linked/actionable matches are visible instead of the oldest in history.
            ORDER BY COUNT(DISTINCT m.market_id) DESC, c.starts_at DESC, c.contest_id
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "contest_id": row[0],
                "starts_at": row[1],
                "format": row[2],
                "status": row[3],
                "participant_a": row[4],
                "participant_b": row[5],
                "tier": row[6],
                "open_markets": row[7],
                "recommendations": row[8],
                "exposure_fraction": row[9],
                "best_edge": row[10],
            }
            for row in rows
        ]

    def list_console_match_markets(self, contest_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT m.market_id, m.question, r.outcome, r.edge, r.bankroll_fraction,
                   r.passes_filter, r.reason
            FROM markets m
            LEFT JOIN recommendations r ON r.market_id = m.market_id
            WHERE m.contest_id = %s
            ORDER BY COALESCE(r.edge, 0) DESC, m.market_id, r.recommendation_id DESC
            LIMIT %s
            """,
            (contest_id, limit),
        )
        return [
            {
                "market_id": row[0],
                "question": row[1],
                "outcome": row[2],
                "edge": row[3],
                "bankroll_fraction": row[4],
                "passes_filter": row[5],
                "reason": row[6],
            }
            for row in rows
        ]

    def upsert_paper_bet_from_recommendation(
        self,
        recommendation: dict[str, Any],
        bankroll_usd: float,
    ) -> None:
        stake_usd = float(recommendation["bankroll_fraction"] or 0.0) * bankroll_usd
        self.db.execute(
            """
            INSERT INTO bets
              (recommendation_id, market_id, outcome, placed_at, model_prob, market_prob, edge, kelly_fraction,
               stake_usd, price_in, strategy_id, model_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (recommendation_id, strategy_id) WHERE recommendation_id IS NOT NULL DO UPDATE SET
              model_prob = EXCLUDED.model_prob,
              market_prob = EXCLUDED.market_prob,
              edge = EXCLUDED.edge,
              kelly_fraction = EXCLUDED.kelly_fraction,
              stake_usd = EXCLUDED.stake_usd,
              price_in = EXCLUDED.price_in,
              model_version = EXCLUDED.model_version
            """,
            (
                recommendation["recommendation_id"],
                recommendation["market_id"],
                recommendation["outcome"],
                recommendation["taken_at"],
                recommendation["model_prob"],
                recommendation["market_prob"],
                recommendation["edge"],
                recommendation["bankroll_fraction"],
                stake_usd,
                recommendation["market_prob"],
                recommendation["strategy_id"],
                recommendation["model_id"],
            ),
        )

    def insert_execution_bet(
        self,
        *,
        market_id: str,
        outcome: str,
        placed_at: Any,
        model_prob: float,
        market_prob: float,
        edge: float,
        kelly_fraction: float,
        stake_usd: float,
        price_in: float | None,
        strategy_id: str,
        model_version: str = "api_execution",
        mode: str = "paper",
    ) -> int | None:
        rows = self.db.execute(
            """
            INSERT INTO bets
              (market_id, outcome, placed_at, model_prob, market_prob, edge, kelly_fraction,
               stake_usd, price_in, strategy_id, model_version, mode)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING bet_id
            """,
            (
                market_id,
                outcome,
                placed_at,
                model_prob,
                market_prob,
                edge,
                kelly_fraction,
                stake_usd,
                price_in,
                strategy_id,
                model_version,
                mode,
            ),
        )
        return int(rows[0][0]) if rows else None

    def insert_order(
        self,
        *,
        order_id: str,
        bet_id: int | None,
        market_id: str,
        outcome: str,
        mode: str,
        side: str,
        size_usd: float,
        fill_price: float | None,
        order_status: str,
        token_id: str | None = None,
        polymarket_order_id: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO orders
              (order_id, bet_id, market_id, outcome, mode, side, size_usd, fill_price,
               fill_size_usd, order_status, polymarket_token_id, polymarket_order_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (order_id) DO UPDATE SET
              bet_id = COALESCE(EXCLUDED.bet_id, orders.bet_id),
              fill_price = EXCLUDED.fill_price,
              fill_size_usd = EXCLUDED.fill_size_usd,
              order_status = EXCLUDED.order_status,
              polymarket_token_id = COALESCE(EXCLUDED.polymarket_token_id, orders.polymarket_token_id),
              polymarket_order_id = COALESCE(EXCLUDED.polymarket_order_id, orders.polymarket_order_id),
              updated_at = now()
            """,
            (
                order_id,
                bet_id,
                market_id,
                outcome,
                mode,
                side,
                size_usd,
                fill_price,
                size_usd if fill_price is not None else None,
                order_status,
                token_id,
                polymarket_order_id,
            ),
        )

    def list_orders(self, market_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        where_sql = "WHERE market_id = %s" if market_id is not None else ""
        params: tuple[Any, ...] = (market_id, limit) if market_id is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT order_id, bet_id, market_id, outcome, mode, order_type, side,
                   limit_price, fill_price, size_usd, fill_size_usd, order_status,
                   polymarket_token_id, polymarket_order_id, tx_hash, created_at, updated_at
            FROM orders
            {where_sql}
            ORDER BY created_at DESC, order_id DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "order_id": row[0],
                "bet_id": row[1],
                "market_id": row[2],
                "outcome": row[3],
                "mode": row[4],
                "order_type": row[5],
                "side": row[6],
                "limit_price": row[7],
                "fill_price": row[8],
                "size_usd": row[9],
                "fill_size_usd": row[10],
                "order_status": row[11],
                "polymarket_token_id": row[12],
                "polymarket_order_id": row[13],
                "tx_hash": row[14],
                "created_at": row[15],
                "updated_at": row[16],
            }
            for row in rows
        ]

    def mark_order_cancelled(self, order_id: str) -> None:
        self.db.execute(
            """
            UPDATE orders
            SET order_status = 'cancelled',
                updated_at = now()
            WHERE order_id = %s OR polymarket_order_id = %s
            """,
            (order_id, order_id),
        )

    def reconcile_polymarket_trades_to_orders(self) -> int:
        rows = self.db.execute(
            """
            WITH trade_summary AS (
              SELECT
                order_id,
                SUM(size * price) / NULLIF(SUM(size), 0) AS fill_price,
                SUM(size * price) AS fill_size_usd,
                MAX(tx_hash) FILTER (WHERE tx_hash IS NOT NULL) AS tx_hash
              FROM polymarket_trades
              WHERE order_id IS NOT NULL
              GROUP BY order_id
            )
            UPDATE orders o
            SET fill_price = COALESCE(ts.fill_price, o.fill_price),
                fill_size_usd = COALESCE(ts.fill_size_usd, o.fill_size_usd),
                tx_hash = COALESCE(ts.tx_hash, o.tx_hash),
                order_status = CASE
                  WHEN COALESCE(ts.fill_size_usd, 0) >= o.size_usd * 0.999 THEN 'filled'
                  WHEN COALESCE(ts.fill_size_usd, 0) > 0 THEN 'partial'
                  ELSE o.order_status
                END,
                updated_at = now()
            FROM trade_summary ts
            WHERE o.order_id = ts.order_id OR o.polymarket_order_id = ts.order_id
            RETURNING o.order_id
            """,
            (),
        )
        return len(rows or [])

    def settle_bets_from_polymarket_resolutions(self, strategy_id: str | None = None) -> int:
        strategy_filter = "AND b.strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id,) if strategy_id is not None else ()
        rows = self.db.execute(
            f"""
            WITH resolved AS (
              SELECT
                b.bet_id,
                m.resolved_outcome,
                CASE WHEN m.resolved_outcome = b.outcome THEN 1.0::numeric ELSE 0.0::numeric END AS close_price
              FROM bets b
              JOIN markets m ON m.market_id = b.market_id
              WHERE m.source = 'polymarket'
                AND m.resolved_outcome IS NOT NULL
                AND b.resolved_outcome IS NULL
                AND b.price_in IS NOT NULL
                AND b.price_in > 0
                {strategy_filter}
            )
            UPDATE bets b
            SET price_close = r.close_price,
                clv = r.close_price - b.price_in,
                resolved_outcome = r.resolved_outcome,
                pnl_usd = CASE
                  WHEN r.resolved_outcome = b.outcome THEN b.stake_usd * ((1 / b.price_in) - 1)
                  ELSE -b.stake_usd
                END
            FROM resolved r
            WHERE b.bet_id = r.bet_id
            RETURNING b.bet_id
            """,
            params,
        )
        return len(rows or [])

    def upsert_polymarket_account_order(self, raw: dict[str, Any]) -> None:
        self.db.execute(
            """
            INSERT INTO polymarket_account_orders
              (order_id, market_id, token_id, side, outcome, original_size, size_matched,
               price, status, order_type, created_at, raw)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (order_id) DO UPDATE SET
              market_id = EXCLUDED.market_id,
              token_id = EXCLUDED.token_id,
              side = EXCLUDED.side,
              outcome = EXCLUDED.outcome,
              original_size = EXCLUDED.original_size,
              size_matched = EXCLUDED.size_matched,
              price = EXCLUDED.price,
              status = EXCLUDED.status,
              order_type = EXCLUDED.order_type,
              created_at = EXCLUDED.created_at,
              raw = EXCLUDED.raw,
              ingested_at = now()
            """,
            (
                str(raw.get("id") or raw.get("order_id") or raw.get("orderID") or ""),
                _text_or_none(raw.get("market")),
                _text_or_none(raw.get("asset_id") or raw.get("tokenID") or raw.get("token_id")),
                _text_or_none(raw.get("side")),
                _text_or_none(raw.get("outcome")),
                _numeric_or_none(raw.get("original_size") or raw.get("size")),
                _numeric_or_none(raw.get("size_matched") or raw.get("filled_size")),
                _numeric_or_none(raw.get("price")),
                _text_or_none(raw.get("status")),
                _text_or_none(raw.get("order_type") or raw.get("type")),
                _text_or_none(raw.get("created_at") or raw.get("createdAt")),
                json.dumps(raw),
            ),
        )

    def upsert_polymarket_trade(self, raw: dict[str, Any]) -> None:
        self.db.execute(
            """
            INSERT INTO polymarket_trades
              (trade_id, order_id, market_id, token_id, side, outcome, size, price,
               status, tx_hash, matched_at, raw)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (trade_id) DO UPDATE SET
              order_id = EXCLUDED.order_id,
              market_id = EXCLUDED.market_id,
              token_id = EXCLUDED.token_id,
              side = EXCLUDED.side,
              outcome = EXCLUDED.outcome,
              size = EXCLUDED.size,
              price = EXCLUDED.price,
              status = EXCLUDED.status,
              tx_hash = EXCLUDED.tx_hash,
              matched_at = EXCLUDED.matched_at,
              raw = EXCLUDED.raw,
              ingested_at = now()
            """,
            (
                str(raw.get("id") or raw.get("trade_id") or ""),
                _text_or_none(raw.get("taker_order_id") or raw.get("order_id") or raw.get("orderId")),
                _text_or_none(raw.get("market")),
                _text_or_none(raw.get("asset_id") or raw.get("assetId") or raw.get("token_id")),
                _text_or_none(raw.get("side")),
                _text_or_none(raw.get("outcome")),
                _numeric_or_none(raw.get("size")),
                _numeric_or_none(raw.get("price")),
                _text_or_none(raw.get("status")),
                _text_or_none(raw.get("transactionHash") or raw.get("tx_hash")),
                _text_or_none(raw.get("matchTime") or raw.get("matched_at") or raw.get("created_at")),
                json.dumps(raw),
            ),
        )

    def list_paper_bets(self, strategy_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id, limit) if strategy_id is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT bet_id, recommendation_id, market_id, outcome, placed_at, model_prob, market_prob, edge,
                   kelly_fraction, stake_usd, price_in, price_close, clv, resolved_outcome, pnl_usd,
                   model_version, strategy_id, mode
            FROM bets
            {where_sql}
            ORDER BY placed_at DESC, bet_id DESC
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "bet_id": row[0],
                "recommendation_id": row[1],
                "market_id": row[2],
                "outcome": row[3],
                "placed_at": row[4],
                "model_prob": row[5],
                "market_prob": row[6],
                "edge": row[7],
                "kelly_fraction": row[8],
                "stake_usd": row[9],
                "price_in": row[10],
                "price_close": row[11],
                "clv": row[12],
                "resolved_outcome": row[13],
                "pnl_usd": row[14],
                "model_version": row[15],
                "strategy_id": row[16],
                "mode": row[17],
            }
            for row in rows
        ]

    def summarize_paper_bets(self, strategy_id: str | None = None) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id,) if strategy_id is not None else ()
        rows = self.db.execute(
            f"""
            SELECT strategy_id,
                   COUNT(*)::INT AS bets,
                   COUNT(*) FILTER (WHERE resolved_outcome IS NOT NULL)::INT AS settled_bets,
                   COUNT(*) FILTER (WHERE resolved_outcome IS NULL)::INT AS open_bets,
                   SUM(stake_usd) AS stake_usd,
                   SUM(pnl_usd) FILTER (WHERE pnl_usd IS NOT NULL) AS pnl_usd,
                   SUM(pnl_usd) FILTER (WHERE pnl_usd IS NOT NULL) / NULLIF(SUM(stake_usd) FILTER (WHERE pnl_usd IS NOT NULL), 0) AS roi,
                   AVG(clv) FILTER (WHERE clv IS NOT NULL) AS mean_clv,
                   COUNT(*) FILTER (WHERE pnl_usd > 0)::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE resolved_outcome IS NOT NULL), 0) AS hit_rate,
                   MIN(placed_at) AS first_placed_at,
                   MAX(placed_at) AS latest_placed_at
            FROM bets
            {where_sql}
            GROUP BY strategy_id
            ORDER BY strategy_id
            """,
            params,
        )
        return [
            {
                "strategy_id": row[0],
                "bets": row[1],
                "settled_bets": row[2],
                "open_bets": row[3],
                "stake_usd": row[4],
                "pnl_usd": row[5],
                "roi": row[6],
                "mean_clv": row[7],
                "hit_rate": row[8],
                "first_placed_at": row[9],
                "latest_placed_at": row[10],
            }
            for row in rows
        ]

    def summarize_paper_bets_by_day(self, strategy_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id, limit) if strategy_id is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT placed_at::date AS placed_date,
                   strategy_id,
                   COUNT(*)::INT AS bets,
                   COUNT(*) FILTER (WHERE resolved_outcome IS NOT NULL)::INT AS settled_bets,
                   SUM(stake_usd) AS stake_usd,
                   SUM(pnl_usd) FILTER (WHERE pnl_usd IS NOT NULL) AS pnl_usd,
                   SUM(pnl_usd) FILTER (WHERE pnl_usd IS NOT NULL) / NULLIF(SUM(stake_usd) FILTER (WHERE pnl_usd IS NOT NULL), 0) AS roi,
                   AVG(clv) FILTER (WHERE clv IS NOT NULL) AS mean_clv,
                   COUNT(*) FILTER (WHERE pnl_usd > 0)::NUMERIC / NULLIF(COUNT(*) FILTER (WHERE resolved_outcome IS NOT NULL), 0) AS hit_rate
            FROM bets
            {where_sql}
            GROUP BY placed_at::date, strategy_id
            ORDER BY placed_date DESC, strategy_id
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "placed_date": row[0],
                "strategy_id": row[1],
                "bets": row[2],
                "settled_bets": row[3],
                "stake_usd": row[4],
                "pnl_usd": row[5],
                "roi": row[6],
                "mean_clv": row[7],
                "hit_rate": row[8],
            }
            for row in rows
        ]

    def update_paper_bet_settlement(
        self,
        market_id: str,
        outcome: str,
        price_close: float | None,
        resolved_outcome: str | None,
        strategy_id: str | None = None,
    ) -> None:
        strategy_filter = "AND strategy_id = %s" if strategy_id is not None else ""
        params: list[Any] = [
            price_close,
            price_close,
            price_close,
            resolved_outcome,
            resolved_outcome,
            resolved_outcome,
            market_id,
            outcome,
        ]
        if strategy_id is not None:
            params.append(strategy_id)
        self.db.execute(
            f"""
            UPDATE bets
            SET price_close = COALESCE(%s::numeric, price_close),
                clv = CASE WHEN %s::numeric IS NULL THEN clv ELSE %s::numeric - price_in END,
                resolved_outcome = COALESCE(%s::text, resolved_outcome),
                pnl_usd = CASE
                  WHEN %s::text IS NULL THEN pnl_usd
                  WHEN %s::text = outcome THEN stake_usd * ((1 / price_in) - 1)
                  ELSE -stake_usd
                END
            WHERE market_id = %s
              AND outcome = %s
              {strategy_filter}
            """,
            tuple(params),
        )

    def upsert_report_artifact(
        self,
        report_id: str,
        strategy_id: str,
        report_type: str,
        artifact_uri: str,
        metrics: dict[str, Any],
        readiness: dict[str, Any],
    ) -> None:
        self.db.execute(
            """
            INSERT INTO report_artifacts (report_id, strategy_id, report_type, artifact_uri, metrics, readiness)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb)
            ON CONFLICT (report_id) DO UPDATE SET
              artifact_uri = EXCLUDED.artifact_uri,
              metrics = EXCLUDED.metrics,
              readiness = EXCLUDED.readiness
            """,
            (
                report_id,
                strategy_id,
                report_type,
                artifact_uri,
                json.dumps(metrics),
                json.dumps(readiness),
            ),
        )

    def list_report_artifacts(self, strategy_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id, limit) if strategy_id is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT report_id, strategy_id, report_type, artifact_uri, metrics, readiness, created_at
            FROM report_artifacts
            {where_sql}
            ORDER BY created_at DESC, report_id
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "report_id": row[0],
                "strategy_id": row[1],
                "report_type": row[2],
                "artifact_uri": row[3],
                "metrics": row[4],
                "readiness": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]

    def upsert_backtest_run(
        self,
        backtest_run_id: str,
        strategy_id: str,
        game_id: str,
        target: str,
        data_snapshot_id: str | None,
        run_config: dict[str, Any],
        metrics: dict[str, Any],
        window_results: list[dict[str, Any]],
        artifact_uri: str | None = None,
    ) -> None:
        self.db.execute(
            """
            INSERT INTO backtest_runs
              (backtest_run_id, strategy_id, game_id, target, data_snapshot_id, run_config, metrics, window_results, artifact_uri)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
            ON CONFLICT (backtest_run_id) DO UPDATE SET
              run_config = EXCLUDED.run_config,
              metrics = EXCLUDED.metrics,
              window_results = EXCLUDED.window_results,
              artifact_uri = EXCLUDED.artifact_uri
            """,
            (
                backtest_run_id,
                strategy_id,
                game_id,
                target,
                data_snapshot_id,
                json.dumps(run_config),
                json.dumps(metrics),
                json.dumps(window_results),
                artifact_uri,
            ),
        )

    def list_backtest_runs(self, strategy_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        where_sql = "WHERE strategy_id = %s" if strategy_id is not None else ""
        params: tuple[Any, ...] = (strategy_id, limit) if strategy_id is not None else (limit,)
        rows = self.db.execute(
            f"""
            SELECT backtest_run_id, strategy_id, game_id, target, data_snapshot_id, run_config, metrics,
                   window_results, artifact_uri, created_at
            FROM backtest_runs
            {where_sql}
            ORDER BY created_at DESC, backtest_run_id
            LIMIT %s
            """,
            params,
        )
        return [
            {
                "backtest_run_id": row[0],
                "strategy_id": row[1],
                "game_id": row[2],
                "target": row[3],
                "data_snapshot_id": row[4],
                "run_config": row[5],
                "metrics": row[6],
                "window_results": row[7],
                "artifact_uri": row[8],
                "created_at": row[9],
            }
            for row in rows
        ]

    def upsert_market(self, market: Market) -> None:
        self.db.execute(
            """
            INSERT INTO markets (market_id, source, question, market_type, contest_id, outcomes, created_at, resolved_at, resolved_outcome)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (market_id) DO UPDATE SET
              question = EXCLUDED.question,
              market_type = EXCLUDED.market_type,
              contest_id = EXCLUDED.contest_id,
              outcomes = EXCLUDED.outcomes,
              resolved_at = EXCLUDED.resolved_at,
              resolved_outcome = EXCLUDED.resolved_outcome
            """,
            (
                market.market_id,
                market.source,
                market.question,
                market.market_type,
                market.contest_id,
                json.dumps(list(market.outcomes)),
                market.created_at,
                market.resolved_at,
                market.resolved_outcome,
            ),
        )

    def update_market_polymarket_meta(self, market_id: str, meta: dict[str, Any], description: str = "") -> None:
        self.db.execute(
            """
            UPDATE markets
            SET polymarket_meta = %s::jsonb,
                description = %s
            WHERE market_id = %s
            """,
            (json.dumps(meta), description, market_id),
        )

    def list_polymarket_tokens_for_price_history(self, limit: int = 100, closed_only: bool = False) -> list[dict[str, Any]]:
        closed_filter = """
            AND (
              m.resolved_outcome IS NOT NULL
              OR COALESCE((m.polymarket_meta->>'closed')::boolean, false)
            )
        """ if closed_only else ""
        rows = self.db.execute(
            f"""
            SELECT
                m.market_id,
                token->>'outcome' AS outcome,
                token->>'token_id' AS token_id
            FROM markets m
            CROSS JOIN LATERAL jsonb_array_elements(COALESCE(m.polymarket_meta->'tokens', '[]'::jsonb)) AS token
            WHERE m.source = 'polymarket'
              AND m.polymarket_meta IS NOT NULL
              AND token->>'token_id' IS NOT NULL
              {closed_filter}
            ORDER BY m.created_at DESC NULLS LAST, m.market_id
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "market_id": row[0],
                "outcome": row[1],
                "token_id": row[2],
            }
            for row in rows
        ]

    def insert_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        self.db.execute(
            """
            INSERT INTO market_snapshots (market_id, outcome, taken_at, best_bid, best_ask, last_trade_price, depth_bid_1pct, depth_ask_1pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (market_id, outcome, taken_at) DO NOTHING
            """,
            (
                snapshot.market_id,
                snapshot.outcome,
                snapshot.taken_at,
                snapshot.best_bid,
                snapshot.best_ask,
                snapshot.last_trade_price,
                snapshot.depth_bid_1pct,
                snapshot.depth_ask_1pct,
            ),
        )

    def list_edge_comparison_rows(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            WITH latest_snapshots AS (
                SELECT DISTINCT ON (ms.market_id, ms.outcome)
                    ms.market_id, ms.outcome, ms.best_bid, ms.best_ask,
                    ms.last_trade_price, ms.taken_at
                FROM market_snapshots ms
                ORDER BY ms.market_id, ms.outcome, ms.taken_at DESC
            )
            SELECT
                m.contest_id,
                COALESCE(
                    (SELECT pa.display_name FROM participants pa WHERE pa.participant_id = c.participant_a_id)
                    || ' vs ' ||
                    (SELECT pb.display_name FROM participants pb WHERE pb.participant_id = c.participant_b_id),
                    m.question
                ) AS match_label,
                m.market_type,
                ls.outcome,
                r.model_prob,
                CASE WHEN m.source = 'polymarket' THEN
                    CASE WHEN ls.best_bid IS NOT NULL AND ls.best_ask IS NOT NULL
                        THEN (ls.best_bid + ls.best_ask) / 2
                        ELSE ls.last_trade_price END
                END AS pm_prob,
                CASE WHEN m.source = 'polymarket' THEN ls.best_bid END AS pm_bid,
                CASE WHEN m.source = 'polymarket' THEN ls.best_ask END AS pm_ask,
                (m.polymarket_meta->>'volume_usd')::numeric AS pm_volume
            FROM markets m
            JOIN latest_snapshots ls ON ls.market_id = m.market_id
            LEFT JOIN contests c ON c.contest_id = m.contest_id
            LEFT JOIN recommendations r ON r.market_id = m.market_id AND r.outcome = ls.outcome
            WHERE m.source = 'polymarket'
            ORDER BY ls.taken_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [
            {
                "contest_id": row[0] or "",
                "match_label": row[1] or "",
                "market_type": row[2] or "",
                "outcome": row[3] or "",
                "model_prob": float(row[4]) if row[4] is not None else None,
                "pm_prob": float(row[5]) if row[5] is not None else None,
                "pm_bid": float(row[6]) if row[6] is not None else None,
                "pm_ask": float(row[7]) if row[7] is not None else None,
                "pm_volume": float(row[8]) if row[8] is not None else None,
            }
            for row in rows
        ]

    def update_market_link(
        self,
        market_id: str,
        contest_id: str | None,
        outcome_mapping: dict[str, str] | None,
        link_confidence: float,
    ) -> None:
        self.db.execute(
            """
            UPDATE markets
            SET contest_id = %s,
                outcome_mapping = %s::jsonb,
                link_confidence = %s
            WHERE market_id = %s
            """,
            (
                contest_id,
                json.dumps(outcome_mapping) if outcome_mapping is not None else None,
                link_confidence,
                market_id,
            ),
        )

    def list_participants(self, game_id: str | None = None) -> list[Participant]:
        where = "WHERE game_id = %s" if game_id else ""
        params: tuple[Any, ...] = (game_id,) if game_id else ()
        rows = self.db.execute(
            f"""
            SELECT participant_id, game_id, kind, display_name, source, source_id
            FROM participants
            {where}
            """,
            params,
        )
        return [
            Participant(
                participant_id=row[0],
                game_id=row[1],
                kind=ParticipantKind(row[2]),
                display_name=row[3],
                source=row[4] or "",
                source_id=row[5] or "",
            )
            for row in rows
        ]

    def list_contests(self, game_id: str | None = None) -> list[Contest]:
        where = "WHERE game_id = %s" if game_id else ""
        params: tuple[Any, ...] = (game_id,) if game_id else ()
        rows = self.db.execute(
            f"""
            SELECT contest_id, game_id, competition_id, starts_at,
                   participant_a_id, participant_b_id, format, status,
                   match_stage, head_to_head
            FROM contests
            {where}
            """,
            params,
        )
        return [
            Contest(
                contest_id=row[0],
                game_id=row[1],
                competition_id=row[2],
                starts_at=row[3],
                participant_a_id=row[4],
                participant_b_id=row[5],
                format=row[6],
                status=row[7],
                match_stage=row[8],
                head_to_head=row[9],
            )
            for row in rows
        ]

    def list_unlinked_markets(self, source: str = "polymarket") -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT market_id, question, outcomes, created_at, resolved_at
            FROM markets
            WHERE source = %s AND contest_id IS NULL
            """,
            (source,),
        )
        return [
            {
                "market_id": row[0],
                "question": row[1],
                "outcomes": list(row[2]) if row[2] is not None else [],
                "created_at": row[3],
                "resolved_at": row[4],
            }
            for row in rows
        ]


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _numeric_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
