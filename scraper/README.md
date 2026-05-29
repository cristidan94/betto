# HLTV Scraper

Standalone scraper bot for HLTV.org CS2 match data. Produces fixture JSON for Betto.

## Setup

```bash
cd scraper
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
```

Edit `.env` with proxy credentials before live scraping. For Decodo residential proxies, use the dashboard username and password exactly as issued:

```env
HLTV_PROXY_URL=http://username:password@gate.decodo.com:7000
```

## Usage

```bash
python -m scraper.cli discover
python -m scraper.cli fetch
python -m scraper.cli parse
python -m scraper.cli reparse-raw
python -m scraper.cli run
python -m scraper.cli backfill --pages 50 --matches 100
python -m scraper.cli backfill-auto
python -m scraper.cli status
python -m scraper.cli status --verbose
python -m scraper.cli health
python -m scraper.cli quality-report
python -m scraper.cli validate-fixtures
python -m scraper.cli failed --limit 20
python -m scraper.cli show-match 2394349
python -m scraper.cli stats-gaps
python -m scraper.cli retry-stats-only
python -m scraper.cli retry-failed --limit 100
python -m scraper.cli reset-backfill --start-page 0
python -m scraper.cli manifest --out data/hltv_scraped/manifest.json --include-files
python -m scraper.cli report --out data/hltv_scraped/report.html
python -m scraper.cli alert --title "HLTV scraper status"
python -m scraper.cli preflight --create-dirs
python -m scraper.cli test-live
python -m scraper.cli export
python -m scraper.cli backup
python -m scraper.cli discover-upcoming
python -m scraper.cli scrape-events --limit 30
python -m scraper.cli scrape-teams --limit 30
python -m scraper.cli scrape-players --limit 50
python -m scraper.cli scrape-rankings --date 2026-05-26
python -m scraper.cli backfill-rankings
python -m scraper.cli rankings-status
python -m scraper.cli tier-registry
python -m scraper.cli stats-errors
```

Run `preflight` before live scraping. It checks local dependencies, proxy configuration, output paths, rate limits, and quiet hours without making any HLTV requests.
See `DEPLOY.md` for VPS setup and the included systemd timer.

If your proxy provider returns a self-signed certificate chain on the VPS, set `HLTV_VERIFY_TLS=false` in `.env` and rerun `preflight`.

Queue lifecycle is stored in SQLite. Finished complete matches are final; scheduled, live, and incomplete matches are deferred and refreshed later.
`HLTV_EVENT_ALLOW_LIST` can be set in `.env` to tune which event names discovery accepts.
The request daily cap is persisted from SQLite request logs, so restarting the systemd service does not reset it.
Use `backfill` to walk deeper through older HLTV results pages without changing the scheduled timer command.
On the VPS, `hltv-backfill.timer` runs `backfill-auto` hourly, persists its page cursor in SQLite, and disables itself when historical discovery is exhausted.
Use `quality-report` to inspect whether parsed files have maps, players, vetoes, and player stats. Use `health` for a quick no-network operational check that can fail loudly when recent requests or failed queue rows look unhealthy.
If you want a hard safety bound for historical scanning, set `HLTV_BACKFILL_MAX_PAGE` in `.env`. If you set `HLTV_ALERT_WEBHOOK_URL`, the backfill sends one completion webhook when historical discovery is done.
Use `HLTV_BACKFILL_STOP_DATE=2023-09-27` to stop historical discovery at a date boundary when result-page dates are available.
`HLTV_EVENT_TIER_OVERRIDES` lets you pin event-name patterns to explicit priority tiers, for example `IEM Cologne=1,CCT=2`. The scraper checks these overrides before falling back to HLTV star priority.
Use `manifest` after a backfill/export to write a reproducible data snapshot hash, fixture schema version, counts, and quality summary.
Use `validate-fixtures` before training, `stats-gaps` to find finished matches missing player map stats, and `retry-stats-only` to requeue those matches.
Use `report` to write a static HTML operations report.
Use `alert` to send the current status, health, and quality report to `HLTV_ALERT_WEBHOOK_URL` on demand.
Use `reparse-raw` after parser improvements to regenerate fixture JSON from saved raw HTML without making new HLTV requests.

For a one-command VPS install after pushing the repo:

```bash
cd /opt/betto/scraper
HLTV_PROXY_URL='http://username:password@gate.decodo.com:7000' bash deploy/install-vps.sh --run-live-test
```

For later updates on the VPS:

```bash
cd /opt/betto/scraper
bash deploy/update-vps.sh
```

## Testing

```bash
python -m pytest tests/ -v
python -m unittest discover -s tests
python -m scraper.cli test-live
```

The live test needs Playwright browsers and a proxy suitable for HLTV.
