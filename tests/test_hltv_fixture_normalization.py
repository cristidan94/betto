from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from sports.cs.normalization import normalize_match, parse_hltv_fixture, parse_hltv_payload
from sports.cs.normalization.records import (
    CsParsedEvent,
    CsParsedMap,
    CsParsedMatch,
    CsParsedPlayerMapStats,
    CsParsedTeam,
)


FIXTURE = {
    "hltv_id": "2370001",
    "scheduled_at": "2026-05-20T18:00:00Z",
    "best_of": 3,
    "status": "finished",
    "team_a": {"hltv_id": "4608", "name": "Natus Vincere", "aliases": ["NAVI"]},
    "team_b": {"hltv_id": "9565", "name": "Vitality", "aliases": ["Team Vitality"]},
    "event": {"hltv_id": "8001", "name": "IEM Dallas", "tier": "S"},
    "players": [
        {"hltv_id": "p1", "nickname": "b1t", "team_hltv_id": "4608"},
        {"hltv_id": "p2", "nickname": "ZywOo", "team_hltv_id": "9565"},
    ],
    "maps": [
        {"map_index": 1, "map_name": "de_mirage", "team_a_score": 13, "team_b_score": 9, "winner_hltv_id": "4608"},
        {"map_index": 2, "map_name": "Nuke", "team_a_score": 11, "team_b_score": 13, "winner_hltv_id": "9565"},
    ],
    "vetoes": [
        {"order_idx": 1, "team_hltv_id": "4608", "action": "ban", "map_name": "Vertigo"},
        {"order_idx": 2, "team_hltv_id": "9565", "action": "pick", "map_name": "Nuke"},
    ],
}


RICH_FIXTURE = {
    "hltv_id": "2394722",
    "schema_version": "hltv-fixture-v1",
    "source": {"name": "hltv-scraper", "url": "https://example.com", "stats_url": "https://example.com/stats"},
    "status": "finished",
    "best_of": 3,
    "match_stage": "Round of 16",
    "scheduled_at": "2026-05-29T17:00:00+00:00",
    "event": {"hltv_id": "9171", "name": "Thunderpick World Championship", "tier": 2, "hltv_stars": 0},
    "team_a": {"hltv_id": "13644", "name": "TDK"},
    "team_b": {"hltv_id": "13403", "name": "TNC"},
    "head_to_head": {"team_a_wins": 3, "team_b_wins": 2},
    "players": [
        {"hltv_id": "16555", "nickname": "Ax1Le", "team_hltv_id": "13644"},
        {"hltv_id": "20312", "nickname": "deko", "team_hltv_id": "13403"},
    ],
    "vetoes": [
        {"order_idx": 1, "action": "ban", "map_name": "Nuke", "team_hltv_id": "13644"},
        {"order_idx": 2, "action": "pick", "map_name": "Dust2", "team_hltv_id": "13403"},
        {"order_idx": 3, "action": "decider", "map_name": "Mirage", "team_hltv_id": None},
    ],
    "maps": [
        {
            "map_index": 1,
            "map_name": "Dust2",
            "map_stats_id": "230451",
            "overtime": False,
            "winner_hltv_id": "13644",
            "team_a_score": 13,
            "team_a_first_half": 7,
            "team_a_second_half": 6,
            "team_b_score": 6,
            "team_b_first_half": 5,
            "team_b_second_half": 1,
            "player_stats": {
                "ax1le": {
                    "kills": 19,
                    "deaths": 10,
                    "adr": 94.6,
                    "rating": 1.77,
                    "kast_pct": 84.2,
                    "ct_kills": 9,
                    "ct_deaths": 3,
                    "t_kills": 10,
                    "t_deaths": 7,
                    "assists": None,
                    "headshot_pct": None,
                    "first_kills": None,
                    "first_deaths": None,
                    "clutches_won": None,
                    "flash_assists": None,
                    "trade_deaths": None,
                },
                "deko": {
                    "kills": 8,
                    "deaths": 15,
                    "adr": 55.3,
                    "rating": 0.72,
                    "kast_pct": 63.2,
                    "ct_kills": 4,
                    "ct_deaths": 8,
                    "t_kills": 4,
                    "t_deaths": 7,
                    "assists": 3,
                    "headshot_pct": 50.0,
                    "first_kills": 1,
                    "first_deaths": 2,
                    "clutches_won": 0,
                    "flash_assists": 2,
                    "trade_deaths": 1,
                },
            },
        }
    ],
}


