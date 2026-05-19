from __future__ import annotations


def best_of_series_probability(map_win_probs: list[float]) -> float:
    """Compute P(team A wins a fixed-map-order best-of series."""

    if not map_win_probs:
        raise ValueError("map_win_probs cannot be empty")
    best_of = len(map_win_probs)
    needed = best_of // 2 + 1
    states: dict[tuple[int, int], float] = {(0, 0): 1.0}
    for probability in map_win_probs:
        if not 0 <= probability <= 1:
            raise ValueError("map probabilities must be between 0 and 1")
        next_states: dict[tuple[int, int], float] = {}
        for (wins_a, wins_b), state_prob in states.items():
            if wins_a >= needed or wins_b >= needed:
                next_states[(wins_a, wins_b)] = next_states.get((wins_a, wins_b), 0.0) + state_prob
                continue
            next_states[(wins_a + 1, wins_b)] = next_states.get((wins_a + 1, wins_b), 0.0) + state_prob * probability
            next_states[(wins_a, wins_b + 1)] = next_states.get((wins_a, wins_b + 1), 0.0) + state_prob * (1 - probability)
        states = next_states
    return sum(state_prob for (wins_a, _), state_prob in states.items() if wins_a >= needed)

