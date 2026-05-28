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
python -m scraper.cli run
python -m scraper.cli status
python -m scraper.cli preflight --create-dirs
python -m scraper.cli test-live
python -m scraper.cli export
python -m scraper.cli backup
```

Run `preflight` before live scraping. It checks local dependencies, proxy configuration, output paths, rate limits, and quiet hours without making any HLTV requests.
See `DEPLOY.md` for VPS setup and the included systemd timer.

If your proxy provider returns a self-signed certificate chain on the VPS, set `HLTV_VERIFY_TLS=false` in `.env` and rerun `preflight`.

Queue lifecycle is stored in SQLite. Finished complete matches are final; scheduled, live, and incomplete matches are deferred and refreshed later.
`HLTV_EVENT_ALLOW_LIST` can be set in `.env` to tune which event names discovery accepts.
The request daily cap is persisted from SQLite request logs, so restarting the systemd service does not reset it.

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
