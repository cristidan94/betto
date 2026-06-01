from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scraper import enrich
from scraper.config import ScraperConfig
from scraper.parser import parse_stats_map_detailed


STATS_DETAILED_HTML = """
<html><body>
<table class="stats-table totalstats">
  <tr>
    <th><a href="/team/4608/navi">magic</a></th>
    <td>Op. K-D</td><td>Op. eK-eD</td><td>MKs</td><td>KAST</td><td>eKAST</td>
    <td>1vsX</td><td>K (hs)</td><td>eK (hs)</td><td>A (f)</td><td>D (t)</td><td>eD (t)</td>
    <td>ADR</td><td>eADR</td><td>KAST</td><td>eKAST</td><td>Swing</td><td>Rating 3.0</td>
  </tr>
  <tr>
    <td>tenzy</td>
    <td>2 : 4</td><td>2 : 4</td><td>5</td><td>79.2%</td><td>84.2%</td>
    <td>0</td><td>20 (13)</td><td>20 (13)</td><td>8 (1)</td><td>18 (6)</td><td>19 (7)</td>
    <td>96.9</td><td>94.4</td><td>79.2%</td><td>84.2%</td><td>+3.59%</td><td>1.36</td>
  </tr>
</table>
</body></html>
"""


class StatsDetailedParserTests(unittest.TestCase):
    def test_parse_detailed_columns(self) -> None:
        rows = parse_stats_map_detailed(STATS_DETAILED_HTML)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["nickname"], "tenzy")
        self.assertEqual((r["first_kills"], r["first_deaths"]), (2, 4))
        self.assertEqual(r["multi_kills"], 5)
        self.assertEqual(r["clutches_won"], 0)
        self.assertEqual((r["kills"], r["hs_kills"]), (20, 13))
        self.assertEqual((r["assists"], r["flash_assists"]), (8, 1))
        self.assertEqual((r["deaths"], r["trade_deaths"]), (18, 6))
        self.assertEqual(r["adr"], 96.9)
        self.assertEqual(r["kast_pct"], 79.2)
        self.assertEqual(r["rating"], 1.36)
        self.assertEqual(r["headshot_pct"], 65.0)


class EnrichMergeTests(unittest.TestCase):
    def _fixture(self) -> dict:
        return {
            "hltv_id": "1",
            "status": "finished",
            "event": {"tier": 1},
            "team_a": {"name": "magic"},
            "team_b": {"name": "FaZe"},
            "maps": [
                {
                    "map_stats_id": "230557",
                    "player_stats": {
                        "tenzy": {"kills": 20, "deaths": 18, "adr": 96.9, "rating": 1.36, "first_kills": None},
                    },
                }
            ],
        }

    def test_enrich_merges_detail_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "1.json").write_text(json.dumps(self._fixture()), encoding="utf-8")
            config = ScraperConfig(
                output_dir=out,
                unblocker_proxy="https://unblock.example:60000",
                unblocker_user="u",
                unblocker_pass="p",
            )
            # Stub the network: return our sample /stats/ HTML.
            orig = enrich.fetch_via_unblocker
            enrich.fetch_via_unblocker = lambda url, cfg, **kw: (True, STATS_DETAILED_HTML)
            try:
                result = enrich.enrich_stats(config, max_tier=1, limit=10, min_delay=0)
            finally:
                enrich.fetch_via_unblocker = orig

            self.assertEqual(result["enriched_maps"], 1)
            self.assertEqual(result["enriched_matches"], 1)
            payload = json.loads((out / "1.json").read_text())
            tenzy = payload["maps"][0]["player_stats"]["tenzy"]
            self.assertEqual(tenzy["first_kills"], 2)
            self.assertEqual(tenzy["hs_kills"], 13)
            self.assertEqual(tenzy["multi_kills"], 5)
            self.assertEqual(tenzy["flash_assists"], 1)
            self.assertEqual(tenzy["trade_deaths"], 6)

    def test_enrich_no_unblocker_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = ScraperConfig(output_dir=Path(tmp))
            result = enrich.enrich_stats(config, max_tier=1, limit=10)
            self.assertEqual(result.get("error"), "unblocker_not_configured")


if __name__ == "__main__":
    unittest.main()
