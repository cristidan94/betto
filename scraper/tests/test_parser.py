from __future__ import annotations

import unittest
from pathlib import Path

from scraper.parser import (
    _resolve_best_of,
    _results_floor,
    parse_map_stats_page,
    parse_match_page,
    parse_results_page,
    parse_stats_page,
)


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


MATCH_WITH_EMBEDDED_STATS_HTML = """
<html><body>
  <div data-unix="1772539200000"></div>
  <a href="/team/4608/navi">NAVI</a>
  <a href="/team/6667/faze">FaZe</a>
  <a href="/events/7148/iem-katowice">IEM Katowice</a>
  <div>Best of 1</div>
  <div class="mapholder">
    <div class="mapname">Inferno</div>
    <div class="results-left won"><div class="results-team-score">13</div></div>
    <div class="results-right"><div class="results-team-score">9</div></div>
    <div class="results-center-half-score">( 7 : 5 ; 6 : 4 )</div>
    <a href="/stats/matches/mapstatsid/98765/navi-vs-faze">map stats</a>
  </div>
  <div id="matchstats" class="match-stats matchstats">
    <div id="98765-content" class="stats-content">
      <table class="table totalstats">
        <tr><th><a href="/team/4608/navi">NAVI</a></th><td>K-D</td><td>ADR</td><td>KAST</td><td>Rating 3.0</td></tr>
        <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>25-15</td><td>92.1</td><td>78.0%</td><td>1.40</td></tr>
      </table>
      <table class="table ctstats hidden">
        <tr><th><a href="/team/4608/navi">NAVI</a></th><td>K-D</td><td>ADR</td><td>KAST</td><td>Rating 3.0</td></tr>
        <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>15-7</td><td>110.0</td><td>85.0%</td><td>1.70</td></tr>
      </table>
      <table class="table tstats hidden">
        <tr><th><a href="/team/4608/navi">NAVI</a></th><td>K-D</td><td>ADR</td><td>KAST</td><td>Rating 3.0</td></tr>
        <tr><td><a href="/player/7998/s1mple">s1mple</a></td><td>10-8</td><td>74.2</td><td>71.0%</td><td>1.10</td></tr>
      </table>
    </div>
  </div>
</body></html>
"""


