from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from core.feature_store import FeatureValue
from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMatch


FEATURE_NAME_30D = "cs.team.map_win_rate_30d"
FEATURE_NAME_90D = "cs.team.map_win_rate_90d"
FEATURE_NAME_180D = "cs.team.map_win_rate_180d"

# Keep legacy alias so existing imports of FEATURE_NAME still work.
FEATURE_NAME = FEATURE_NAME_90D


def materialize_map_win_rate(matches: list[CsParsedMatch], as_of: datetime, *, days: int) -> list[FeatureValue]:
    feature_name = f"cs.team.map_win_rate_{days}d"
    window_start = as_of - timedelta(days=days)
    counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for match in matches:
        if match.status != "finished":
            continue
        if not (window_start <= match.scheduled_at < as_of):
            continue
        team_a_id = cs_participant_id("hltv", match.team_a.hltv_id)
        team_b_id = cs_participant_id("hltv", match.team_b.hltv_id)
        for played_map in match.maps:
            for team_id in (team_a_id, team_b_id):
                counts[(team_id, played_map.map_name)][1] += 1
            winner_id = cs_participant_id("hltv", played_map.winner_hltv_id)
            counts[(winner_id, played_map.map_name)][0] += 1

    features: list[FeatureValue] = []
    for (team_id, map_name), (wins, played) in sorted(counts.items()):
        entity_id = f"{team_id}:map:{map_name}"
        features.append(
            FeatureValue(
                entity_id=entity_id,
                name=feature_name,
                as_of=as_of,
                value={"map_name": map_name, "wins": wins, "maps_played": played, "win_rate": wins / played if played else None},
            )
        )
    return features


def materialize_map_win_rate_30d(matches: list[CsParsedMatch], as_of: datetime) -> list[FeatureValue]:
    return materialize_map_win_rate(matches, as_of, days=30)


def materialize_map_win_rate_90d(matches: list[CsParsedMatch], as_of: datetime) -> list[FeatureValue]:
    return materialize_map_win_rate(matches, as_of, days=90)


def materialize_map_win_rate_180d(matches: list[CsParsedMatch], as_of: datetime) -> list[FeatureValue]:
    return materialize_map_win_rate(matches, as_of, days=180)