class HltvFixtureNormalizationTests(unittest.TestCase):
    def test_parse_hltv_payload_normalizes_maps(self) -> None:
        parsed = parse_hltv_payload(FIXTURE)

        self.assertEqual(parsed.hltv_id, "2370001")
        self.assertEqual(parsed.maps[0].map_name, "Mirage")
        self.assertEqual(parsed.vetoes[1].map_name, "Nuke")

    def test_parse_hltv_fixture_reads_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "match.json"
            path.write_text(json.dumps(FIXTURE), encoding="utf-8")

            parsed = parse_hltv_fixture(path)

            self.assertEqual(parsed.event.name, "IEM Dallas")

    def test_normalize_match_outputs_core_entities(self) -> None:
        normalized = normalize_match(parse_hltv_payload(FIXTURE))

        participants = normalized["participants"]
        self.assertEqual(len(participants), 4)  # type: ignore[arg-type]
        self.assertEqual(normalized["competition"].name, "IEM Dallas")  # type: ignore[union-attr]
        self.assertEqual(normalized["contest"].format, "bo3")  # type: ignore[union-attr]
        self.assertEqual(len(normalized["contest_units"]), 2)  # type: ignore[arg-type]


class RecordDefaultsTests(unittest.TestCase):
    def test_parsed_map_has_rich_fields_with_defaults(self) -> None:
        basic = CsParsedMap(1, "Mirage", 13, 9, "4608")
        self.assertIsNone(basic.map_stats_id)
        self.assertIsNone(basic.overtime)
        self.assertIsNone(basic.team_a_first_half)
        self.assertIsNone(basic.team_b_first_half)
        self.assertEqual(basic.player_stats, ())

    def test_parsed_map_accepts_rich_fields(self) -> None:
        rich = CsParsedMap(
            map_index=1,
            map_name="Dust2",
            team_a_score=13,
            team_b_score=6,
            winner_hltv_id="13644",
            map_stats_id="230451",
            overtime=False,
            team_a_first_half=7,
            team_a_second_half=6,
            team_b_first_half=5,
            team_b_second_half=1,
            player_stats=(
                CsParsedPlayerMapStats(player_hltv_id="16555", team_hltv_id="13644", kills=19, deaths=10),
            ),
        )
        self.assertEqual(rich.map_stats_id, "230451")
        self.assertFalse(rich.overtime)
        self.assertEqual(rich.team_a_first_half, 7)
        self.assertEqual(rich.team_b_second_half, 1)
        self.assertEqual(len(rich.player_stats), 1)
        self.assertEqual(rich.player_stats[0].kills, 19)
        self.assertIsNone(rich.player_stats[0].assists)

    def test_parsed_match_has_rich_fields_with_defaults(self) -> None:
        match = CsParsedMatch(
            hltv_id="1",
            scheduled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            best_of=1,
            status="finished",
            team_a=CsParsedTeam("1", "A"),
            team_b=CsParsedTeam("2", "B"),
            event=CsParsedEvent("1", "Test"),
            players=(),
            maps=(),
            vetoes=(),
        )
        self.assertIsNone(match.match_stage)
        self.assertIsNone(match.head_to_head)

    def test_parsed_player_map_stats_all_nullable(self) -> None:
        stats = CsParsedPlayerMapStats(player_hltv_id="16555", team_hltv_id="13644")
        self.assertIsNone(stats.kills)
        self.assertIsNone(stats.ct_kills)
        self.assertIsNone(stats.flash_assists)
        self.assertIsNone(stats.trade_deaths)


