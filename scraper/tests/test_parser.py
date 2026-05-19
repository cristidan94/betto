from __future__ import annotations

import unittest
from pathlib import Path

from scraper.parser import parse_map_stats_page, parse_match_page, parse_results_page, parse_stats_page


RESULTS_HTML = """
<html><body>
  <div class="event-name" data-stars="5">IEM Cologne</div>
  <a class="a-reset" href="/matches/2371234/navi-vs-faze">NAVI vs FaZe</a>
  <a class="a-reset" href="/matches/2371234/navi-vs-faze">Duplicate</a>
</body></html>
"""


MATCH_HTML = """
<html><body>
  <div data-unix="1772539200000"></div>
  <a href="/team/4608/navi">NAVI</a>
  <a href="/team/6667/faze">FaZe</a>
  <a href="/events/7148/iem-katowice">IEM Katowice</a>
  <a href="/player/7998/s1mple">s1mple</a>
  <a href="/player/7592/bit">b1t</a>
  <a href="/player/18053/broky">broky</a>
  <a href="/stats/matches/111111/vitality-vs-bcgame">Past stats</a>
  <a href="/stats/matches/112345/navi-vs-faze">Stats</a>
  <div>Best of 3</div>
  <div>NAVI removed Dust2. FaZe picked Nuke.</div>
  <div>Inferno 13 - 9 <a href="/stats/matches/mapstatsid/98765/slug">map stats</a></div>
</body></html>
"""


STATS_HTML = """
<table>
  <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>25</td></tr>
  <tr><td><a href="/player/18053/broky">broky</a></td><td>20</td></tr>
</table>
"""


class ParserTests(unittest.TestCase):
    def test_parse_results_page_deduplicates_matches(self) -> None:
        entries = parse_results_page(RESULTS_HTML)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["match_id"], "2371234")
        self.assertIn("/matches/2371234", entries[0]["match_url"])

    def test_parse_match_page_extracts_core_fields(self) -> None:
        match = parse_match_page(MATCH_HTML, "2371234")

        self.assertEqual(match["team_a"]["hltv_id"], "4608")
        self.assertEqual(match["team_b"]["name"], "FaZe")
        self.assertEqual(match["event"]["hltv_id"], "7148")
        self.assertEqual(match["best_of"], 3)
        self.assertEqual(match["maps"][0]["winner_hltv_id"], "4608")
        self.assertEqual(match["maps"][0]["map_stats_id"], "98765")
        self.assertEqual(match["stats_url"], "https://www.hltv.org/stats/matches/112345/navi-vs-faze")
        self.assertGreaterEqual(len(match["players"]), 3)
        self.assertGreaterEqual(len(match["vetoes"]), 1)

    def test_parse_match_page_ignores_unrelated_stats_links(self) -> None:
        html = """
        <html><body>
          <a href="/team/11283/falcons">Falcons</a>
          <a href="/team/13382/bcgame">BC.Game</a>
          <a href="/stats/matches/126812/vitality-vs-bcgame">Past stats</a>
          <div>Best of 3</div>
        </body></html>
        """
        match = parse_match_page(html, "2394201")

        self.assertIsNone(match["stats_url"])

    def test_parse_stats_pages(self) -> None:
        stats = parse_stats_page(STATS_HTML)
        map_stats = parse_map_stats_page(STATS_HTML)

        self.assertEqual(stats["players"][0]["hltv_id"], "7998")
        self.assertEqual(map_stats[0]["nickname"], "s1mple")
        self.assertEqual(map_stats[0]["cells"][1], "25")

    def test_parse_live_fixture_extracts_match_sidebar_event_and_lineups(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "match_2394349.html"
        if not fixture.exists():
            self.skipTest("live fixture not present")

        match = parse_match_page(fixture.read_text(encoding="utf-8"), "2394349")

        self.assertEqual(match["event"]["hltv_id"], "9180")
        self.assertEqual(match["event"]["name"], "CCT 2026 South America Series 2")
        self.assertEqual(len(match["players"]), 10)
        self.assertEqual(match["players"][0]["nickname"], "trindade")
        self.assertEqual(match["players"][5]["nickname"], "coxa")
        self.assertEqual(match["vetoes"][0]["map_name"], "Anubis")

    def test_parse_live_results_fixture_uses_link_title_for_event(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "results_page.html"
        if not fixture.exists():
            self.skipTest("live fixture not present")

        entries = parse_results_page(fixture.read_text(encoding="utf-8"))

        self.assertGreaterEqual(len(entries), 1)
        self.assertEqual(entries[0]["match_id"], "2394349")
        self.assertEqual(entries[0]["event_name"], "CCT 2026 South America Series 2")


if __name__ == "__main__":
    unittest.main()
