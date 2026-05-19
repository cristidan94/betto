from __future__ import annotations

from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMap, CsParsedVeto


class CsRepository:
    """Counter-Strike table persistence."""

    def __init__(self, db) -> None:
        self.db = db

    def upsert_map_result(self, unit_id: str, parsed_map: CsParsedMap) -> None:
        self.db.execute(
            """
            INSERT INTO cs_map_results (unit_id, map_name, team_a_score, team_b_score)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (unit_id) DO UPDATE SET
              map_name = EXCLUDED.map_name,
              team_a_score = EXCLUDED.team_a_score,
              team_b_score = EXCLUDED.team_b_score
            """,
            (
                unit_id,
                parsed_map.map_name,
                parsed_map.team_a_score,
                parsed_map.team_b_score,
            ),
        )

    def upsert_veto_action(self, contest_id: str, veto: CsParsedVeto) -> None:
        team_id = cs_participant_id("hltv", veto.team_hltv_id) if veto.team_hltv_id is not None else None
        self.db.execute(
            """
            INSERT INTO cs_veto_actions (contest_id, order_idx, team_id, action, map_name)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (contest_id, order_idx) DO UPDATE SET
              team_id = EXCLUDED.team_id,
              action = EXCLUDED.action,
              map_name = EXCLUDED.map_name
            """,
            (
                contest_id,
                veto.order_idx,
                team_id,
                veto.action,
                veto.map_name,
            ),
        )