class RichParserTests(unittest.TestCase):
    def test_parse_extracts_match_stage_and_head_to_head(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        self.assertEqual(parsed.match_stage, "Round of 16")
        self.assertEqual(parsed.head_to_head, {"team_a_wins": 3, "team_b_wins": 2})

    def test_parse_extracts_map_rich_fields(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        parsed_map = parsed.maps[0]
        self.assertEqual(parsed_map.map_stats_id, "230451")
        self.assertFalse(parsed_map.overtime)
        self.assertEqual(parsed_map.team_a_first_half, 7)
        self.assertEqual(parsed_map.team_a_second_half, 6)
        self.assertEqual(parsed_map.team_b_first_half, 5)
        self.assertEqual(parsed_map.team_b_second_half, 1)

    def test_parse_extracts_player_stats_with_id_resolution(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        stats = parsed.maps[0].player_stats
        self.assertEqual(len(stats), 2)
        ax1le = next(item for item in stats if item.player_hltv_id == "16555")
        self.assertEqual(ax1le.team_hltv_id, "13644")
        self.assertEqual(ax1le.kills, 19)
        self.assertEqual(ax1le.ct_kills, 9)
        self.assertIsNone(ax1le.assists)
        deko = next(item for item in stats if item.player_hltv_id == "20312")
        self.assertEqual(deko.assists, 3)
        self.assertEqual(deko.first_deaths, 2)
        self.assertEqual(deko.flash_assists, 2)
        self.assertEqual(deko.trade_deaths, 1)

    def test_parse_handles_missing_player_stats(self) -> None:
        fixture = {
            **RICH_FIXTURE,
            "maps": [
                {
                    "map_index": 1,
                    "map_name": "Dust2",
                    "team_a_score": 13,
                    "team_b_score": 6,
                    "winner_hltv_id": "13644",
                }
            ],
        }
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(parsed.maps[0].player_stats, ())
        self.assertIsNone(parsed.maps[0].map_stats_id)

    def test_parse_skips_unresolvable_player_stats(self) -> None:
        fixture = {
            **RICH_FIXTURE,
            "maps": [
                {
                    **RICH_FIXTURE["maps"][0],
                    "player_stats": {"unknown_player": {"kills": 5, "deaths": 3}},
                }
            ],
        }
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(len(parsed.maps[0].player_stats), 0)

    def test_parse_skips_malformed_player_stats_entry(self) -> None:
        fixture = {
            **RICH_FIXTURE,
            "maps": [
                {
                    **RICH_FIXTURE["maps"][0],
                    "player_stats": {"ax1le": None},
                }
            ],
        }
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(parsed.maps[0].player_stats, ())

    def test_parse_skips_malformed_player_stats_container(self) -> None:
        fixture = {
            **RICH_FIXTURE,
            "maps": [
                {
                    **RICH_FIXTURE["maps"][0],
                    "player_stats": ["ax1le"],
                }
            ],
        }
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(parsed.maps[0].player_stats, ())

    def test_parse_ignores_malformed_head_to_head(self) -> None:
        fixture = {**RICH_FIXTURE, "head_to_head": "3-2"}
        parsed = parse_hltv_payload(fixture)
        self.assertIsNone(parsed.head_to_head)

    def test_parse_coerces_head_to_head_counts_to_ints(self) -> None:
        fixture = {**RICH_FIXTURE, "head_to_head": {"team_a_wins": "3", "team_b_wins": "2"}}
        parsed = parse_hltv_payload(fixture)
        self.assertEqual(parsed.head_to_head, {"team_a_wins": 3, "team_b_wins": 2})

    def test_parse_ignores_head_to_head_with_bad_count(self) -> None:
        fixture = {**RICH_FIXTURE, "head_to_head": {"team_a_wins": "three", "team_b_wins": 2}}
        parsed = parse_hltv_payload(fixture)
        self.assertIsNone(parsed.head_to_head)

    def test_null_veto_team_hltv_id_for_decider(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        decider = parsed.vetoes[2]
        self.assertIsNone(decider.team_hltv_id)
        self.assertEqual(decider.action, "decider")

    def test_plain_fixture_still_works(self) -> None:
        parsed = parse_hltv_payload(FIXTURE)
        self.assertIsNone(parsed.match_stage)
        self.assertIsNone(parsed.head_to_head)
        self.assertEqual(parsed.maps[0].player_stats, ())


class NormalizeRichMatchTests(unittest.TestCase):
    def test_normalize_passes_match_stage_and_head_to_head(self) -> None:
        normalized = normalize_match(parse_hltv_payload(RICH_FIXTURE))
        contest = normalized["contest"]
        self.assertEqual(contest.match_stage, "Round of 16")
        self.assertEqual(contest.head_to_head, {"team_a_wins": 3, "team_b_wins": 2})

    def test_normalize_plain_fixture_has_none_for_rich_fields(self) -> None:
        normalized = normalize_match(parse_hltv_payload(FIXTURE))
        contest = normalized["contest"]
        self.assertIsNone(contest.match_stage)
        self.assertIsNone(contest.head_to_head)


class FullPipelineIntegrationTests(unittest.TestCase):
    def test_rich_fixture_produces_all_record_types(self) -> None:
        parsed = parse_hltv_payload(RICH_FIXTURE)
        normalized = normalize_match(parsed)

        self.assertEqual(len(normalized["participants"]), 4)
        self.assertIsNotNone(normalized["competition"])
        self.assertEqual(normalized["contest"].match_stage, "Round of 16")
        self.assertEqual(normalized["contest"].head_to_head, {"team_a_wins": 3, "team_b_wins": 2})
        self.assertEqual(len(normalized["contest_units"]), 1)
        self.assertEqual(len(normalized["cs_maps"]), 1)
        self.assertEqual(len(normalized["cs_vetoes"]), 3)

        parsed_map = normalized["cs_maps"][0]
        self.assertEqual(parsed_map.map_stats_id, "230451")
        self.assertEqual(len(parsed_map.player_stats), 2)
        ax1le = next(item for item in parsed_map.player_stats if item.player_hltv_id == "16555")
        self.assertEqual(ax1le.kills, 19)
        self.assertEqual(ax1le.ct_kills, 9)

    def test_fixture_without_stats_still_normalizes(self) -> None:
        no_stats = {
            **RICH_FIXTURE,
            "maps": [
                {
                    "map_index": 1,
                    "map_name": "Dust2",
                    "team_a_score": 13,
                    "team_b_score": 6,
                    "winner_hltv_id": "13644",
                }
            ],
        }
        no_stats_copy = {**no_stats}
        del no_stats_copy["match_stage"]
        del no_stats_copy["head_to_head"]
        parsed = parse_hltv_payload(no_stats_copy)
        normalized = normalize_match(parsed)
        self.assertEqual(len(normalized["cs_maps"]), 1)
        self.assertEqual(normalized["cs_maps"][0].player_stats, ())
        self.assertIsNone(normalized["contest"].match_stage)


if __name__ == "__main__":
    unittest.main()
