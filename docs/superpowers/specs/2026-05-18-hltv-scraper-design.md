# HLTV Scraper Design Spec

Date: 2026-05-18

## 1. Goal

Build a standalone HLTV scraper bot that extracts match results, map scores, vetoes, and per-player per-map statistics from HLTV.org without getting IP-blocked. The bot runs locally for development and testing, then deploys to a cheap VPS for 24/7 operation. It produces fixture JSON compatible with Betto's existing `CsParsedMatch` pipeline.

## 2. Scope

### In Scope

- Tier 1-2 CS2 matches from the last 2 years (~5,000-8,000 matches).
- Maximum data depth per match: match page, stats overview, per-map detailed stats (CT/T splits, economy, opening duels, clutches, utility damage).
- Daily incremental scraping of new matches.
- Hybrid fetcher: `curl_cffi` fast path with Playwright fallback.
- Rotating residential proxies (BrightData or SmartProxy, $15-30/month).
- Standalone deployable package with step-by-step VPS deployment instructions.
- Integration test suite that validates scraping against live HLTV pages before deployment.

### Out of Scope (Future)

- Player profile pages and career stats.
- Team ranking history pages.
- Demo file downloads.
- Tier 3+ events.
- Historical backfill before June 2023.

## 3. Architecture

### 3.1 Standalone Package

The scraper is a self-contained Python package at `scraper/` in the repo root. It does NOT import from `core/`, `sports/`, or any Betto module. It has its own `requirements.txt`, its own entry point, and can be deployed independently.

```
scraper/
  scraper/
    __init__.py
    cli.py              # Entry point: python -m scraper.cli
    fetcher.py          # HltvFetcher (curl_cffi + Playwright hybrid)
    proxy.py            # ProxyRotator
    rate_limiter.py     # RateLimiter with jitter, cooldowns, daily caps
    session.py          # SessionManager (Playwright browser lifecycle)
    discovery.py        # Results page crawler, match ID extraction
    match_scraper.py    # Orchestrates fetch of match + stats + map pages
    parser.py           # Raw HTML -> structured data
    tracking_db.py      # SQLite queue and request log
    models.py           # Dataclasses for parsed match data
    config.py           # Settings from env vars or config file
    anti_detect.py      # Header profiles, fingerprint rotation, decoy requests
  tests/
    test_parser.py      # Unit tests with saved HTML fixtures
    test_fetcher.py     # Integration tests against live HLTV
    test_rate_limiter.py
    test_anti_detect.py
    fixtures/           # Saved HTML pages for offline parser testing
  requirements.txt
  Dockerfile
  README.md
  .env.example
```

**Output**: The scraper writes raw HTML to `data/raw/hltv/` and parsed JSON to `data/hltv_scraped/`. A separate Betto CLI command (`convert-hltv-scraped`) imports the parsed JSON into the main fixture store.

### 3.2 Hybrid Fetcher

```
URL --> curl_cffi (TLS-impersonated GET, ~200ms)
    |
    +--> Response OK (200 + valid HTML)?
    |       --> return HTML, save to raw store
    |
    +--> Cloudflare challenge (403, or JS challenge in body)?
            --> Playwright fallback (~3-5s)
                --> return HTML, save to raw store
            --> Log URL pattern as "needs_playwright" in tracking DB
    |
    +--> Both fail?
            --> Log error, increment retry_count, skip for now
```

**Challenge detection**: Check for status 403, 429, or HTML body containing `"cf-challenge"`, `"cf-browser-verification"`, or `"Checking your browser"`.

**Blocked pattern cache**: If a URL pattern (e.g., `/stats/matches/`) triggers Playwright fallback 3+ times in a row, skip curl_cffi for that pattern going forward. Reset the cache weekly.

### 3.3 Proxy Configuration

Supports BrightData and SmartProxy residential proxy formats via environment variable:

```
HLTV_PROXY_URL=http://user-session-{session}:password@gate.smartproxy.com:10000
```

The `{session}` placeholder is replaced per-request with a random string for IP rotation, or kept constant for 5-10 minutes during sticky sessions (match page + its stats pages).

