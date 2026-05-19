# Betto

CS-first betting alpha research and recommendation platform.

The codebase is organized around a reusable core platform plus game-specific plugins. Counter-Strike is the first plugin.

## Quick Start

```powershell
$py = 'C:\Users\crist\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $py -m core.cli.main validate-config
& $py -m unittest discover tests
```

## WSL Startup

Start the WSL Betto environment from Windows:

```powershell
.\scripts\start-betto-wsl.cmd
```

Or from an existing PowerShell session:

```powershell
.\scripts\start-betto-wsl.ps1
```

The starter enters WSL at `/mnt/c/Users/crist/Desktop/betto`, creates/uses `.betto/wsl-venv`, installs `psycopg` in that venv if needed, starts the WSL Postgres cluster if it is down, exports:

```text
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto
```

and runs `db-check` plus idempotent migrations before leaving you in an interactive shell.

Useful options:

```powershell
.\scripts\start-betto-wsl.ps1 -SkipMigrations
.\scripts\start-betto-wsl.ps1 -NoShell
.\scripts\start-betto-wsl.ps1 -DatabaseUrl "postgresql://betto:betto@localhost:5433/betto"
```

Run a single Betto command inside WSL without leaving an interactive shell open:

```powershell
.\scripts\run-betto-wsl.ps1 -ApplyMigrations -BettoCommand "python -m core.cli.main db-check"
```

Run the DB-backed fixture verification workflow inside WSL:

```powershell
.\scripts\verify-betto-wsl-db.ps1
```

The non-interactive runner will not prompt for `sudo` by default. If the WSL Postgres cluster is already online on port `5433`, it can run unattended. If the cluster is down, start Postgres once in WSL or run from an interactive terminal with `-AllowSudo`.

## Console API Dev

The first console screens are wired through FastAPI fixture endpoints. Run the API and Vite dev server in two terminals:

```powershell
$env:BETTO_API_PORT = '8000'
& $py scripts\dev_api_server.py
```

```powershell
cd console
$env:BETTO_API_URL = 'http://127.0.0.1:8000'
npm run dev
```

If port `8000` is unavailable, use another port for both variables, for example `8001`.

By default the API serves checked-in fixture data, which keeps the console usable without Postgres. To serve from the Betto database instead, set:

```powershell
$env:BETTO_API_DATA_SOURCE = 'postgres'
$env:BETTO_DATABASE_URL = 'postgresql://betto:betto@localhost:5433/betto'
```

The current console endpoints are:

- `GET /api/today/recommendations`
- `GET /api/recommendations/{rec_id}`
- `GET /api/matches`
- `GET /api/matches/{match_id}/markets`
- `GET /api/strategies/{strategy_id}`
- `GET /api/bets`
- `GET /api/ingestion`
- `GET /api/risk`

## Offline Evaluation Workflow

The current alpha can run end-to-end against the checked-in CS fixture corpus and market price corpus without Postgres or network access.

Parse one HLTV-style fixture and inspect normalized entity counts:

```powershell
& $py -m core.cli.main parse-cs-fixture --path tests\fixtures\cs_match_001.json
```

Convert a manually downloaded Kaggle CS2 HLTV match-results CSV into fixture-shaped JSON:

```powershell
& $py -m core.cli.main convert-cs-kaggle-hltv-results --path data\downloads\cs2_results.csv --out-dir data\hltv_kaggle_results
```

Convert the richer Kaggle Counter Strike Competitive Data `match_results.csv` into map-level fixtures:

```powershell
& $py -m core.cli.main convert-cs-kaggle-competitive-results --path data\downloads\match_results.csv --players-path data\downloads\match_players.csv --out-dir data\hltv_kaggle_competitive
```

Materialize point-in-time map win-rate features from the sample corpus:

```powershell
& $py -m core.cli.main materialize-cs-features --as-of 2026-02-20T00:00:00Z --fixtures tests\fixtures\corpus\cs_match_001.json tests\fixtures\corpus\cs_match_002.json tests\fixtures\corpus\cs_match_003.json
```

Evaluate the dependency-light baseline model and optionally write a model artifact:

```powershell
& $py -m core.cli.main evaluate-cs-baseline --fixtures tests\fixtures\corpus\cs_match_001.json tests\fixtures\corpus\cs_match_002.json --include-calibration --write-artifact
```

Run walk-forward validation over the fixture corpus:

```powershell
& $py -m core.cli.main walk-forward-cs-baseline --corpus tests\fixtures\corpus --start 2026-01-01 --end 2026-02-15 --train-days 30 --validate-days 14 --step-days 14
```

Run compact paper evaluation against fixture market prices:

```powershell
& $py -m core.cli.main paper-evaluate-cs-baseline --corpus tests\fixtures\corpus --markets tests\fixtures\market_corpus --compact --min-edge 0.03 --max-recommendations-per-match 1
```

