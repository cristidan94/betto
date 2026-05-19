from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sports.cs.features import materialize_map_glicko, materialize_map_win_rate_30d, materialize_map_win_rate_90d, materialize_map_win_rate_180d
from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMatch


@dataclass(frozen=True)
class MapWinnerTrainingRow:
    contest_hltv_id: str
    map_index: int
    map_name: str
    as_of: datetime
    team_id: str
    opponent_id: str
    target: int
    features: dict[str, float | int | None]


def build_map_winner_dataset(matches: list[CsParsedMatch]) -> list[MapWinnerTrainingRow]:
    sorted_matches = sorted(matches, key=lambda match: (match.scheduled_at, match.hltv_id))
    rows: list[MapWinnerTrainingRow] = []
    for index, match in enumerate(sorted_matches):
        if match.status != "finished":
            continue
        prior_matches = sorted_matches[:index]
        feature_lookup = _feature_lookup(prior_matches, match.scheduled_at)
        team_a_id = cs_participant_id("hltv", match.team_a.hltv_id)
        team_b_id = cs_participant_id("hltv", match.team_b.hltv_id)
        rest_days = _rest_days_lookup(prior_matches, match.scheduled_at)
        for played_map in match.maps:
            team_a_features = _row_features(feature_lookup, rest_days, team_a_id, team_b_id, played_map.map_name, match.best_of)
            team_b_features = _row_features(feature_lookup, rest_days, team_b_id, team_a_id, played_map.map_name, match.best_of)
            team_a_won = cs_participant_id("hltv", played_map.winner_hltv_id) == team_a_id
            rows.append(
                MapWinnerTrainingRow(
                    contest_hltv_id=match.hltv_id,
                    map_index=played_map.map_index,
                    map_name=played_map.map_name,
                    as_of=match.scheduled_at,
                    team_id=team_a_id,
                    opponent_id=team_b_id,
                    target=1 if team_a_won else 0,
                    features=team_a_features,
                )
            )
            rows.append(
                MapWinnerTrainingRow(
                    contest_hltv_id=match.hltv_id,
                    map_index=played_map.map_index,
                    map_name=played_map.map_name,
                    as_of=match.scheduled_at,
                    team_id=team_b_id,
                    opponent_id=team_a_id,
                    target=0 if team_a_won else 1,
                    features=team_b_features,
                )
            )
    return rows


def _feature_lookup(matches: list[CsParsedMatch], as_of: datetime) -> dict[str, dict[str, dict[str, float | int | None]]]:
    lookup: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for suffix, materializer in (("30d", materialize_map_win_rate_30d), ("90d", materialize_map_win_rate_90d), ("180d", materialize_map_win_rate_180d)):
        for feature in materializer(matches, as_of):
            lookup.setdefault(feature.entity_id, {})[suffix] = feature.value
    for feature in materialize_map_glicko(matches, as_of):
        lookup.setdefault(feature.entity_id, {})["glicko"] = feature.value
    return lookup


def _rest_days_lookup(matches: list[CsParsedMatch], as_of: datetime) -> dict[str, float]:
    latest_match_at: dict[str, datetime] = {}
    for match in matches:
        if match.status != "finished" or match.scheduled_at >= as_of:
            continue
        for team in (match.team_a, match.team_b):
            team_id = cs_participant_id("hltv", team.hltv_id)
            previous = latest_match_at.get(team_id)
            if previous is None or match.scheduled_at > previous:
                latest_match_at[team_id] = match.scheduled_at
    return {
        team_id: (as_of - played_at).total_seconds() / 86400
        for team_id, played_at in latest_match_at.items()
    }


def _row_features(
    feature_lookup: dict[str, dict[str, dict[str, float | int | None]]],
    rest_days_lookup: dict[str, float],
    team_id: str,
    opponent_id: str,
    map_name: str,
    best_of: int,
) -> dict[str, float | int | None]:
    team_features_by_window = feature_lookup.get(f"{team_id}:map:{map_name}", {})
    opponent_features_by_window = feature_lookup.get(f"{opponent_id}:map:{map_name}", {})
    team_rest_days = rest_days_lookup.get(team_id)
    opponent_rest_days = rest_days_lookup.get(opponent_id)
    rest_days_diff = None
    if team_rest_days is not None and opponent_rest_days is not None:
        rest_days_diff = team_rest_days - opponent_rest_days

    result: dict[str, float | int | None] = {
        "best_of": best_of,
        "team_rest_days": team_rest_days,
        "opponent_rest_days": opponent_rest_days,
        "rest_days_diff": rest_days_diff,
    }

    for suffix in ("30d", "90d", "180d"):
        team_feature = team_features_by_window.get(suffix, {})
        opponent_feature = opponent_features_by_window.get(suffix, {})
        team_win_rate = team_feature.get("win_rate")
        opponent_win_rate = opponent_feature.get("win_rate")
        diff = None
        if isinstance(team_win_rate, (int, float)) and isinstance(opponent_win_rate, (int, float)):
            diff = float(team_win_rate) - float(opponent_win_rate)
        result[f"team_map_win_rate_{suffix}"] = team_win_rate
        result[f"team_maps_played_{suffix}"] = team_feature.get("maps_played", 0)
        result[f"opponent_map_win_rate_{suffix}"] = opponent_win_rate
        result[f"opponent_maps_played_{suffix}"] = opponent_feature.get("maps_played", 0)
        result[f"map_win_rate_diff_{suffix}"] = diff

    # Glicko-2 features
    team_glicko = team_features_by_window.get("glicko", {})
    opponent_glicko = opponent_features_by_window.get("glicko", {})
    team_glicko_rating = team_glicko.get("rating")
    team_glicko_rd = team_glicko.get("rd")
    opponent_glicko_rating = opponent_glicko.get("rating")
    opponent_glicko_rd = opponent_glicko.get("rd")
    glicko_rating_diff = None
    if isinstance(team_glicko_rating, (int, float)) and isinstance(opponent_glicko_rating, (int, float)):
        glicko_rating_diff = float(team_glicko_rating) - float(opponent_glicko_rating)
    result["team_map_glicko_rating"] = team_glicko_rating
    result["team_map_glicko_rd"] = team_glicko_rd
    result["opponent_map_glicko_rating"] = opponent_glicko_rating
    result["opponent_map_glicko_rd"] = opponent_glicko_rd
    result["map_glicko_rating_diff"] = glicko_rating_diff

    return result
