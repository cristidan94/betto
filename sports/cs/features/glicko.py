from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from core.feature_store import FeatureValue
from sports.cs.normalization.ids import cs_participant_id
from sports.cs.normalization.records import CsParsedMatch


FEATURE_NAME = "cs.team.map_glicko"

# ----- Glicko-2 constants -----
INITIAL_RATING = 1500.0
INITIAL_RD = 350.0
INITIAL_VOLATILITY = 0.06
SCALE = 173.7178  # conversion factor between Glicko-1 and Glicko-2 scales
TAU = 0.5  # system constant constraining volatility change
EPSILON = 1e-6  # convergence threshold for Illinois algorithm
RD_GROWTH_PER_DAY = 1.0  # RD increase per day of inactivity (Glicko-1 scale)


@dataclass
class GlickoState:
    rating: float = INITIAL_RATING
    rd: float = INITIAL_RD
    volatility: float = INITIAL_VOLATILITY
    last_updated: datetime | None = None


# ----- Glicko-2 helper functions -----

def _to_glicko2(rating: float, rd: float) -> tuple[float, float]:
    """Convert from Glicko-1 scale to Glicko-2 scale."""
    mu = (rating - INITIAL_RATING) / SCALE
    phi = rd / SCALE
    return mu, phi


def _from_glicko2(mu: float, phi: float) -> tuple[float, float]:
    """Convert from Glicko-2 scale back to Glicko-1 scale."""
    rating = mu * SCALE + INITIAL_RATING
    rd = phi * SCALE
    return rating, rd


def _g(phi: float) -> float:
    """Glicko-2 g function: reduces impact of opponent's rating based on their RD."""
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    """Expected score E(mu, mu_j, phi_j)."""
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _update_volatility(sigma: float, phi: float, v: float, delta: float) -> float:
    """Update volatility using the Illinois algorithm (Glicko-2 Step 5)."""
    a = math.log(sigma * sigma)
    delta_sq = delta * delta
    phi_sq = phi * phi

    def f(x: float) -> float:
        ex = math.exp(x)
        num = ex * (delta_sq - phi_sq - v - ex)
        denom = 2.0 * (phi_sq + v + ex) ** 2
        return num / denom - (x - a) / (TAU * TAU)

    # Bracket the root
    lo = a
    if delta_sq > phi_sq + v:
        hi = math.log(delta_sq - phi_sq - v)
    else:
        k = 1
        while f(a - k * TAU) < 0:
            k += 1
        hi = a - k * TAU

    f_lo = f(lo)
    f_hi = f(hi)

    # Illinois algorithm (modified regula falsi) for convergence
    for _ in range(100):
        if abs(hi - lo) < EPSILON:
            break
        mid = lo + (lo - hi) * f_lo / (f_hi - f_lo)
        f_mid = f(mid)
        if f_mid * f_hi <= 0:
            lo = hi
            f_lo = f_hi
        else:
            f_lo /= 2.0
        hi = mid
        f_hi = f_mid

    return math.exp(hi / 2.0)


def update_glicko(
    state: GlickoState,
    opponent_rating: float,
    opponent_rd: float,
    score: float,
) -> GlickoState:
    """
    Perform a single Glicko-2 rating update.

    score: 1.0 for win, 0.0 for loss, 0.5 for draw.
    Returns a new GlickoState with updated values.
    """
    mu, phi = _to_glicko2(state.rating, state.rd)
    mu_j, phi_j = _to_glicko2(opponent_rating, opponent_rd)

    g_j = _g(phi_j)
    e_j = _expected(mu, mu_j, phi_j)

    # Step 3: Compute estimated variance
    v = 1.0 / (g_j * g_j * e_j * (1.0 - e_j))

    # Step 4: Compute delta (improvement)
    delta = v * g_j * (score - e_j)

    # Step 5: Update volatility
    new_sigma = _update_volatility(state.volatility, phi, v, delta)

    # Step 6: Update RD incorporating new volatility
    phi_star = math.sqrt(phi * phi + new_sigma * new_sigma)

    # Step 7: Update rating and RD
    new_phi = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    new_mu = mu + new_phi * new_phi * g_j * (score - e_j)

    new_rating, new_rd = _from_glicko2(new_mu, new_phi)
    return GlickoState(rating=new_rating, rd=new_rd, volatility=new_sigma)


def apply_rd_decay(state: GlickoState, days_inactive: float) -> GlickoState:
    """Increase RD for time since last game (uncertainty grows with inactivity)."""
    if days_inactive <= 0:
        return state
    new_rd = min(math.sqrt(state.rd ** 2 + RD_GROWTH_PER_DAY ** 2 * days_inactive), INITIAL_RD)
    return GlickoState(rating=state.rating, rd=new_rd, volatility=state.volatility, last_updated=state.last_updated)


# ----- Materializer -----

def materialize_map_glicko(matches: list[CsParsedMatch], as_of: datetime) -> list[FeatureValue]:
    """
    Compute per-team-per-map Glicko-2 ratings using all finished matches before as_of.

    Returns a FeatureValue for each team-map entity observed before as_of.
    """
    sorted_matches = sorted(
        (m for m in matches if m.status == "finished" and m.scheduled_at < as_of),
        key=lambda m: (m.scheduled_at, m.hltv_id),
    )

    # Per-team-per-map Glicko state
    states: dict[tuple[str, str], GlickoState] = {}

    for match in sorted_matches:
        team_a_id = cs_participant_id("hltv", match.team_a.hltv_id)
        team_b_id = cs_participant_id("hltv", match.team_b.hltv_id)

        for played_map in match.maps:
            map_name = played_map.map_name
            winner_id = cs_participant_id("hltv", played_map.winner_hltv_id)

            key_a = (team_a_id, map_name)
            key_b = (team_b_id, map_name)

            state_a = states.get(key_a, GlickoState())
            state_b = states.get(key_b, GlickoState())

            # Apply RD decay for time since last update
            if state_a.last_updated is not None:
                days_a = (match.scheduled_at - state_a.last_updated).total_seconds() / 86400
                state_a = apply_rd_decay(state_a, days_a)
            if state_b.last_updated is not None:
                days_b = (match.scheduled_at - state_b.last_updated).total_seconds() / 86400
                state_b = apply_rd_decay(state_b, days_b)

            score_a = 1.0 if winner_id == team_a_id else 0.0
            score_b = 1.0 - score_a

            new_state_a = update_glicko(state_a, state_b.rating, state_b.rd, score_a)
            new_state_b = update_glicko(state_b, state_a.rating, state_a.rd, score_b)

            new_state_a.last_updated = match.scheduled_at
            new_state_b.last_updated = match.scheduled_at

            states[key_a] = new_state_a
            states[key_b] = new_state_b

    features: list[FeatureValue] = []
    for (team_id, map_name), state in sorted(states.items()):
        entity_id = f"{team_id}:map:{map_name}"
        features.append(
            FeatureValue(
                entity_id=entity_id,
                name=FEATURE_NAME,
                as_of=as_of,
                value={
                    "map_name": map_name,
                    "rating": state.rating,
                    "rd": state.rd,
                    "volatility": state.volatility,
                },
            )
        )
    return features