**Geo-targeting**: Rotate between `us`, `eu`, `br` country parameters (appended to proxy URL per provider's format).

### 3.4 Rate Limiting

| Parameter | Value | Rationale |
|---|---|---|
| Base delay | 8-15s (uniform random) | Mimics human browsing pace |
| Cooldown pause | 90-180s every 40-60 requests | Prevents sustained high-rate detection |
| Daily cap | 5,000 requests | Keeps monthly bandwidth under budget |
| Quiet hours | 03:00-06:00 UTC (no scraping) | Low real-user traffic makes scrapers conspicuous |
| Failure backoff | 5 min after 3 consecutive failures | Avoids hammering during blocks |
| Emergency halt | 1 hour after 10 failures/hour | Full stop to prevent IP burn |

### 3.5 Anti-Detection Layers

**Layer 1 — TLS Fingerprint (curl_cffi)**
- Rotate between `chrome120`, `chrome124`, `chrome131` impersonation profiles per session.

**Layer 2 — Request Headers**
- 5-10 realistic browser header sets (User-Agent, Accept, Accept-Language, Sec-CH-UA, etc.).
- `Referer` header set to the previous HLTV page in the navigation sequence.
- Random header set per session (30-50 requests).

**Layer 3 — Behavioral Patterns**
- 1 in 20 requests is a "decoy" — visit homepage, event page, or team page.
- Navigate match -> stats -> map stats in natural order, not random.
- Vary daily scraping start time by +/- 2 hours.

**Layer 4 — Proxy Rotation**
- New residential IP per request (default).
- Sticky session (same IP) for match + its related stats pages (~2-5 min).
- Geo-rotation between US, EU, BR.

**Layer 5 — Playwright Fallback**
- `playwright-stealth` plugin for WebGL, canvas, navigator overrides.
- Browser instance reused for 10-20 requests, then recycled with new fingerprint.
- Same proxy as the failed curl_cffi request.

### 3.6 Detection Recovery

| Condition | Action |
|---|---|
| Single 403/429 | Retry once with Playwright + different proxy region |
| 3 consecutive failures | Pause 5 minutes, switch proxy region |
| 10 failures in 1 hour | Halt for 1 hour |
| 50 failures in 1 day | Halt for 24 hours, alert via log |
| Repeated pattern failures | Mark URL pattern as needs_playwright in DB |

## 4. HLTV Page Targets

### 4.1 Discovery — Results Pages

**URL**: `https://www.hltv.org/results?offset={n}&stars=4&stars=5` (HLTV star rating: 5 = tier 1 majors/EPL, 4 = tier 2 large events)

**Extracted**: List of match IDs, team names, event names, event star ratings, dates. Each page has ~100 matches.

**Filtering** (two stages): The URL `stars` parameter pre-filters to 4-5 star events server-side. After parsing each results page, a second pass checks event names against a curated allow-list and drops any that slipped through (HLTV occasionally mis-rates events):
- Majors (PGL, FACEIT, StarLadder, ESL, IEM Katowice/Cologne)
- ESL Pro League
- BLAST Premier (Spring/Fall/World Final)
- IEM series
- PGL series
- NAVI/Vitality/FaZe invitational tier events

### 4.2 Match Page

**URL**: `https://www.hltv.org/matches/{match_id}/{slug}`

**Extracted**:
- `match_id` (from URL)
- `scheduled_at` (datetime)
- `best_of` (1, 3, or 5)
- Team A and Team B: name, HLTV team ID (from team page links)
- Event: name, HLTV event ID, star rating
- Series score
- Per-map: map name, team A score, team B score, winner, map stats link ID
- Veto sequence: team, action (ban/pick/left_over), map name
- Player lineup: player HLTV ID, nickname, team ID (from player page links)
- Stats page link (contains stats match ID)

### 4.3 Stats Overview Page

**URL**: `https://www.hltv.org/stats/matches/{stats_id}/{slug}`

**Extracted** (per player, per map):
- Kills, assists, deaths
- K/D ratio
- ADR (average damage per round)
- KAST%
- HLTV Rating (1.0 or 2.0)
- Headshot %
- First kills, first deaths
- Map stats page link IDs (for detailed per-map breakdowns)

### 4.4 Map Stats Page

**URL**: `https://www.hltv.org/stats/matches/mapstatsid/{map_stats_id}/{slug}`

**Extracted** (per player, for this specific map):
- CT-side and T-side stat splits (kills, deaths, ADR, rating)
- Opening kills/deaths
- Clutch wins (1v1 through 1v5)
- Utility damage per round
- Round-by-round economy data (if available in the page)

### 4.5 Requests Per Match

| Match Type | Match Page | Stats Page | Map Stats Pages | Total |
|---|---|---|---|---|
| BO1 | 1 | 1 | 1 | **3** |
| BO3 (2 maps played) | 1 | 1 | 2 | **4** |
| BO3 (3 maps played) | 1 | 1 | 3 | **5** |
| BO5 (3-5 maps played) | 1 | 1 | 3-5 | **5-7** |

**Average across typical tier 1-2 matches: ~4 requests per match.**

## 5. Raw Store & Parser

### 5.1 Raw Store Layout

```
data/raw/hltv/
  matches/
    {match_id}/
      match.html
      stats.html
      map_{map_stats_id}.html   (one per map played)
      meta.json                 (fetch timestamps, proxy info, status codes)
  results/
    page_{offset}.html
```

Every response is saved as-is before parsing. `meta.json` example:

```json
{
  "match_id": "2371234",
  "fetched_at": "2026-05-18T14:30:00Z",
  "pages": {
    "match": {"status": 200, "fetcher": "curl_cffi", "bytes": 52340, "elapsed_ms": 310},
    "stats": {"status": 200, "fetcher": "curl_cffi", "bytes": 48120, "elapsed_ms": 280},
    "map_12345": {"status": 200, "fetcher": "playwright", "bytes": 61200, "elapsed_ms": 4200}
  }
}
```

### 5.2 Parser

`scraper/parser.py` contains pure functions that take raw HTML and return structured dataclasses defined in `scraper/models.py`. These dataclasses mirror Betto's `CsParsedMatch` structure but are independent types.

The parser is tested against saved HTML fixtures in `scraper/tests/fixtures/` — real HLTV pages saved during the integration test phase.

### 5.3 Output

The parser writes JSON fixture files to `data/hltv_scraped/{match_id}.json`. Format:

```json
{
  "hltv_id": "2371234",
  "scheduled_at": "2026-05-18T12:00:00+00:00",
  "best_of": 3,
  "status": "finished",
  "team_a": {"hltv_id": "4608", "name": "Natus Vincere"},
  "team_b": {"hltv_id": "6667", "name": "FaZe"},
  "event": {"hltv_id": "7148", "name": "IEM Katowice 2026", "tier": "5"},
  "players": [...],
  "maps": [
    {
      "map_index": 1,
      "map_name": "Inferno",
      "team_a_score": 13,
      "team_b_score": 9,
      "winner_hltv_id": "4608",
      "player_stats": {
        "s1mple": {
          "kills": 24, "deaths": 15, "adr": 92.3, "rating": 1.45,
          "ct_kills": 14, "ct_deaths": 8, "t_kills": 10, "t_deaths": 7,
          "first_kills": 4, "first_deaths": 1, "clutches_won": 2
        }
      }
    }
  ],
  "vetoes": [...],
  "source": {"name": "hltv-scraper", "url": "https://www.hltv.org/matches/2371234/..."}
}
```

A Betto CLI command (`convert-hltv-scraped`) reads these files and writes them into the main fixture store, mapping the standalone data model to `CsParsedMatch`.

## 6. Tracking Database

SQLite at `data/hltv_scraper.db`.

### 6.1 Tables

```sql
CREATE TABLE scrape_queue (
    match_id        TEXT PRIMARY KEY,
    match_url       TEXT NOT NULL,
    event_name      TEXT,
    event_stars     INTEGER,
    scheduled_at    TEXT,
    discovered_at   TEXT DEFAULT (datetime('now')),
    match_fetched   INTEGER DEFAULT 0,
    stats_fetched   INTEGER DEFAULT 0,
    maps_fetched    INTEGER DEFAULT 0,
    maps_total      INTEGER,
    parsed          INTEGER DEFAULT 0,
    priority_tier   INTEGER DEFAULT 1,
    last_error      TEXT,
    retry_count     INTEGER DEFAULT 0,
    updated_at      TEXT
);

CREATE TABLE blocked_patterns (
    url_pattern     TEXT PRIMARY KEY,
    needs_playwright INTEGER DEFAULT 0,
    consecutive_blocks INTEGER DEFAULT 0,
    last_tested     TEXT
);

CREATE TABLE request_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url             TEXT,
    status_code     INTEGER,
    fetcher_type    TEXT,
    proxy_region    TEXT,
    response_bytes  INTEGER,
    elapsed_ms      INTEGER,
    created_at      TEXT DEFAULT (datetime('now'))
);
```

### 6.2 Resumability

Main loop per run:

1. **Discovery**: Scrape results pages, insert new match IDs into `scrape_queue`.
2. **Fetch**: Query `SELECT * FROM scrape_queue WHERE NOT parsed AND retry_count < 5 ORDER BY priority_tier, scheduled_at DESC`.
3. For each match: check `match_fetched`, `stats_fetched`, `maps_fetched < maps_total` — only fetch what's missing.
4. After all pages saved: run parser, set `parsed = 1`.

Process can be killed at any point. Next run resumes from the exact position.

## 7. Scrape Priority & Timeline

### 7.1 Priority Tiers

| Tier | Description | Matches | Requests | Est. Cost | Est. Time |
|---|---|---|---|---|---|
| 1 | CS2 tier 1-2, last 6 months | ~2,000-3,000 | ~10,000-15,000 | ~$10 | ~5-7 days |
| 2 | CS2 tier 1-2, 6-24 months ago | ~3,000-5,000 | ~15,000-20,000 | ~$12-15 | ~7-10 days |
| Daily | New matches (ongoing) | 10-30/day | ~60-120/day | <$1/day | ~15 min |

### 7.2 Event Allow-List

Curated list of tier 1-2 event series for filtering discovery results:

```
PGL Major, IEM Katowice, IEM Cologne, IEM Chengdu, IEM Dallas, IEM Sydney,
ESL Pro League, BLAST Premier Spring, BLAST Premier Fall, BLAST Premier World Final,
BLAST.tv Major, Intel Extreme Masters, Thunderpick World Championship,
CS Asia Championships, Perfect World Major, FACEIT Major, StarLadder Major,
YaLLa Compass, Roobet Cup, Betway Championship, CCT series (tier 2)
```

This list is maintained in `scraper/config.py` and can be updated without code changes.

## 8. CLI Interface

```
python -m scraper.cli discover      # Find new match IDs from results pages
python -m scraper.cli fetch         # Fetch pending matches (match + stats + map pages)
python -m scraper.cli parse         # Parse all fetched-but-unparsed matches
python -m scraper.cli run           # Full pipeline: discover + fetch + parse
python -m scraper.cli status        # Show queue stats (pending/fetched/parsed/errors)
python -m scraper.cli test-live     # Integration test: fetch 3 real matches, validate parsing
python -m scraper.cli export        # Copy parsed JSON to Betto fixture store
```

All commands read config from environment variables (`.env` file):

```
HLTV_PROXY_URL=http://user-session-{session}:pass@gate.smartproxy.com:10000
HLTV_PROXY_REGIONS=us,eu,br
HLTV_RAW_DIR=data/raw/hltv
HLTV_OUTPUT_DIR=data/hltv_scraped
HLTV_DB_PATH=data/hltv_scraper.db
HLTV_DAILY_CAP=5000
HLTV_MIN_DELAY=8
HLTV_MAX_DELAY=15
HLTV_COOLDOWN_EVERY=50
HLTV_COOLDOWN_SECONDS=120
```

## 9. Integration Testing (Pre-Deployment Gate)

Before deploying to VPS, run the live integration test suite to verify every page type parses correctly:

```
python -m scraper.cli test-live
```

This command:

1. **Fetches 3 real matches** from HLTV using the configured proxy:
   - One recent BO3 from a major event (tests full depth)
   - One BO1 (tests minimal map case)
   - One match with overtime (tests edge case scoring)

2. **For each match, validates:**
   - Match page: teams extracted, event name present, map count > 0, veto sequence non-empty
   - Stats page: player count == 10 (5 per team), all have kills/deaths/rating
   - Map stats pages: CT/T splits present, round count matches score (e.g., 16+13 = 29 rounds)
   - All HLTV IDs are numeric (not synthetic/kaggle-prefixed)

3. **Tests both fetcher paths:**
   - Forces one request through curl_cffi
   - Forces one request through Playwright
   - Verifies both return valid HTML

4. **Saves test fixtures** to `scraper/tests/fixtures/` for offline parser testing.

5. **Reports results:**
   ```
   Match 2371234 (NAVI vs FaZe, BO3):
     match.html: OK (52KB, curl_cffi, 310ms)
     stats.html: OK (48KB, curl_cffi, 280ms)
     map_12345.html: OK (61KB, playwright, 4200ms)
     map_12346.html: OK (59KB, curl_cffi, 290ms)
     map_12347.html: OK (63KB, curl_cffi, 320ms)
     Parser: OK (3 maps, 10 players, 7 vetoes)
   
   All 3 matches passed. Fixtures saved to scraper/tests/fixtures/
   Ready for deployment.
   ```

**This test must pass before any VPS deployment.** The saved fixtures also become the baseline for offline parser unit tests.

## 10. VPS Deployment Guide

### 10.1 Prerequisites

- A VPS with Ubuntu 22.04+ (DigitalOcean $6/mo droplet, Hetzner CX22 at EUR 4/mo, or similar).
- SSH access to the VPS.
- A residential proxy account (BrightData or SmartProxy) with credentials.
- The scraper integration test (`test-live`) passing on your local machine.

### 10.2 Step-by-Step Deployment

**Step 1: Provision VPS**

Create a VPS with at least 1 CPU, 2 GB RAM, 20 GB SSD. Ubuntu 22.04 LTS recommended.

```bash
# After SSH-ing into the VPS:
sudo apt update && sudo apt upgrade -y
```

**Step 2: Install system dependencies**

```bash
sudo apt install -y python3.11 python3.11-venv python3-pip git curl
```

**Step 3: Install Playwright system dependencies**

```bash
sudo apt install -y libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
  libgbm1 libpango-1.0-0 libcairo2 libasound2 libxshmfence1
```

**Step 4: Clone and set up the scraper**

```bash
cd /opt
sudo mkdir -p betto-scraper && sudo chown $USER:$USER betto-scraper
git clone <your-repo-url> betto-scraper
cd betto-scraper/scraper

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

**Step 5: Configure environment**

```bash
cp .env.example .env
nano .env
```

Fill in:
```
HLTV_PROXY_URL=http://user-session-{session}:YOUR_PASS@gate.smartproxy.com:10000
HLTV_PROXY_REGIONS=us,eu,br
HLTV_RAW_DIR=/opt/betto-scraper/data/raw/hltv
HLTV_OUTPUT_DIR=/opt/betto-scraper/data/hltv_scraped
HLTV_DB_PATH=/opt/betto-scraper/data/hltv_scraper.db
HLTV_DAILY_CAP=5000
HLTV_MIN_DELAY=8
HLTV_MAX_DELAY=15
```

**Step 6: Create data directories**

```bash
mkdir -p /opt/betto-scraper/data/raw/hltv/matches
mkdir -p /opt/betto-scraper/data/raw/hltv/results
mkdir -p /opt/betto-scraper/data/hltv_scraped
```

**Step 7: Run integration test on VPS**

```bash
cd /opt/betto-scraper/scraper
source .venv/bin/activate
python -m scraper.cli test-live
```

Verify all 3 test matches pass. If Playwright tests fail, check system dependencies (Step 3).

**Step 8: Test a small scrape run**

```bash
python -m scraper.cli discover --limit 5
python -m scraper.cli status
python -m scraper.cli fetch --limit 5
python -m scraper.cli parse
python -m scraper.cli status
```

Verify: 5 matches discovered, fetched, parsed. Check `data/hltv_scraped/` for valid JSON files.

**Step 9: Set up systemd service**

```bash
sudo tee /etc/systemd/system/hltv-scraper.service > /dev/null << 'EOF'
[Unit]
Description=HLTV Scraper Bot
After=network.target

[Service]
Type=oneshot
User=root
WorkingDirectory=/opt/betto-scraper/scraper
EnvironmentFile=/opt/betto-scraper/scraper/.env
ExecStart=/opt/betto-scraper/scraper/.venv/bin/python -m scraper.cli run
StandardOutput=append:/var/log/hltv-scraper.log
StandardError=append:/var/log/hltv-scraper.log

[Install]
WantedBy=multi-user.target
EOF
```

**Step 10: Set up cron schedule**

```bash
sudo tee /etc/systemd/system/hltv-scraper.timer > /dev/null << 'EOF'
[Unit]
Description=Run HLTV scraper every 6 hours

[Timer]
OnCalendar=*-*-* 07:00,13:00,19:00,01:00:00
RandomizedDelaySec=1800
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now hltv-scraper.timer
```

This runs the scraper 4 times daily at 07:00, 13:00, 19:00, and 01:00 UTC (with up to 30 min random jitter). Each run discovers new matches, fetches pending pages, and parses results.

**Step 11: Verify it's running**

```bash
sudo systemctl status hltv-scraper.timer
sudo journalctl -u hltv-scraper.service --since "1 hour ago"
tail -50 /var/log/hltv-scraper.log
```

**Step 12: Set up data sync to your local machine**

On your local machine, create a script to pull scraped data:

```bash
#!/bin/bash
rsync -avz --progress vps-user@your-vps-ip:/opt/betto-scraper/data/hltv_scraped/ ./data/hltv_scraped/
```

Or set up a cron job on the VPS to push to a cloud bucket (S3, GCS, or Backblaze B2).

### 10.3 Monitoring

Check scraper health:

```bash
# On VPS:
python -m scraper.cli status

# Expected output:
# Queue: 5234 total, 3100 fetched, 2890 parsed, 12 errors
# Today: 342 requests, 2.1 MB bandwidth, 3 failures
# Last run: 2026-05-18 13:04 UTC, 45 matches processed
```

Check `request_log` for block rate:

```bash
sqlite3 data/hltv_scraper.db "
  SELECT fetcher_type, status_code, COUNT(*)
  FROM request_log
  WHERE created_at > datetime('now', '-1 day')
  GROUP BY fetcher_type, status_code
  ORDER BY COUNT(*) DESC;
"
```

### 10.4 Troubleshooting

| Problem | Fix |
|---|---|
| High 403 rate (>20%) | Reduce daily cap, increase delays, check proxy subscription is active |
| Playwright crashes | Check RAM (need ~500MB free), reinstall: `playwright install chromium` |
| Parser errors | Run `parse` again after fixing parser; raw HTML is preserved |
| Disk full | Archive old `data/raw/hltv/results/` pages (discovery cache, not needed long-term) |
| Proxy bandwidth exceeded | Reduce `HLTV_DAILY_CAP`, increase `HLTV_MIN_DELAY` |

## 11. Betto Integration

After scraping, import into Betto's fixture store:

```powershell
python -m core.cli.main convert-hltv-scraped --raw-dir data/hltv_scraped --out-dir data/hltv_fixtures
```

This command:
1. Reads each `{match_id}.json` from the scraper's output directory.
2. Maps the standalone data model to Betto's `CsParsedMatch`.
3. Writes fixture JSON in the same format as all other converters.
4. Skips matches that already exist in the target directory.

The imported fixtures feed directly into `build_map_winner_dataset()`, feature materializers (30d/90d/180d win rates, Glicko-2), and the baseline model.

## 12. Dependencies

### scraper/requirements.txt

```
curl_cffi>=0.7.0
playwright>=1.40.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
python-dotenv>=1.0.0
```

### System (VPS)

```
python3.11+
chromium system libraries (see Step 3)
```

No database server. No Redis. No Docker required (optional Dockerfile provided for convenience).
