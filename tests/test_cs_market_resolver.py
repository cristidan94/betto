from __future__ import annotations

import unittest
from datetime import datetime, timezone

from sports.cs.markets import ContestCandidate, resolve_market


def candidate(
    contest_id: str,
    team_a_names: tuple[str, ...],
    team_b_names: tuple[str, ...],
) -> ContestCandidate:
    return ContestCandidate(
        contest_id=contest_id,
        starts_at=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
        team_a_names=team_a_names,
        team_b_names=team_b_names,
        event_names=("IEM Dallas",),
    )


class CsMarketResolverTests(unittest.TestCase):
    def test_exact_match_links_market(self) -> None:
        result = resolve_market(
            "Will Natus Vincere beat Vitality at IEM Dallas?",
            [candidate("contest-1", ("Natus Vincere", "NAVI"), ("Vitality", "Team Vitality"))],
            outcomes=("NAVI", "Vitality"),
            starts_at_hint=datetime(2026, 5, 20, 19, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(result.contest_id, "contest-1")
        self.assertFalse(result.manual_review)
        self.assertEqual(result.outcome_mapping, {"NAVI": "team_a", "Vitality": "team_b"})

    def test_alias_match_links_market(self) -> None:
        result = resolve_market(
            "Counter-Strike 2: NAVI vs G2 winner",
            [candidate("contest-1", ("Natus Vincere", "NAVI"), ("G2 Esports", "G2"))],
            outcomes=("Natus Vincere", "G2 Esports"),
        )

        self.assertEqual(result.contest_id, "contest-1")
        self.assertEqual(result.reason, "linked")

    def test_ambiguous_match_requires_manual_review(self) -> None:
        result = resolve_market(
            "Will NAVI beat Vitality?",
            [
                candidate("contest-1", ("NAVI",), ("Vitality",)),
                candidate("contest-2", ("NAVI",), ("Vitality",)),
            ],
            outcomes=("NAVI", "Vitality"),
        )

        self.assertIsNone(result.contest_id)
        self.assertTrue(result.manual_review)
        self.assertEqual(result.reason, "ambiguous_match")

    def test_no_match_requires_manual_review(self) -> None:
        result = resolve_market(
            "Will FaZe beat MOUZ?",
            [candidate("contest-1", ("NAVI",), ("Vitality",))],
            outcomes=("FaZe", "MOUZ"),
        )

        self.assertIsNone(result.contest_id)
        self.assertTrue(result.manual_review)
        self.assertEqual(result.reason, "no_match")


if __name__ == "__main__":
    unittest.main()

