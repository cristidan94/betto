from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.entities import Contest, Participant, ParticipantKind
from sports.cs.normalization.polymarket_linker import extract_team_names, link_market_to_contest


class ExtractTeamNamesTests(unittest.TestCase):
    def test_will_x_beat_y(self) -> None:
        result = extract_team_names("Will NAVI beat Vitality in Counter-Strike 2?")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "NAVI")
        self.assertEqual(result[1], "Vitality")

    def test_will_x_win_map_vs_y(self) -> None:
        result = extract_team_names("Will G2 win map 1 vs FaZe?")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "G2")
        self.assertEqual(result[1], "FaZe")

    def test_x_vs_y_simple(self) -> None:
        result = extract_team_names("NAVI vs Vitality?")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result[0], "NAVI")
        self.assertEqual(result[1], "Vitality")

    def test_no_teams_found(self) -> None:
        result = extract_team_names("Will it rain tomorrow?")
        self.assertIsNone(result)


class LinkMarketToContestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.navi = Participant("cs:participant:hltv:navi", "cs2", ParticipantKind.TEAM, "Natus Vincere", "hltv", "4608")
        self.vitality = Participant("cs:participant:hltv:vitality", "cs2", ParticipantKind.TEAM, "Team Vitality", "hltv", "9565")
        self.g2 = Participant("cs:participant:hltv:g2", "cs2", ParticipantKind.TEAM, "G2 Esports", "hltv", "9565")
        self.participants = [self.navi, self.vitality, self.g2]

        self.contest = Contest(
            contest_id="cs:contest:hltv:2370001",
            game_id="cs2",
            competition_id="comp-1",
            starts_at=datetime(2026, 5, 20, 18, 0, tzinfo=timezone.utc),
            participant_a_id="cs:participant:hltv:navi",
            participant_b_id="cs:participant:hltv:vitality",
            format="best_of_3",
            status="scheduled",
        )

    def test_links_navi_vs_vitality(self) -> None:
        result = link_market_to_contest(
            "Will NAVI beat Vitality in Counter-Strike 2?",
            self.participants,
            [self.contest],
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.contest_id, "cs:contest:hltv:2370001")
        self.assertGreaterEqual(result.confidence, 0.8)

    def test_higher_confidence_when_date_matches(self) -> None:
        result = link_market_to_contest(
            "Will NAVI beat Vitality in Counter-Strike 2?",
            self.participants,
            [self.contest],
            market_end_date=datetime(2026, 5, 20, 22, 0, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.confidence, 0.95)

    def test_no_match_when_teams_unknown(self) -> None:
        result = link_market_to_contest(
            "Will TeamX beat TeamY?",
            self.participants,
            [self.contest],
        )
        self.assertIsNone(result)

    def test_no_match_when_no_contest(self) -> None:
        result = link_market_to_contest(
            "Will NAVI beat Vitality?",
            self.participants,
            [],
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
