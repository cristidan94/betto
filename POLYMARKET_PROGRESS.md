# Polymarket CS2 Integration — Progress

## Completed

### Phase 1: Enhanced Polymarket Scraping & Data Extraction
- [x] **1a. Enrich Gamma API data extraction** — Added `PolymarketMarketMeta` dataclass with volume, liquidity, outcome prices, lifecycle state, event grouping, spread, description. Updated `parse_gamma_market()` to populate all fields. Tests pass.
  - `sports/cs/ingestion/polymarket.py`
  - `tests/test_polymarket_ingestion.py` (5 tests)

- [x] **1b. Link Polymarket markets to HLTV matches** — Built fuzzy team name matcher that extracts teams from Polymarket question text and links to known contests via display name + alias matching. Confidence scoring with date proximity boost.
  - `sports/cs/normalization/polymarket_linker.py` (new)
  - `tests/test_polymarket_linker.py` (8 tests)

- [x] **1c. Automated Polymarket polling loop** — Two new CLI commands: `poll-polymarket-cs-loop` (filesystem) and `db-ingest-polymarket-cs-loop` (Postgres). Paginate all markets, configurable interval, SIGINT graceful stop, lifecycle logging.
  - `core/cli/main.py`

- [x] **1d. DB migration for enriched data** — New migration adds `polymarket_meta` JSONB and `description` columns to markets, `orders` table for order tracking, `mode` column on bets table.
  - `infra/migrations/0007_polymarket_enriched.sql`

### Phase 2: Edge Comparison — Polymarket vs OddsAPI
- [x] **2a. Cross-source market matching** — `core/markets/cross_source.py` with `EdgeComparisonRow`, `SourceOdds`, and `build_comparison()` function. Tests pass.
  - `core/markets/cross_source.py` (new)
  - `tests/test_cross_source.py` (2 tests)

- [x] **2b. Edge comparison API models** — Pydantic models for the API response.
  - `api/models/edge_comparison.py` (new)

- [x] **2c. Edge comparison API endpoint** — `GET /api/edge-comparison` router, fixture JSON, DB query via `list_edge_comparison_rows()`.
  - `api/routers/edge_comparison.py` (new)
  - `api/fixtures/edge_comparison.json` (new)
  - `api/data.py` — added `get_edge_comparison()`
  - `core/db/repository.py` — added `list_edge_comparison_rows()`

- [x] **2d. Console screen** — "Edge compare" screen in nav rail (key 9) with table showing match, market type, outcome, model/PM/book probs, edge deltas, volume.
  - `console/src/screens/EdgeComparison.tsx` (new)
  - `console/src/types/edge_comparison.ts` (new)
  - `console/src/components/ConsoleShell.tsx` — added 'edge' screen type
  - `console/src/App.tsx` — added EdgeComparison routing

### Phase 3: Bet Placement on Polymarket
- [x] **3a. Polymarket order client** — `PolymarketOrderClient` with HMAC auth, market orders, limit orders, cancel, list orders, get balance.
  - `sports/cs/ingestion/polymarket_orders.py` (new)

- [x] **3b. Polymarket credentials** — Added 5 new env vars to Settings: API key, secret, passphrase, private key, chain ID. Added `polymarket_credentials_configured` property.
  - `core/config/settings.py`

- [x] **3c-d. Execution service** — `ExecutionService` with paper/live modes, daily cap enforcement, single bet cap, Kelly sizing. Full test coverage.
  - `core/execution/service.py` (new)
  - `core/execution/__init__.py` (new)
  - `tests/test_execution_service.py` (6 tests)

- [x] **3e. CLI commands** — `place-polymarket-bet`, `list-polymarket-orders`, `cancel-polymarket-order` commands added.
  - `core/cli/main.py`

- [x] **3f. Bet placement API endpoints** — `POST /api/bets` and `DELETE /api/bets/{order_id}` wired through `api.data`. `POST /api/bets` accepts mode in either the request body or `?mode=paper|live`.
  - `api/routers/bets.py`
  - `api/data.py`

### Phase 4: Console UI — Mode Toggle & Bet Actions
- [x] **4a. Wire Paper/Live toggle** — Mode is stored in app state, displayed in `ConsoleShell`, passed to every screen, and live mode requires confirmation.
- [x] **4b. API mode parameter** — `POST /api/bets?mode=paper|live` is supported.
- [x] **4c. Bet placement from Recommendation screen** — The screen now loads surfaced recommendations and can place the selected recommendation in the current mode.
- [x] **4d. Bet placement from Today screen** — Per-row bet buttons, detail-panel placement, Bet All, and per-market status messages are wired.
- [x] **4e. Persist Polymarket metadata for execution** — DB polling stores parsed Polymarket metadata and per-outcome token IDs into `markets.polymarket_meta`, so live execution can resolve token IDs from recommendation rows.

