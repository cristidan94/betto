from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sports.cs.normalization import normalize_match, parse_hltv_fixture, parse_hltv_payload


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


if __name__ == "__main__":
    unittest.main()

