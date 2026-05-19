# Counter-Strike Dataset Sources

Last updated: 2026-05-18.

HLTV does not publish a public API. Betto should treat direct HLTV scraping as a last resort and prefer downloaded, licensed, or partner-provided datasets for historical backfill.

## Tier 1 — High Priority for Betto

1. **Kaggle: CS2 Professional HLTV Rolling Stats (Time Series)**
   - URL: https://www.kaggle.com/datasets/griffindesroches/cs2-professional-hltv-match-data-time-series
   - License: CC0
   - Shape: CS2 match data with pre-computed rolling/time-series team and player statistics.
   - Betto fit: **point-in-time features** — critical for training without leakage. Best available source for model-ready time-series features.
   - Status: download needed. Place in `data/downloads/`.

2. **Kaggle: CS:GO Professional Matches**
   - URL: https://www.kaggle.com/datasets/mateusdmachado/csgo-professional-matches
   - License: validate before commercial use.
   - Shape: 25K+ matches (Nov 2015 - Mar 2020). Four CSV files: `results.csv` (map scores, team rankings), `picks.csv` (map vetoes), `economy.csv` (round-level equipment values), `players.csv` (per-player per-map CT/T side ratings).
   - Betto support: `convert-cs-kaggle-pro-matches` converts results.csv with optional picks/players join.
   - Betto fit: richest legacy dataset — round economy data enables CT/T side features, player ratings enable per-player form features.
   - Status: download needed. Place in `data/downloads/csgo_pro_matches/`.

3. **Kaggle: Counter Strike Competitive Data**
   - URL: https://www.kaggle.com/datasets/filipechavesdemacedo/counter-strike-competitive-data
   - License: CC BY 4.0
   - Shape: historical CS:GO match results, player match scores, and player stat files with partial HLTV links and IDs.
   - Betto support: `convert-cs-kaggle-competitive-results` converts `match_results.csv` into fixture-shaped JSON with map-level winners, and can optionally join `match_players.csv`.
   - Betto fit: good candidate for deeper historical map/player backfill because it exposes match IDs, team IDs, player IDs, and match links.
   - Status: download needed. Place in `data/downloads/`.

4. **OddsPapi Historical Odds API**
   - URL: https://oddspapi.io
   - License: free tier, no credit card required.
   - Shape: historical odds from 350+ bookmakers including Pinnacle closing lines for CS2 (sport ID 17). Timestamped price movements for match winner (market 171), map winners (173/175/177), handicaps, and correct score.
   - Betto support: `OddsPapiClient` in `sports/cs/ingestion/oddspapi.py`, batch fetch script at `scripts/fetch_oddspapi_cs2.py`, CLI `convert-oddspapi-cs2`.
   - Betto fit: **only free source of historical sharp closing lines** for CLV backtesting and edge validation.
   - Status: register free API key at oddspapi.io, set `BETTO_ODDSPAPI_API_KEY`.

5. **Kaggle: HLTV MATCH RESULTS|CS2**
   - URL: https://www.kaggle.com/datasets/ilyazored/hltv-match-resultscs2/data
   - License: Apache 2.0
   - Shape: `cs2_results.csv`, match-level CS2 rows with `team_won`, `team_lost`, `event_name`, `shape`, `score`, `time`, `team1`, `team2`, and `target`.
   - Betto support: `convert-cs-kaggle-hltv-results` converts manually downloaded CSV rows to fixture-shaped JSON.
   - Limitation: no real HLTV numeric IDs, map names, per-map winners, player rows, or vetoes.

6. **Kaggle: CS2 HLTV Professional match statistics dataset**
   - URL: https://www.kaggle.com/datasets/griffindesroches/cs2-hltv-professional-match-statistics-dataset
   - License: CC0
   - Shape: match-level CS2 rows with many model-ready team/player features.
   - Limitation: the dataset page warns that some team-level statistics are scraped as current statistics rather than point-in-time values. Do not use those columns for production betting features unless provenance is independently validated.

## Tier 2 — Supplementary Sources

7. **Kaggle: Counter Strike 2 Match Data for Betting**
   - URL: https://www.kaggle.com/datasets/victorpicinin/counter-strike-2-hltv-match-data
   - License: unknown.
   - Shape: CS2 match data (Nov 2023 - Jan 2024) focused on betting analysis.
   - Betto fit: small window but may contain odds/betting features useful for calibration.

8. **Kaggle: CS2 Win Prediction (FACEIT)**
   - URL: https://www.kaggle.com/datasets/piercehentosh/counter-strike-2-win-prediction-faceit
   - License: unknown.
   - Shape: FACEIT matchmaking data for CS2 win prediction. Updated Mar 2025.
   - Betto fit: non-pro data, useful for FACEIT-specific modeling only.

9. **Kaggle: PGL CS2 Major Copenhagen 2024**
   - URL: https://www.kaggle.com/datasets/vanshbordia/pgl-cs2-major-copenhagen-2024-data
   - License: unknown.
   - Shape: single tournament deep-dive data.
   - Betto fit: supplementary validation for major events.

10. **Kaggle: CS2 Telemetry/Event Data**
    - URL: https://www.kaggle.com/datasets/billpureskillgg/cs2-2023-11-23
    - License: unknown.
    - Shape: demo-parsed telemetry/event data.
    - Betto fit: round-level and action-level features when demo parsing is needed.

## APIs

11. **GGScore CS2 API**
    - URL: https://ggscore.net/features
    - Shape: authenticated JSON API for completed and upcoming CS2 matches with pagination, team/event metadata, dates, and HLTV links.
    - Free tier: 3 requests/day (too limited for backfill, useful for live schedule checks).
    - Betto fit: possible live schedule/results source.