## Next Improvements

- [x] Persist API-triggered paper/live executions into `orders` and `bets` in Postgres mode so console button clicks become part of the durable bet log.
- [x] Backfill historical Polymarket CS markets with closed/resolved metadata via `db-backfill-polymarket-cs-closed`.
- [x] Add authenticated Polymarket account order/trade history ingestion via `db-ingest-polymarket-account-history`.
- [x] Add API and console affordances for persisted order state and cancellation via `GET /api/orders` and Bet Log order controls.

## Current Follow-Ups

- [x] Add settlement reconciliation that links `polymarket_trades` to `orders` and closed Gamma market resolutions back to `bets` for realized P&L via `db-reconcile-polymarket-settlements`.
- [x] Add price-history ingestion from Polymarket CLOB `/prices-history` for historical CLV curves where snapshots were missed via `db-ingest-polymarket-price-history`.
- [x] Add a migration repair path if any local database already attempted the earlier `0007` migration before the `orders.bet_id` type fix.
- Consider switching live execution to the official Polymarket SDK for full EIP-712 order signing instead of the current direct REST client.

## Test Summary
Focused verification passing:
- `npm run build` in `console/`
- `python -m unittest tests.test_api tests.test_repository tests.test_cli tests.test_execution_service tests.test_polymarket_ingestion` - 64 tests
- `python -m core.cli.main db-ingest-polymarket-price-history --help`

Full `python -m unittest discover -s tests` currently reaches 239 passing tests and stops on 2 import errors because this Python environment does not have `pytest` installed for two Kaggle ingestion test modules.

## Files Created/Modified

### New Files
- `sports/cs/normalization/polymarket_linker.py`
- `sports/cs/ingestion/polymarket_orders.py`
- `core/markets/cross_source.py`
- `core/execution/__init__.py`
- `core/execution/service.py`
- `api/models/edge_comparison.py`
- `api/routers/edge_comparison.py`
- `api/routers/bets.py`
- `api/fixtures/edge_comparison.json`
- `infra/migrations/0007_polymarket_enriched.sql`
- `infra/migrations/0008_polymarket_account_history.sql`
- `infra/migrations/0009_orders_bet_id_type_repair.sql`
- `infra/migrations/0010_market_snapshot_idempotency.sql`
- `console/src/screens/EdgeComparison.tsx`
- `console/src/types/edge_comparison.ts`
- `tests/test_polymarket_linker.py`
- `tests/test_cross_source.py`
- `tests/test_execution_service.py`

### Modified Files
- `sports/cs/ingestion/polymarket.py` - enriched meta extraction and CLOB price-history parsing/client
- `sports/cs/ingestion/__init__.py` — new exports
- `sports/cs/normalization/__init__.py` — new exports
- `core/config/settings.py` — Polymarket credentials with safe defaults
- `core/markets/__init__.py` — cross-source exports
- `core/db/repository.py` - edge comparison query, Polymarket metadata persistence, durable execution bets/orders, account-history upserts, trade/order reconciliation, Gamma-resolution bet settlement, and price-history token lookup
- `core/cli/main.py` - new commands (loop, bet placement, closed-market backfill, account-history ingestion, settlement reconciliation, price-history ingestion) and DB metadata persistence
- `api/main.py` — new routers
- `api/data.py` — edge comparison data function and bet execution bridge
- `api/routers/bets.py` — bet placement/cancel endpoints and order listing
- `api/models/today.py` — recommendation outcome/token fields
- `console/src/components/ConsoleShell.tsx` — edge screen and Paper/Live mode control
- `console/src/App.tsx` — edge screen routing and mode state
- `console/src/api.ts` — bet placement and cancel client helpers
- `console/src/screens/Today.tsx` — per-row/detail/Bet All placement actions
- `console/src/screens/Recommendation.tsx` — placement action for surfaced recommendations
- `console/src/screens/BetLog.tsx` — persisted order state and cancel controls
- `console/src/screens/*.tsx` — mode prop pass-through
- `console/src/types/today.ts` — recommendation outcome/token fields
- `sports/cs/ingestion/polymarket_orders.py` — authenticated order/trade history requests
- `tests/test_repository.py` - metadata, execution persistence, account-history, and price-history token coverage
- `tests/test_polymarket_ingestion.py` - enriched test data and CLOB price-history coverage