Optional risk caps are available for stake size and daily exposure:

```powershell
& $py -m core.cli.main paper-evaluate-cs-baseline --corpus tests\fixtures\cs_match_001.json --markets tests\fixtures\cs_market_prices.json --compact --market-bankroll-cap 0.01 --max-daily-bankroll-fraction 0.015
```

Write or print a human-review handoff containing only accepted recommendations:

```powershell
& $py -m core.cli.main paper-evaluate-cs-baseline --corpus tests\fixtures\cs_match_001.json --markets tests\fixtures\cs_market_prices.json --accepted-only --write-accepted-json --write-accepted-csv --max-accepted-output 10
```

Accepted handoff rows include the recommendation, settlement fields, CLV/PnL fields, feature values, and model score breakdown used by the baseline model.

For a compact daily review digest:

```powershell
& $py -m core.cli.main paper-evaluate-cs-baseline --corpus tests\fixtures\cs_match_001.json --markets tests\fixtures\cs_market_prices.json --digest --max-accepted-output 10
```

Build the compact baseline strategy report with readiness checks:

```powershell
& $py -m core.cli.main report-cs-baseline-strategy --corpus tests\fixtures\corpus --markets tests\fixtures\market_corpus --compact
```

Readiness thresholds can be tuned from the command line:

```powershell
& $py -m core.cli.main report-cs-baseline-strategy --corpus tests\fixtures\corpus --markets tests\fixtures\market_corpus --compact --max-brier-score 0.30 --max-log-loss 0.80 --max-total-bankroll-fraction 0.25 --max-drawdown-per-unit-stake 3.0 --min-paper-recommendations 1 --min-mean-edge 0.03
```

Expected sample report highlights:

- `12` model rows.
- Brier score around `0.2602`.
- Log loss around `0.7147`.
- `12` paper candidates.
- `4` passing paper recommendations.
- Daily exposure summaries for accepted recommendations.
- Max drawdown per unit stake; currently `0.0` on the sample corpus.
- Readiness checks pass with the default model, paper, exposure, drawdown, and edge thresholds.

Artifacts written with `--write-artifact` or `--write-csv` land under `.betto\artifacts`.

## Live And Database Commands

Live Polymarket polling requires network access:

```powershell
& $py -m core.cli.main poll-polymarket-cs --limit 25
```

DB-backed ingestion requires a dedicated Betto Postgres database. After setting `BETTO_DATABASE_URL`, run:

```powershell
& $py -m core.cli.main db-check
& $py -m core.cli.main db-apply-migrations
& $py -m core.cli.main db-ingest-cs-fixture --path tests\fixtures\cs_match_001.json
```

When running inside WSL, the current local Postgres cluster listens on port `5433`:

```bash
source .betto/wsl-venv/bin/activate
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-check
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-apply-migrations
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-ingest-cs-fixture --path tests/fixtures/cs_match_001.json
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-materialize-cs-features --as-of 2026-05-21T00:00:00Z --fixtures tests/fixtures/cs_match_001.json
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-cs-features --limit 10
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-evaluate-cs-baseline --fixtures tests/fixtures/cs_match_001.json --write-artifact
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-model-artifacts --target cs.map_winner
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-walk-forward-cs-baseline --corpus tests/fixtures/corpus --start 2026-01-01 --end 2026-03-31 --train-days 30 --validate-days 20 --step-days 15
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-backtest-runs --strategy-id cs_baseline_fixture_v1
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-paper-evaluate-cs-baseline --corpus tests/fixtures/cs_match_001.json --markets tests/fixtures/cs_market_prices.json --compact
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-recommendations
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-recommendations --passing-only --limit 10
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-log-paper-bets-from-recommendations --strategy-id cs_baseline_fixture_v1 --bankroll-usd 1000
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-settle-paper-bets-from-market-fixtures --markets tests/fixtures/cs_market_prices.json --strategy-id cs_baseline_fixture_v1
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-paper-bets --strategy-id cs_baseline_fixture_v1
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-summarize-paper-bets --strategy-id cs_baseline_fixture_v1
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-summarize-paper-bets-by-day --strategy-id cs_baseline_fixture_v1 --limit 10
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-check-paper-bet-readiness --strategy-id cs_baseline_fixture_v1 --min-settled-bets 1 --min-roi 0 --min-hit-rate 0 --min-mean-clv 0 --min-pnl-usd 0 --max-drawdown-usd 1000
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-report-cs-baseline-strategy --corpus tests/fixtures/corpus --markets tests/fixtures/market_corpus --compact
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-report-artifacts
```

## Shape

- `core/`: reusable ingestion, raw storage, entities, markets, features, backtesting, risk, and monitoring.
- `sports/cs/`: Counter-Strike adapters, normalizers, features, simulation, and strategies.
- `infra/migrations/`: database migration SQL.
- `docs/`: product and implementation planning.