class ParserTests(unittest.TestCase):
    def test_parse_match_page_extracts_embedded_map_player_stats_with_sides(self) -> None:
        match = parse_match_page(MATCH_WITH_EMBEDDED_STATS_HTML, "2400001")
        self.assertEqual(match["status"], "finished")
        self.assertEqual(len(match["maps"]), 1)
        m = match["maps"][0]
        self.assertEqual(m["map_name"], "Inferno")
        self.assertEqual((m["team_a_score"], m["team_b_score"]), (13, 9))
        self.assertEqual(m["map_stats_id"], "98765")
        self.assertEqual((m["team_a_first_half"], m["team_b_first_half"]), (7, 5))
        stats = {row["player_hltv_id"]: row for row in m["player_stats"]}
        s1mple = stats["7998"]
        self.assertEqual((s1mple["kills"], s1mple["deaths"]), (25, 15))
        self.assertEqual(s1mple["adr"], 92.1)
        self.assertEqual(s1mple["kast_pct"], 78.0)
        self.assertEqual(s1mple["rating"], 1.40)
        # CT/T side splits merged from the hidden per-side tables.
        self.assertEqual((s1mple["ct_kills"], s1mple["ct_deaths"]), (15, 7))
        self.assertEqual((s1mple["t_kills"], s1mple["t_deaths"]), (10, 8))
        # Players list derived from the scoreboard, not every /player/ link.
        self.assertEqual([p["hltv_id"] for p in match["players"]], ["7998"])

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

    def test_best_of_inferred_from_results_when_text_missing(self) -> None:
        sweep = [
            {"team_a_score": 13, "team_b_score": 7},
            {"team_a_score": 13, "team_b_score": 9},
        ]
        # No "Best of N" text on the page: a 2-0 sweep proves at least a Bo3
        # (the old odd-map-count heuristic wrongly returned 1 for 2 maps).
        self.assertEqual(_resolve_best_of("Group A decider", sweep), 3)
        # A 3-1 series proves at least a Bo5.
        bo5 = sweep + [{"team_a_score": 7, "team_b_score": 13}, {"team_a_score": 13, "team_b_score": 4}]
        self.assertEqual(_resolve_best_of("", bo5), 5)
        # An explicit "Best of N" is trusted but never lowered below the floor.
        self.assertEqual(_resolve_best_of("Best of 1", sweep), 3)
        # Single-map forfeit: results floor is 1, so an explicit Bo3 is kept.
        forfeit = [{"team_a_score": 13, "team_b_score": 5}]
        self.assertEqual(_resolve_best_of("Best of 3", forfeit), 3)
        # No maps and no text (unplayed) falls back to the odd-count heuristic.
        self.assertEqual(_resolve_best_of("upcoming", []), 1)
        # Tied maps contribute no wins, so they don't inflate the floor.
        self.assertEqual(_results_floor([{"team_a_score": 13, "team_b_score": 13}]), 0)

    def test_parse_match_page_parses_numbered_veto_box(self) -> None:
        html = """
        <html><body>
          <a href="/team/5973/liquid">Liquid</a>
          <a href="/team/10831/entropiq">Entropiq</a>
          <div class="standard-box veto-box"><div class="padding">* Group D</div></div>
          <div class="standard-box veto-box"><div class="padding">
            <div>1. Entropiq removed Inferno</div>
            <div>2. Liquid removed Ancient</div>
            <div>3. Entropiq picked Vertigo</div>
            <div>4. Liquid picked Overpass</div>
            <div>5. Entropiq removed Nuke</div>
            <div>6. Liquid removed Dust2</div>
            <div>7. Mirage was left over</div>
          </div></div>
        </body></html>
        """
        vetoes = parse_match_page(html, "2350370")["vetoes"]

        # Exactly the 7 numbered steps, no stray/duplicate entries from a page scan.
        self.assertEqual([v["order_idx"] for v in vetoes], [1, 2, 3, 4, 5, 6, 7])
        self.assertEqual(vetoes[0], {"order_idx": 1, "team_hltv_id": "10831", "action": "ban", "map_name": "Inferno"})
        self.assertEqual(vetoes[2], {"order_idx": 3, "team_hltv_id": "10831", "action": "pick", "map_name": "Vertigo"})
        # Map names are canonicalized and the leftover map is the decider with no team.
        self.assertEqual(vetoes[6], {"order_idx": 7, "team_hltv_id": None, "action": "decider", "map_name": "Mirage"})

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
        self.assertIn("match_id", entries[0])
        self.assertIn("event_name", entries[0])
        self.assertTrue(entries[0]["match_id"].isdigit())
        self.assertGreater(len(entries[0]["event_name"]), 0)
        # Event names come from the .event-name node, not a scooped sidebar blob.
        self.assertLessEqual(len(entries[0]["event_name"]), 80)
        # scheduled_at is read from data-zonedgrouping-entry-unix on .result-con;
        # the live results page has no data-unix descendants, so this regresses
        # to None if that selector breaks.
        dated = [e for e in entries if e.get("scheduled_at")]
        self.assertGreater(len(dated), 0)
        self.assertTrue(dated[0]["scheduled_at"].startswith("20"))

    def test_parse_results_page_reads_zonedgrouping_date_and_rejects_junk(self) -> None:
        # The live results page nests the match link inside a .result-con that
        # carries the timestamp as data-zonedgrouping-entry-unix (ms) and the
        # event in a .event-name child — there are no [data-unix] descendants.
        html = """
        <html><body>
          <div class="results-sublist">
            <div class="result-con" data-zonedgrouping-entry-unix="1780166912000">
              <a class="a-reset" href="/matches/2394322/magic-vs-nip">
                <div class="event"><span class="event-name">Stake Ranked Episode 2</span></div>
              </a>
            </div>
          </div>
          <div class="newsline">FaZe vs NAVI 177 Infographic plus a very long
            concatenated sidebar headline blob that runs well past eighty chars
            <a class="a-reset" href="/matches/2399999/foo-vs-bar">match</a>
          </div>
        </body></html>
        """
        by_id = {e["match_id"]: e for e in parse_results_page(html)}

        good = by_id["2394322"]
        self.assertEqual(good["event_name"], "Stake Ranked Episode 2")
        self.assertEqual(good["scheduled_at"], "2026-05-30T18:48:32+00:00")

        # A link outside a clean .result-con must not absorb sidebar text as the
        # event name (the old _nearby_event blob bug).
        self.assertIsNone(by_id["2399999"]["event_name"])


if __name__ == "__main__":
    unittest.main()
