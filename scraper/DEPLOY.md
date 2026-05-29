# HLTV Scraper VPS Deploy

This scraper is ready for a cautious VPS pilot. Start with a low daily cap, inspect the parsed JSON for 24-48 hours, then raise volume gradually.

## Automatic Install

After the repo is on the server, run:

```bash
cd /opt/betto/scraper
HLTV_PROXY_URL='http://username:password@gate.decodo.com:7000' \
  bash deploy/install-vps.sh --run-live-test
```

The script installs OS packages, creates `.venv`, installs Python dependencies, installs Playwright Chromium, writes `.env` if needed, runs preflight, optionally runs the live test, generates systemd units for the current repo path, and enables the timer.

Use `--project-dir /path/to/betto` if the repo is not at `/opt/betto`, or `--no-systemd` if you only want local setup.

## Git Push Hook

If the VPS is a Git remote and you want deployment to run automatically after `git push`, use [deploy/post-receive.sample](deploy/post-receive.sample) as the bare repo's `hooks/post-receive`.

Practical setup is:

1. Put the repo on the server once.
2. Run `bash deploy/install-vps.sh --run-live-test` once so `.env`, `.venv`, Chromium, and systemd are created.
3. Install the hook below so future pushes redeploy automatically.

One-time hook setup:

```bash
sudo mkdir -p /opt/betto
sudo chown "$USER:$USER" /opt/betto
git init --bare ~/betto.git
cp /opt/betto/scraper/deploy/post-receive.sample ~/betto.git/hooks/post-receive
chmod +x ~/betto.git/hooks/post-receive
```

Then from your laptop:

```bash
git remote add vps user@server:~/betto.git
git push vps main
```

The hook checks out `main` to `/opt/betto` and runs `bash deploy/install-vps.sh --project-dir /opt/betto`.

## Updating From Git

After the scraper is cloned on the VPS, deploy future code changes with:

```bash
cd /opt/betto/scraper
bash deploy/update-vps.sh
```

That script runs:

- `git pull`
- `bash deploy/install-vps.sh --project-dir /opt/betto`
- `sudo systemctl start hltv-scraper.service`
- `journalctl -u hltv-scraper.service -n 100 --no-pager`

Use `--branch main` if your GitHub branch is `main`, or `--no-start` if you only want to update code and timer files.

## Manual Ubuntu Setup

```bash
sudo apt update
sudo apt install -y python3.11 python3.11-venv git rsync
sudo mkdir -p /opt/betto
sudo chown "$USER:$USER" /opt/betto
```

Copy or clone the project into `/opt/betto`, then install the scraper:

```bash
cd /opt/betto/scraper
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium
cp .env.example .env
```

Edit `.env` and set your Decodo residential proxy credentials:

```env
HLTV_PROXY_URL=http://username:password@gate.decodo.com:7000
HLTV_DAILY_CAP=100
HLTV_EVENT_ALLOW_LIST=PGL Major,BLAST.tv Major,IEM,Intel Extreme Masters,ESL Pro League,BLAST Premier,CS Asia Championships,CCT,YaLLa,Roobet
```

## Smoke Test

```bash
cd /opt/betto/scraper
. .venv/bin/activate
python -m scraper.cli preflight --create-dirs
python -m scraper.cli test-live
python -m scraper.cli run
python -m scraper.cli backup
```

## Historical Backfill

Historical backfill runs automatically on the VPS through `hltv-backfill.timer`. It stores its cursor in `data/hltv_scraper.db`, so it can stop at the daily cap and continue later from the same HLTV results page.

Check it with:

```bash
systemctl list-timers hltv-backfill.timer
journalctl -u hltv-backfill.service -n 100 --no-pager
.venv/bin/python -m scraper.cli status --verbose
.venv/bin/python -m scraper.cli quality-report
.venv/bin/python -m scraper.cli validate-fixtures
.venv/bin/python -m scraper.cli health
.venv/bin/python -m scraper.cli failed --limit 20
.venv/bin/python -m scraper.cli stats-gaps
.venv/bin/python -m scraper.cli manifest --out data/hltv_scraped/manifest.json --include-files
.venv/bin/python -m scraper.cli report --out data/hltv_scraped/report.html
.venv/bin/python -m scraper.cli alert --title "HLTV scraper status"
.venv/bin/python -m scraper.cli reparse-raw
```