12. **Liquipedia API**
    - URL: https://liquipedia.net/api
    - Shape: REST API with 15+ years of roster changes, transfers, tournament brackets, match results.
    - Free tier: 1,000 requests/hour for open-source/educational/non-commercial use. Betting use prohibited on free tier.
    - Betto fit: **best source for roster history** and transfer data (for `cs.roster.days_since_change` feature). Requires contacting Liquipedia for full API docs.

13. **FACEIT Data API**
    - URL: https://docs.faceit.com
    - Shape: player ELO, match results, player stats for FACEIT platform matches.
    - Betto fit: FACEIT-specific only, not HLTV pro circuit.

14. **PandaScore**
    - URL: https://www.pandascore.co
    - Free tier: fixtures-only. Post-game stats require paid Historical plan ($2K+/month).
    - Betto fit: too expensive for current stage.

15. **Bettingiscool Pinnacle Data API**
    - URL: https://api.bettingiscool.com
    - Shape: 2.7B+ odds rows, Pinnacle opening/closing lines since 2021.
    - Pricing: paid.
    - Betto fit: backup if OddsPapi free tier proves insufficient for historical Pinnacle data.

## Research Data and Tools

16. **awpy (CS2 Demo Parser)**
    - URL: https://github.com/pnxenopoulos/awpy
    - License: MIT
    - Shape: parses CS2 demo files into tick-level kills, damages, economy, positions, rounds, player stats (ADR, KAST, Rating). Outputs Polars DataFrames.
    - Betto fit: **best path to round-level features** from demo files. Requires downloading .dem files from HLTV or FACEIT.
    - Requires: Python 3.11+, `pip install awpy`.

17. **ESTA Dataset**
    - URL: https://github.com/pnxenopoulos/esta
    - License: CC-BY-SA-4.0
    - Shape: 1,558 parsed CS:GO demos (3.9GB compressed), 41K rounds, 8.6M player actions, 7.9M frames.
    - Betto fit: research-grade trajectory/action modeling. Requires awpy 1.3.1 specifically.

18. **GitHub HLTV Scrapers**
    - gelbling/HLTV.org-Scraper (MIT, Scrapy-based, 3K+ matches)
    - jparedesDS/hltv-scraper (Selenium-based, detailed per-player stats)
    - nmwalsh/HLTV-Scraper (pure Python, multi-threaded, CSV output)
    - Betto fit: last resort for backfilling historical HLTV data not available in Kaggle datasets. Use with strict rate limiting.

## Current Bridges

### 1. CS2 HLTV Match Results (match-level, no maps)

```powershell
python -m core.cli.main convert-cs-kaggle-hltv-results --path data\downloads\cs2_results.csv --out-dir data\hltv_kaggle_results
```

Writes fixture-shaped JSON with series winners and scores. No map names or per-map winners. Suitable for contest/team/event backfill, not map-winner training.

### 2. Counter Strike Competitive Data (map-level with players)

```powershell
python -m core.cli.main convert-cs-kaggle-competitive-results --path data\downloads\match_results.csv --players-path data\downloads\match_players.csv --out-dir data\hltv_kaggle_competitive
```

Groups rows by `match_id`, preserves HLTV-derived IDs, normalizes maps, writes map-level winners. Attaches player participants. Output: 94,591 matches / 92,151 maps / 945,855 players.

### 3. CS:GO Professional Matches (map-level with vetoes and players)

```powershell
python -m core.cli.main convert-cs-kaggle-pro-matches --path "data\downloads\archive (1)\results.csv" --picks-path "data\downloads\archive (1)\picks.csv" --players-path "data\downloads\archive (1)\players.csv" --out-dir data\csgo_pro_matches
```

Map-level fixtures with veto sequences (wide-format picks.csv with `t1_removed_*`/`t1_picked_*`/`left_over` columns) and per-player stats. Handles `inverted_teams` flag for correct team attribution. Output: 27,240 matches / 45,752 maps / 265,335 players / 112,183 vetoes.

### 4. CS2 Rolling Stats — Time Series (series-level with point-in-time features)

```powershell
python -m core.cli.main convert-cs-rolling-stats --path "data\downloads\archive\updated_ts_cs_data.csv" --out-dir data\cs2_rolling_stats
```

Series-level fixtures with embedded rolling 5-match team features (ADR, KAST%, Rating 3.0, opening kills, clutches, etc.). Extracts HLTV stats match IDs from `detailed_stats_url`. Rolling features are point-in-time safe. Output: 8,226 matches with rolling features.

### 5. CS2 HLTV Match Data for Betting (map-level with per-player stats, no dates)

```powershell
python -m core.cli.main convert-cs2-match-data-betting --path "data\downloads\archive (2)\CS2_HLTV_MATCH_DATA2.csv" --out-dir data\cs2_match_data_betting
```

Semicolon-delimited map-level data with real HLTV matchIDs and per-player statistics (5 players/team, 14 stats each). **Limitation**: no date column — uses epoch sentinel (2000-01-01) for `scheduled_at`. Useful for matchID cross-reference and player stat analysis, not temporal features. Output: 627 matches / ~1,200 maps.

## Ingestion Policy

- Preserve raw downloaded files in the raw store before normalization.
- Record dataset URL, license, download date, and Kaggle version when available.
- Never infer map-level facts from series-level scores.
- Treat non-point-in-time feature columns as research-only until independently reproduced from historical inputs.
- Prefer datasets with stable IDs or source links; name-only rows require synthetic IDs and should not be mixed blindly with real HLTV IDs.
