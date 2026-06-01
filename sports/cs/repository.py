from __future__ import annotations

from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMap, CsParsedPlayerMapStats, CsParsedVeto


class CsRepository:
    """Counter-Strike table persistence."""

    def __init__(self, db) -> None:
        self.db = db

    def upsert_map_result(self, unit_id: str, parsed_map: CsParsedMap) -> None:
        self.db.execute(
            """
            INSERT INTO cs_map_results
              (unit_id, map_name, team_a_score, team_b_score,
               map_stats_id, overtime, team_a_first_half, team_a_second_half,
               team_b_first_half, team_b_second_half)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id) DO UPDATE SET
              map_name = EXCLUDED.map_name,
              team_a_score = EXCLUDED.team_a_score,
              team_b_score = EXCLUDED.team_b_score,
              map_stats_id = EXCLUDED.map_stats_id,
              overtime = EXCLUDED.overtime,
              team_a_first_half = EXCLUDED.team_a_first_half,
              team_a_second_half = EXCLUDED.team_a_second_half,
              team_b_first_half = EXCLUDED.team_b_first_half,
              team_b_second_half = EXCLUDED.team_b_second_half
            """,
            (
                unit_id,
                parsed_map.map_name,
                parsed_map.team_a_score,
                parsed_map.team_b_score,
                parsed_map.map_stats_id,
                parsed_map.overtime,
                parsed_map.team_a_first_half,
                parsed_map.team_a_second_half,
                parsed_map.team_b_first_half,
                parsed_map.team_b_second_half,
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

    def upsert_map_lineup(self, unit_id: str, team_id: str, player_id: str) -> None:
        self.db.execute(
            """
            INSERT INTO cs_map_lineups (unit_id, team_id, player_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (unit_id, player_id) DO UPDATE SET
              team_id = EXCLUDED.team_id
            """,
            (unit_id, team_id, player_id),
        )

    def upsert_player_map_stats(self, unit_id: str, stats: CsParsedPlayerMapStats) -> None:
        player_id = cs_participant_id("hltv", stats.player_hltv_id)
        team_id = cs_participant_id("hltv", stats.team_hltv_id)
        self.db.execute(
            """
            INSERT INTO cs_player_map_stats
              (unit_id, player_id, team_id,
               kills, deaths, assists, adr, kast, rating_2_0, hs_pct,
               first_kills, first_deaths, clutches_won,
               ct_kills, ct_deaths, t_kills, t_deaths,
               flash_assists, trade_deaths)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (unit_id, player_id) DO UPDATE SET
              team_id = EXCLUDED.team_id,
              kills = EXCLUDED.kills,
              deaths = EXCLUDED.deaths,
              assists = EXCLUDED.assists,
              adr = EXCLUDED.adr,
              kast = EXCLUDED.kast,
              rating_2_0 = EXCLUDED.rating_2_0,
              hs_pct = EXCLUDED.hs_pct,
              first_kills = EXCLUDED.first_kills,
              first_deaths = EXCLUDED.first_deaths,
              clutches_won = EXCLUDED.clutches_won,
              ct_kills = EXCLUDED.ct_kills,
              ct_deaths = EXCLUDED.ct_deaths,
              t_kills = EXCLUDED.t_kills,
              t_deaths = EXCLUDED.t_deaths,
              flash_assists = EXCLUDED.flash_assists,
              trade_deaths = EXCLUDED.trade_deaths
            """,
            (
                unit_id,
                player_id,
                team_id,
                stats.kills,
                stats.deaths,
                stats.assists,
                stats.adr,
                stats.kast_pct,
                stats.rating,
                stats.headshot_pct,
                stats.first_kills,
                stats.first_deaths,
                stats.clutches_won,
                stats.ct_kills,
                stats.ct_deaths,
                stats.t_kills,
                stats.t_deaths,
                stats.flash_assists,
                stats.trade_deaths,
            ),
        )