To start a backfill run immediately:

```bash
sudo systemctl start hltv-backfill.service
```

Each page is one HLTV results request with 100 result entries before event filtering. Manual one-off backfill is also available:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli backfill --pages 50 --matches 100
```

Use a larger page count to go further back:

```bash
.venv/bin/python -m scraper.cli backfill --pages 200 --matches 100
```

The daily cap still applies across discovery and match fetches. With `HLTV_DAILY_CAP=100`, a large backfill may take multiple days/runs. Increase it cautiously only after logs look healthy.

`backfill-auto` persists these state keys:

- `backfill_next_page`
- `backfill_empty_pages`
- `backfill_done`
- `backfill_started_at`
- `backfill_completed_at`

When `backfill_done = 1` and no due queue items remain, the backfill service disables `hltv-backfill.timer`.

Optional `.env` controls:

```env
HLTV_BACKFILL_MAX_PAGE=
HLTV_BACKFILL_STOP_DATE=
HLTV_ALERT_WEBHOOK_URL=
HLTV_EVENT_TIER_OVERRIDES=PGL Major=1,BLAST.tv Major=1,IEM Katowice=1,IEM Cologne=1,ESL Pro League=1,BLAST Premier World Final=1,CS Asia Championships=1,CCT=2,YaLLa Compass=2,Roobet Cup=2
```

`HLTV_BACKFILL_MAX_PAGE` is a hard stop by HLTV results page number, where each page is an offset of 100 results. `HLTV_ALERT_WEBHOOK_URL` receives one JSON completion alert when auto-backfill finishes.
`HLTV_BACKFILL_STOP_DATE` is a date boundary for historical backfill, such as `2023-09-27` for CS2-era coverage.
`HLTV_EVENT_TIER_OVERRIDES` pins event-name patterns to explicit priority tiers before the scraper falls back to HLTV star priority.

To requeue failed rows without editing SQLite:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli failed --limit 50
.venv/bin/python -m scraper.cli retry-failed --limit 100
sudo systemctl start hltv-backfill.service
```

To requeue finished matches that are missing player map stats:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli stats-gaps --limit 50
.venv/bin/python -m scraper.cli retry-stats-only --limit 50
sudo systemctl start hltv-backfill.service
```

To restart historical discovery from a specific page:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli reset-backfill --start-page 0
sudo systemctl enable --now hltv-backfill.timer
sudo systemctl start hltv-backfill.service
```

## Queue Lifecycle

The scraper keeps its queue in `data/hltv_scraper.db`.

- Finished matches with complete map data are marked `final = 1` and are not scraped again.
- Scheduled/live/incomplete matches are written to JSON but kept `final = 0` with a `next_attempt_at` refresh time.
- Scheduled matches refresh after about 6 hours, live matches after about 15 minutes, and finished-but-incomplete matches after about 1 hour.
- The daily cap is based on `request_log`, so it survives restarts and separate systemd runs on the same UTC day.

When deploying a version that adds lifecycle columns, no manual migration is needed. The SQLite schema is migrated automatically on startup. Existing old rows may be refreshed once so the scraper can assign the new lifecycle state.

## Manual systemd Timer

```bash
sudo cp /opt/betto/scraper/deploy/systemd/hltv-scraper.service /etc/systemd/system/
sudo cp /opt/betto/scraper/deploy/systemd/hltv-scraper.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hltv-scraper.timer
sudo systemctl list-timers hltv-scraper.timer
```

Check logs:

```bash
journalctl -u hltv-scraper.service -n 100 --no-pager
```

## Import Into Betto

```bash
cd /opt/betto
python -m core.cli.main convert-hltv-scraped \
  --raw-dir scraper/data/hltv_scraped \
  --out-dir data/hltv_fixtures
```

## Reparse Saved Raw HTML

Parser improvements do not require spending proxy requests again. Regenerate fixture JSON from already-saved raw HTML with:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli reparse-raw
.venv/bin/python -m scraper.cli quality-report
.venv/bin/python -m scraper.cli manifest --out data/hltv_scraped/manifest.json --include-files
```

## Backup Files

`python -m scraper.cli backup` writes a `.tar.gz` containing:

- `data/hltv_scraper.db`
- `data/raw/hltv`
- `data/hltv_scraped`

The systemd service runs this after each scheduled scrape.
