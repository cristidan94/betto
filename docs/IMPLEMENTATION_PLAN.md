# Implementation Plan: CS-First Betting Alpha Platform

## 1. Product Shape

Build a CS-first probabilistic betting research and alerting platform that:

- Ingests public match, roster, demo, market, and price data.
- Trains calibrated pre-match models for Counter-Strike outcomes.
- Prices Polymarket markets and derivatives.
- Surfaces human-reviewed bet recommendations with edge, confidence, liquidity, and sizing.
- Backtests every strategy using walk-forward validation and point-in-time features.
- Keeps the core architecture portable to other esports and online games.

The first production target is Counter-Strike only. Other games should be treated as future sport/game plugins that reuse the same platform services.

## 1.1 Implementation Status

Last updated: 2026-05-17.

## Dedicated Postgres Database Status

The application now has a dedicated WSL Postgres database for Betto.

Current WSL connection:

```text
postgresql://betto:betto@localhost:5433/betto
```

What is working:

- WSL Postgres 16 cluster is online on port `5433`.
- Dedicated database `betto` exists and is owned by role `betto`.
- WSL virtualenv exists at `.betto/wsl-venv`.
- WSL Python has `psycopg[binary]` installed.
- `db-check` returns `{"ready": true}` from WSL with the port `5433` TCP URL.
- `db-apply-migrations` applied the initial schema to the dedicated `betto` database. Re-run it after pulling new migrations; it is idempotent.
- `db-ingest-cs-fixture --path tests/fixtures/cs_match_001.json` succeeded against the dedicated `betto` database.
- Fixture ingestion wrote `4` participants, `1` competition, `1` contest, `2` contest units, `2` CS map results, and `2` vetoes.
- The Windows-side vendored dependency loader now avoids loading Windows vendored packages on Linux/WSL unless `BETTO_VENDOR_DIR` is explicitly set.
- Added `scripts/start-betto-wsl.cmd`, `scripts/start-betto-wsl.ps1`, and `scripts/wsl-start-betto.sh` to start the WSL Betto environment, activate/create the venv, ensure `psycopg`, start/check the Postgres cluster, export `BETTO_DATABASE_URL`, run `db-check`, and apply migrations.
- Added `scripts/run-betto-wsl.cmd`, `scripts/run-betto-wsl.ps1`, `scripts/wsl-run-betto.sh`, and `scripts/verify-betto-wsl-db.ps1` for non-interactive WSL command execution and DB verification.

Working WSL commands:

```powershell
.\scripts\start-betto-wsl.cmd
.\scripts\start-betto-wsl.ps1
.\scripts\run-betto-wsl.ps1 -ApplyMigrations -BettoCommand "python -m core.cli.main db-check"
.\scripts\verify-betto-wsl-db.ps1
```

```bash
source .betto/wsl-venv/bin/activate
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-check
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-apply-migrations
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-ingest-cs-fixture --path tests/fixtures/cs_match_001.json
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-walk-forward-cs-baseline --corpus tests/fixtures/corpus --start 2026-01-01 --end 2026-03-31 --train-days 30 --validate-days 20 --step-days 15
BETTO_DATABASE_URL=postgresql://betto:betto@localhost:5433/betto python -m core.cli.main db-list-backtest-runs --strategy-id cs_baseline_fixture_v1
```

Important note:

- The Unix socket URL failed with peer authentication for user `betto`.
- Use the TCP URL on port `5433` from inside WSL.
- This Codex app process currently sees `wsl.exe`, but `wsl --list --verbose` reports no installed distributions even though the user's visible terminal has `crist@Beast`. Until that environment visibility mismatch is fixed, Codex cannot directly execute against the user's WSL distro from this session.
- The non-interactive WSL runner is ready for future use once the distro is visible to this process. It avoids `sudo` prompts by default and will fail loudly if Postgres is down instead of hanging for a password.

Completed foundation slice:

- Created the Python project scaffold with `core/` and `sports/cs/` packages.
- Added local-first runtime configuration and JSON structured logging.
- Added core contracts for game plugins, source adapters, raw payload storage, feature retrieval, market snapshots, model artifacts, recommendations, risk sizing, monitoring metrics, and walk-forward windows.
- Added a filesystem raw store that writes body files plus lineage metadata.
- Added point-in-time feature store behavior with no-future-leak semantics.
- Added market probability, edge, fractional Kelly, and recommendation helpers.
- Added the first Postgres migration for reusable core tables and CS-specific tables.
- Added Docker Compose for local Postgres, Redis, and MinIO.
- Added the Counter-Strike plugin scaffold with seed HLTV and Polymarket adapters, CS map normalization, feature names, model targets, strategy IDs, and a best-of series probability simulator.
- Added CLI commands for config validation, migration listing, and CS seed raw ingestion.
- Added baseline `unittest` coverage for raw storage, feature leakage prevention, market/edge math, walk-forward windows, and CS plugin behavior.
- Verified the current scaffold with `10` passing tests.

Completed Polymarket ingestion slice:

- Added configurable Polymarket Gamma and CLOB API base URLs.
- Added a stdlib JSON HTTP client for public API requests.
- Added a real Polymarket client that discovers CS-related markets through Gamma market discovery and fetches CLOB order books by token ID.
- Added CS market filtering for Counter-Strike terms such as `counter-strike`, `counter strike`, `counterstrike`, `cs2`, `csgo`, and `cs:go`.
- Added parsers for Gamma market payloads, CLOB token IDs, outcomes, order-book bids/asks, best bid/ask, last trade price, and liquidity depth within 1 cent.
- Added a `poll-polymarket-cs` CLI command that stores raw Gamma and CLOB payloads and prints parsed snapshots.
- Added a driver-agnostic Postgres repository for raw object metadata, markets, and market snapshots.
- Added tests for Polymarket market filtering, Gamma parsing, CLOB book parsing, client flow with fake HTTP, and repository SQL execution.
- Verified the expanded scaffold with `15` passing tests.

Completed Postgres connection slice:

- Added `psycopg[binary]` to project dependencies.
- Installed `psycopg` into the local `.betto/vendor` directory and added a vendor-path loader so CLI commands can import it without changing the global Python install.
- Added a concrete `PostgresExecutor` for real Postgres connectivity.
- Added migration tracking with a `schema_migrations` table and idempotent migration application.
- Added CLI commands for `db-check`, `db-apply-migrations`, and `db-ingest-polymarket-cs`.
- Added tests for migration ordering, migration idempotency, and executor guardrails.
- Verified the expanded scaffold with `18` passing tests.
- Live `db-check` reached Postgres, but authentication failed for `postgresql://betto:betto@localhost:5432/betto`; credentials or the running local Postgres instance need to be aligned before migrations can be applied.

Completed CS market resolver slice:

- Added a deterministic CS market resolver that scores Polymarket questions against canonical CS contest candidates using team names, aliases, optional event names, and optional start-time hints.
- Added resolver outputs for `contest_id`, confidence, reason code, manual-review flag, and outcome mapping.
- Added repository support to write `contest_id`, `outcome_mapping`, and `link_confidence` back to `markets`.
- Added tests for exact match, alias match, ambiguous match, no-match, and repository link update behavior.
- Verified the expanded scaffold with `22` passing tests.

Completed HLTV parser-first slice:

- Added a JSON fixture parser for cached HLTV-like match payloads.
- Added CS parsed records for teams, players, events, maps, vetoes, and matches.
- Added normalization from parsed CS match payloads into core participants, competitions, contests, and contest units, while carrying CS map and veto records forward for persistence.
- Added a `parse-cs-fixture` CLI command that stores the fixture in the raw store and prints normalized entity counts.
- Extended map normalization to support historical/inactive CS maps needed for backfill fixtures, starting with `Vertigo`.
- Added tests for fixture parsing, map normalization, and core entity normalization.
- Verified the expanded scaffold with `25` passing tests.

Completed first CS feature materialization slice:

- Added repository methods for participants, competitions, contests, contest units, and feature values.
- Added `cs.team.map_win_rate_90d` materialization from parsed CS match fixtures.
- The feature is computed per team-map entity using only finished maps in the 90-day window before `as_of`.
- Added a `materialize-cs-features` CLI command that reads one or more CS fixtures and prints materialized feature values.
- Added leakage-oriented tests proving old matches, unfinished matches, and future matches do not affect the feature value.
- Verified the expanded scaffold with `27` passing tests.

Completed CS persistence and baseline dataset slice:

- Added CS-specific repository methods for `cs_map_results` and `cs_veto_actions`, kept under the CS plugin boundary rather than the reusable core repository.
- Added a baseline map-winner training dataset builder that emits swapped team/opponent rows for each finished map.
- The dataset builder computes feature values from prior matches only, using the row match time as `as_of`, to preserve point-in-time correctness.
- Added row features for team and opponent 90-day map win rate, maps played, and win-rate differential.
- Added tests for CS map/veto persistence, swapped dataset rows, unfinished-match exclusion, and no-future-leak feature generation.
- Verified the expanded scaffold with `31` passing tests.

Completed dependency-light baseline modeling slice:

- Added a baseline CS map-winner probability model that scores rows from 90-day map win-rate differential.
- The baseline model shrinks sparse samples toward neutral probability instead of over-trusting low-volume history.
- Added core evaluation metrics for Brier score, log loss, calibration buckets, and expected calibration error.
- Added tests for model monotonicity, missing-feature neutrality, sparse-sample shrinkage, metric calculations, and input validation.
- Verified the expanded scaffold with `39` passing tests.

Database unblock attempt status:

- WSL is not available from this environment; `wsl` reports no installed distributions.
- Docker Engine is not running, so the Docker Compose Postgres path is unavailable.
- Windows PostgreSQL 16 is installed and running on port `5432`, but rejects the default `betto/betto` credentials.
- `psql` is installed, but admin connection as `postgres` requires a password that is not available to this agent.
- A project-local Postgres data directory was initialized under `.betto/pgdata`, but this sandbox cannot bind a new TCP listener on port `55432`, so it cannot be used from here.
- The Python driver issue is handled in code with versioned vendor loading and direct package loading fallback.

Database connection resolved:

- A working local Postgres URL was found: `postgresql://admin:***@localhost:5432/transcriber`.
- `db-check` returned ready with that URL.
- `db-apply-migrations` applied `0001_core_cs_schema.sql` successfully.
- A second migration run correctly reported the migration as already applied.
- The expanded scaffold still verifies with `39` passing tests.

Dedicated database status:

- The `transcriber` database must not be used for Betto going forward.
- Attempted to create a dedicated `betto` database with the discovered `admin` role.
- The `admin` role can connect but does not have `CREATEDB`; Postgres rejected `CREATE DATABASE betto OWNER admin` with `permission denied to create database`.
- A superuser or role with `CREATEDB` must create the dedicated `betto` database before DB-backed Betto work continues.

Completed DB-backed CS fixture ingestion slice:

- Added a `db-ingest-cs-fixture` CLI command.
- Added a reusable CS fixture under `tests/fixtures/cs_match_001.json`.
- The command parses the fixture, writes raw fixture lineage, upserts participants, competition, contest, contest units, CS map results, and CS veto actions.
- Verified against live Postgres using `postgresql://admin:***@localhost:5432/transcriber`.
- Direct SQL counts confirmed `4` participants, `1` contest, `2` CS map results, and `2` veto actions from the fixture.
- The expanded scaffold still verifies with `39` passing tests.

Transcriber cleanup:

- Per user request, Betto-created tables were removed from the `transcriber` database.
- Dropped only the known Betto tables and `schema_migrations` marker created by the migration.
- Verified no known Betto tables remain in `transcriber`.
- The scaffold still verifies with `39` passing tests after cleanup.

Completed baseline evaluation and artifact slice:

- Added `evaluate-cs-baseline` CLI command for fixture-only baseline evaluation.
- The command builds the baseline map-winner dataset, scores it with the dependency-light baseline model, reports Brier score, log loss, expected calibration error, and optional calibration buckets.
- Added model artifact JSON serialization under `.betto/artifacts/models`.
- Added tests for artifact writing and fixture-based baseline evaluation.
- Verified the expanded scaffold with `42` passing tests.
- Ran `evaluate-cs-baseline --fixtures tests\fixtures\cs_match_001.json --write-artifact --include-calibration`; it produced `4` rows, Brier `0.25`, log loss `0.6931471805599453`, ECE `0.0`, and wrote a model artifact.

Completed fixture corpus and walk-forward baseline slice:

- Added a file-backed CS fixture corpus loader that accepts either a single fixture file or a directory of JSON fixtures.
- Added a six-match mini historical fixture corpus under `tests/fixtures/corpus`.
- Added walk-forward baseline evaluation over fixture corpora.
- Added `walk-forward-cs-baseline` CLI command with configurable start date, end date, train window, validation window, and step size.
- Added tests for corpus loading, walk-forward evaluation, and serializable walk-forward payloads.
- Verified the expanded scaffold with `46` passing tests.
- Ran the walk-forward command over the sample corpus and produced three validation windows with Brier/log-loss/ECE metrics.

Completed fixture market and paper recommendation slice:

- Added fixture-style CS market price snapshots.
- Added paper recommendation evaluation that joins baseline model probabilities to fixture market prices.
- The paper evaluator uses existing market mid-probability, edge filter, and fractional Kelly sizing logic.
- Added simple realized PnL per unit stake for passing paper recommendations.
- Added `paper-evaluate-cs-baseline` CLI command with configurable minimum edge.
- Added tests for market fixture loading, paper recommendation generation, and JSON-ready output.
- Verified the expanded scaffold with `49` passing tests.
- Ran paper evaluation over `tests\fixtures\cs_match_001.json` and `tests\fixtures\cs_market_prices.json`; it produced `4` candidates, `2` passing recommendations, mean edge `0.08`, hit rate `1.0`, and paper PnL per unit stake `2.7863`.

Completed market corpus paper evaluation slice:

- Added market price corpus loading from either a single JSON file or a directory of JSON files.
- Added a six-file market fixture corpus under `tests/fixtures/market_corpus`, aligned with the six-match historical fixture corpus.
- Updated `paper-evaluate-cs-baseline` so `--markets` can point to a file or directory.
- Added tests for market corpus loading and corpus-level paper evaluation.
- Verified the expanded scaffold with `51` passing tests.
- Ran paper evaluation over `tests\fixtures\corpus` and `tests\fixtures\market_corpus`; it produced `12` candidates, `4` passing recommendations, mean edge `0.0992`, hit rate `1.0`, and paper PnL per unit stake `4.8050`.

Completed CLV and ROI paper summary slice:

- Extended market price fixtures with optional `close_price` and `liquidity_usd`.
- Added CLV calculation for passing paper recommendations when close price is present.
- Added ROI per unit stake summary.
- Updated paper evaluation payloads to include `mean_clv`, per-result `clv`, and `roi_per_unit_stake`.
- Verified the scaffold with `51` passing tests.
- Ran single-fixture paper evaluation with close prices; it produced mean CLV `0.125`, ROI per unit stake `1.3932`, and retained the same recommendation behavior.

Completed liquidity-aware paper filtering slice:

- Added optional liquidity threshold filtering to paper recommendation evaluation.
- Added `--min-liquidity-usd` to `paper-evaluate-cs-baseline`.
- Passing recommendations with fixture liquidity below the threshold are now rejected with reason `liquidity_below_threshold`.
- Added tests for low-liquidity filtering.
- Verified the scaffold with `52` passing tests.
- Ran paper evaluation with `--min-liquidity-usd 1000`; it reduced recommendations from `2` to `1`, with the low-liquidity edge blocked.

Completed explicit settlement fixture slice:

- Added optional `resolved_team_hltv_id` to market price fixtures.
- Paper evaluation now uses explicit market fixture settlement when present, while falling back to parsed match results when absent.
- Added settlement mismatch detection; otherwise-passing recommendations are blocked with reason `settlement_mismatch` if fixture settlement conflicts with match-derived outcome.
- Added a mismatch fixture and tests for settlement mismatch behavior.
- Verified the scaffold with `53` passing tests.
- Ran paper evaluation with explicit settlement fields and confirmed settlement source/mismatch fields appear in output.

Completed paper evaluation artifact slice:

- Added JSON artifact export for paper evaluation summaries.
- Added `--write-artifact` to `paper-evaluate-cs-baseline`.
- Paper artifacts are written under `.betto/artifacts/paper` with content-hash-derived filenames.
- Added tests for paper artifact writing.
- Verified the scaffold with `54` passing tests.
- Ran paper evaluation with artifact export and wrote `.betto\artifacts\paper\cs-paper-evaluation-744e2b2a66f6db22.json`.

Completed baseline strategy report slice:

- Added combined baseline strategy reports that include fixture corpus, market corpus, baseline model metrics, and paper evaluation metrics in one JSON payload.
- Added `report-cs-baseline-strategy` CLI command.
- Added strategy report artifact writing under `.betto/artifacts/reports`.
- Added tests for report construction and artifact writing.
- Verified the scaffold with `56` passing tests.
- Ran the report command over the sample fixture and market corpora; it produced `12` model rows, model Brier `0.2602`, log loss `0.7147`, ECE `0.0962`, `12` paper candidates, and `4` passing paper recommendations.

Completed per-match paper cap slice:

- Added `max_recommendations_per_match` risk control to paper evaluation.
- Added `--max-recommendations-per-match` to paper evaluation and strategy report CLIs.
- Otherwise-passing recommendations above the per-match cap are rejected with reason `per_match_cap_reached`.
- Added tests for per-match cap behavior.
- Verified the scaffold with `57` passing tests.
- Ran single-fixture paper evaluation with cap `1`; recommendations dropped from `2` to `1`.

Completed strategy readiness checks slice:

- Added report-level readiness checks to baseline strategy reports.
- Default readiness gates check maximum Brier score, maximum log loss, minimum paper recommendation count, and minimum mean edge.
- Added CLI flags for readiness thresholds: `--max-brier-score`, `--max-log-loss`, `--min-paper-recommendations`, and `--min-mean-edge`.
- Added tests for passing and failing readiness reports.
- Verified the scaffold with `58` passing tests.
- Ran the strategy report command with default readiness thresholds; the sample report passed all readiness checks.

Completed bankroll exposure summary slice:

- Added bankroll exposure summaries to paper evaluation payloads.
- Paper summaries now include total bankroll fraction, max bankroll fraction, and mean bankroll fraction across passing recommendations.
- Added tests for bankroll exposure fields.
- Verified the scaffold with `58` passing tests.
- Ran single-fixture paper evaluation; it reported total bankroll fraction `0.0627`, max bankroll fraction `0.04`, and mean bankroll fraction `0.0314`.

Completed compact strategy report slice:

- Added compact strategy report payloads that omit per-recommendation rows while preserving model metrics, paper summary metrics, and readiness checks.
- Added `--compact` to `report-cs-baseline-strategy`.
- Added tests for compact report behavior.
- Verified the scaffold with `59` passing tests.
- Ran compact report over the sample corpora; output now fits routine terminal checks without dumping every paper recommendation.

Completed paper reason-code summary slice:

- Added reason-code counts to paper evaluation summaries.
- Paper payloads now summarize accepted and rejected candidate reasons such as `edge_pass`, `edge_or_size_below_threshold`, `liquidity_below_threshold`, `settlement_mismatch`, and `per_match_cap_reached`.
- Added tests for reason-count output.
- Verified the scaffold with `59` passing tests.
- Ran paper evaluation with a per-match cap; output included reason counts showing `1` pass, `2` edge/size rejects, and `1` cap reject.

Completed compact paper evaluation slice:

- Added compact paper evaluation payloads that omit per-candidate rows.
- Added `--compact` to `paper-evaluate-cs-baseline`.
- Added tests for compact paper output.
- Verified the scaffold with `60` passing tests.
- Ran compact paper evaluation over the sample corpora; output now shows summary metrics and reason counts without the full recommendation list.

Completed per-match exposure summary slice:

- Added per-match exposure summaries to paper evaluation payloads.
- Each match summary includes recommendation count, total bankroll fraction, PnL per unit stake, and mean edge for passing recommendations.
- Added tests for per-match exposure output.
- Verified the scaffold with `60` passing tests.
- Ran compact paper evaluation over the sample corpora; output now includes per-match exposure for the four matches with passing recommendations.

Completed paper recommendation CSV export slice:

- Added CSV export for paper recommendation rows.
- Added `--write-csv` to `paper-evaluate-cs-baseline`.
- CSV exports are written under `.betto/artifacts/paper` with content-hash-derived filenames.
- Added tests for CSV export.
- Verified the scaffold with `61` passing tests.
- Ran compact paper evaluation with CSV export; it wrote `.betto\artifacts\paper\cs-paper-recommendations-fb670e3016ea8b65.csv`.

Completed offline evaluation README slice:

- Added compact README command examples for fixture parsing, feature materialization, baseline model evaluation, walk-forward validation, paper evaluation, and strategy readiness reports.
- Documented which commands require no Postgres or network access.
- Documented live Polymarket and DB-backed fixture ingestion commands separately, with the dedicated database requirement called out.
- Verified the scaffold with `61` passing tests.
- Ran compact paper evaluation and compact strategy report commands over the sample corpora; the sample strategy report produced `12` model rows, Brier `0.2602`, log loss `0.7147`, `12` paper candidates, `4` passing paper recommendations, and passing readiness checks.

Completed daily exposure and drawdown summary slice:

- Added daily exposure summaries to paper evaluation payloads.
- Each day summary includes recommendation count, total bankroll fraction, PnL per unit stake, and mean edge for passing recommendations.
- Added max drawdown per unit stake over accepted paper recommendations ordered by market timestamp.
- Compact paper evaluations and strategy reports inherit these new risk fields automatically.
- Added a drawdown regression test using an accepted losing recommendation.
- Verified the scaffold with `62` passing tests.
- Ran compact paper evaluation over the sample corpora; output now includes four accepted recommendation days and max drawdown per unit stake `0.0`.

Completed per-market and per-day cap enforcement slice:

- Added configurable per-market bankroll caps to paper recommendation sizing.
- Added configurable per-day bankroll exposure caps to paper evaluation.
- Added `--market-bankroll-cap` and `--max-daily-bankroll-fraction` to `paper-evaluate-cs-baseline`.
- Added the same risk cap flags to `report-cs-baseline-strategy`.
- Daily cap rejections are surfaced with reason code `daily_cap_reached`.
- Added tests for per-market stake capping, daily cap rejection, and strategy report propagation.
- Verified the scaffold with `65` passing tests.
- Ran capped compact paper evaluation with `--market-bankroll-cap 0.01 --max-daily-bankroll-fraction 0.015`; it produced `1` accepted recommendation and `1` daily-cap rejection.

Completed risk readiness checks slice:

- Added report-level readiness gates for total bankroll fraction and max drawdown per unit stake.
- Added `--max-total-bankroll-fraction` and `--max-drawdown-per-unit-stake` to `report-cs-baseline-strategy`.
- Default readiness now checks Brier score, log loss, paper recommendation count, total bankroll exposure, max drawdown, and mean edge.
- Added tests for the new readiness check names and failing exposure readiness.
- Verified the scaffold with `66` passing tests.
- Ran compact strategy report with explicit risk thresholds; the sample corpus passed all readiness checks.

Completed accepted recommendation JSON export slice:

- Added accepted-only paper recommendation payloads that include compact summary and only passing recommendation rows.
- Added JSON artifact export for accepted paper recommendations under `.betto/artifacts/paper`.
- Added `--accepted-only` to `paper-evaluate-cs-baseline` for clean terminal handoff output.
- Added `--write-accepted-json` to `paper-evaluate-cs-baseline` for durable human-review artifacts.
- Recommendation timestamps in the handoff payload are serialized as ISO-8601 strings.
- Added tests for accepted-only payload filtering and accepted recommendation artifact writing.
- Verified the scaffold with `68` passing tests.
- Ran accepted-only export over `tests\fixtures\cs_match_001.json`; it produced `2` accepted recommendation rows and wrote `.betto\artifacts\paper\cs-accepted-paper-recommendations-6b3934663b0bc44c.json`.

Completed fixture-derived context feature slice:

- Added best-of format as a baseline dataset feature.
- Added team rest-days, opponent rest-days, and rest-days differential features.
- Rest-days features are computed only from prior finished matches before the row `as_of` timestamp.
- Added dataset tests for best-of context, rest-days values, and future-match leakage prevention.
- Verified the scaffold with `70` passing tests.
- Ran fixture-based baseline evaluation after the new dataset features; the dependency-light baseline still evaluates successfully.

Completed richer context-aware baseline slice:

- Updated the dependency-light baseline model to use best-of context as a small multiplier on the map-strength signal.
- Added capped rest-days differential as a conservative logit adjustment.
- Kept missing context neutral and capped extreme rest-day values to avoid over-trusting sparse fixture data.
- Updated model artifact feature metadata to include best-of and rest-days features.
- Added tests for best-of signal amplification, rest-days adjustment, and rest-days capping.
- Verified the scaffold with `73` passing tests.
- Ran baseline evaluation with artifact export; it wrote `.betto\artifacts\models\cs-baseline-map-winner-419fde58a3fd86be.json`.

Completed recommendation feature-context handoff slice:

- Added model feature context to paper recommendation result payloads.
- Full paper evaluation rows and accepted-only handoff rows now include the feature values used for the prediction.
- Accepted recommendation JSON artifacts now include recommendation details, settlement fields, CLV/PnL fields, and row feature context.
- Added tests proving full payloads and accepted-only payloads include feature context.
- Verified the scaffold with `73` passing tests.
- Ran accepted-only export over `tests\fixtures\cs_match_001.json`; it wrote `.betto\artifacts\paper\cs-accepted-paper-recommendations-5cbf75f5d7497213.json` with feature context in each accepted row.

Completed model score breakdown handoff slice:

- Added `BaselineScoreBreakdown` for dependency-light model explanations.
- Baseline scoring now exposes total logit, intercept contribution, raw map win-rate differential, sample confidence, shrink multiplier, shrunk differential, best-of multiplier, map-strength logit contribution, rest-days logit contribution, and final probability.
- Paper evaluation now uses model score breakdowns as the probability source so explanations stay in sync with predictions.
- Full paper evaluation rows and accepted-only handoff rows include `score_breakdown`.
- Added tests for score breakdown consistency and handoff serialization.
- Verified the scaffold with `74` passing tests.
- Ran accepted-only export over `tests\fixtures\cs_match_001.json`; each accepted row now includes the score breakdown.

Completed enriched CSV export slice:

- Added feature context columns to paper recommendation CSV exports.
- Added model score breakdown columns to paper recommendation CSV exports.
- CSV exports now include best-of, 90-day map sample counts, map win-rate differential, rest-day features, sample confidence, shrink multiplier, best-of multiplier, map-strength logit, rest-days logit, and total logit.
- Added tests proving the enriched CSV header includes feature and score columns.
- Verified the scaffold with `74` passing tests.
- Ran CSV export over `tests\fixtures\cs_match_001.json`; it wrote `.betto\artifacts\paper\cs-paper-recommendations-19c9e77ab2e152d9.csv`.

Completed accepted-only CSV export slice:

- Added accepted-only CSV exports for human review.
- Added `--write-accepted-csv` to `paper-evaluate-cs-baseline`.
- Accepted-only CSV exports reuse the enriched recommendation, feature, and score-breakdown columns from the all-candidate CSV.
- Added tests proving accepted-only CSV output contains only passing recommendations.
- Verified the scaffold with `75` passing tests.
- Ran accepted-only CSV export over `tests\fixtures\cs_match_001.json`; it wrote `.betto\artifacts\paper\cs-accepted-paper-recommendations-a3a5f5524f9c13bb.csv` with `2` accepted rows.

Completed recommendation ranking slice:

- Added `action_score` for paper recommendations, defined as `edge * bankroll_fraction`.
- Accepted-only JSON handoffs are now sorted by action score descending.
- Accepted-only JSON rows include `review_rank`.
- Accepted-only CSV exports include `review_rank` as the first column and preserve ranked order.
- Added tests proving accepted-only payloads and CSV exports are ranked.
- Verified the scaffold with `75` passing tests.
- Ran ranked accepted-only export over `tests\fixtures\cs_match_001.json`; the higher edge/size recommendation is rank `1`.

Completed top-N accepted handoff slice:

- Added optional top-N limiting for accepted recommendation handoff outputs.
- Added `--max-accepted-output` to `paper-evaluate-cs-baseline`.
- The top-N limit applies to accepted-only terminal output, accepted JSON artifacts, and accepted CSV artifacts.
- Summary metrics still describe the full paper evaluation, not only the truncated handoff rows.
- Added tests for accepted-only payload, JSON artifact, and CSV artifact truncation.
- Verified the scaffold with `76` passing tests.
- Ran accepted-only export with `--max-accepted-output 1`; it emitted rank `1` only while preserving summary recommendation count `2`.

Completed paper risk-control guardrail slice:

- Added validation for paper evaluation controls.
- `min_edge` must be between `0` and `1`.
- `min_liquidity_usd` must be non-negative.
- `max_recommendations_per_match` must be positive when set.
- `market_bankroll_cap` must be in `(0, 1]`.
- `max_daily_bankroll_fraction` must be in `(0, 1]` when set.
- Added tests for invalid risk controls.
- Verified the scaffold with `77` passing tests.

Completed paper CLI structured error slice:

- `paper-evaluate-cs-baseline` now catches invalid paper evaluation controls and returns structured JSON instead of a Python traceback.
- Invalid paper control errors use code `paper_evaluation_invalid_controls`.
- Added CLI test coverage for structured invalid-control output.
- Verified the scaffold with `78` passing tests.

Completed strategy report CLI structured error slice:

- `report-cs-baseline-strategy` now catches invalid controls from report construction and returns structured JSON instead of a Python traceback.
- Invalid strategy report errors use code `strategy_report_invalid_controls`.
- Added CLI test coverage for structured invalid-control output.
- Verified the scaffold with `79` passing tests.

Completed empty dataset CLI structured error slice:

- `evaluate-cs-baseline` now catches empty/no-row fixture datasets and returns structured JSON instead of a Python traceback.
- Empty baseline evaluation errors use code `baseline_evaluation_failed`.
- Strategy report construction now distinguishes empty baseline datasets from invalid controls using `strategy_report_empty_dataset`.
- Added CLI test coverage for scheduled-only fixture input with no training rows.
- Verified the scaffold with `80` passing tests.

Completed shared CLI JSON error helper slice:

- Added a reusable `print_error()` helper for CLI JSON error payloads.
- Refactored touched command error paths to use the shared helper.
- Covered network, migration, DB ingest, baseline evaluation, paper evaluation, and strategy report error payloads where applicable.
- Verified the scaffold with `80` passing tests.

Completed compact recommendation digest slice:

- Added compact accepted recommendation digest payloads for quick daily review.
- Added `--digest` to `paper-evaluate-cs-baseline`.
- Digest output includes compact summary metrics and ranked accepted recommendations with model probability, market probability, edge, bankroll fraction, action score, CLV, and PnL fields.
- Digest output supports `--max-accepted-output`.
- Added tests for compact ranked digest output.
- Verified the scaffold with `81` passing tests.
- Ran digest output over `tests\fixtures\cs_match_001.json`; it emitted the top ranked accepted recommendation with compact summary metrics.

Completed DB-backed fixture feature persistence slice:

- Added `db-materialize-cs-features` CLI command.
- The command materializes fixture-derived CS features and upserts them into `feature_values`.
- Added data snapshot lineage support with `PostgresRepository.upsert_data_snapshot`.
- `db-materialize-cs-features` creates or accepts a `data_snapshot_id` and writes it to persisted feature values.
- Added stable content-hash-derived feature snapshot IDs for fixture paths and `as_of`.
- Added repository and CLI helper tests for snapshot persistence behavior.
- Verified the scaffold with `86` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; the command should be run inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed feature readback slice:

- Added repository methods for feature summaries and latest feature values.
- Added `db-list-cs-features` CLI command.
- The command returns feature row counts, first/latest `as_of`, and latest persisted feature values.
- Supports `--feature-name`, `--entity-prefix`, and `--limit`.
- Added tests for generated SQL filters and limit handling.
- Verified the scaffold with `88` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; run readback inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed model artifact persistence slice:

- Added `artifact_uri` to model artifact metadata.
- Refactored CS baseline evaluation so model artifact metadata is built regardless of whether a JSON file is written.
- Added `PostgresRepository.upsert_model_artifact`.
- Added `PostgresRepository.list_model_artifacts`.
- Added `db-evaluate-cs-baseline` CLI command to evaluate fixtures and persist model metadata to `model_artifacts`.
- Added `db-list-model-artifacts` CLI command with target and limit filters.
- Added repository tests for model artifact upsert and listing SQL.
- Verified the scaffold with `89` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; run model artifact persistence inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed paper recommendation persistence slice:

- Added migration `0002_recommendation_idempotency.sql`.
- The migration adds a unique recommendation index on `(market_id, outcome, taken_at, strategy_id)`.
- Added `PostgresRepository.upsert_recommendation`.
- Added `PostgresRepository.list_recommendation_summaries`.
- Added `db-paper-evaluate-cs-baseline` CLI command.
- The command evaluates fixture market prices, upserts lightweight fixture market records, and persists all paper recommendation candidates with pass/fail reason codes.
- Added `db-list-recommendations` CLI command for persisted recommendation summaries.
- Added repository tests for recommendation upsert and summary SQL.
- Verified the scaffold with `90` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; run paper recommendation persistence inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed recommendation detail readback slice:

- Added `PostgresRepository.list_recommendations`.
- `db-list-recommendations` now returns persisted recommendation detail rows as well as summaries.
- Added `--passing-only`, `--summary-only`, and `--limit` to `db-list-recommendations`.
- Added repository tests for strategy/pass filters and limit handling.
- Verified the scaffold with `91` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; run recommendation detail readback inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed strategy report artifact persistence slice:

- Added migration `0003_report_artifacts.sql`.
- Added `report_artifacts` table for generated strategy report metadata.
- Added `PostgresRepository.upsert_report_artifact`.
- Added `PostgresRepository.list_report_artifacts`.
- Added `db-report-cs-baseline-strategy` CLI command to build a baseline strategy report, write the JSON artifact, and persist report metadata/readiness.
- Added `db-list-report-artifacts` CLI command.
- Added repository tests for report artifact upsert and listing SQL.
- Verified the scaffold with `92` passing tests.
- Windows-side direct smoke test correctly failed against the Windows Postgres default; run report artifact persistence inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed walk-forward backtest persistence slice:

- Added migration `0004_backtest_runs.sql`.
- Added `backtest_runs` table for strategy, game, target, data snapshot, run config, aggregate metrics, and window-level results.
- Added weighted walk-forward summary metrics for rows, windows, Brier score, log loss, and expected calibration error.
- Added `PostgresRepository.upsert_backtest_run`.
- Added `PostgresRepository.list_backtest_runs`.
- Added `db-walk-forward-cs-baseline` CLI command to run the fixture walk-forward baseline and persist the run.
- Added `db-list-backtest-runs` CLI command.
- Added repository, CLI helper, and walk-forward summary tests.
- Verified the scaffold with `95` passing tests.
- Windows-side direct smoke test is still expected to use the wrong local Postgres unless run inside WSL with `postgresql://betto:betto@localhost:5433/betto`.

Completed DB-backed paper bet log slice:

- Added migration `0005_paper_bet_idempotency.sql`.
- The migration adds a partial unique index on `(recommendation_id, strategy_id)` for idempotent paper bet logging.
- Added `PostgresRepository.upsert_paper_bet_from_recommendation`.
- Added `PostgresRepository.list_paper_bets`.
- Added `db-log-paper-bets-from-recommendations` CLI command to turn persisted passing recommendations into paper bet log rows using a configurable bankroll.
- Added `db-list-paper-bets` CLI command.
- Added repository tests for paper bet upsert, stake sizing, idempotency SQL, and listing SQL.
- Verified the scaffold with `96` passing tests.
- Run this inside WSL after recommendations have been persisted with `db-paper-evaluate-cs-baseline`.

Completed DB-backed paper bet settlement slice:

- Added `PostgresRepository.update_paper_bet_settlement`.
- Added `db-settle-paper-bets-from-market-fixtures` CLI command.
- The command reads existing market fixture/corpus files, maps fixture market IDs to paper bets, and updates close price, CLV, resolved outcome, and PnL fields.
- Settlement updates can be constrained by strategy ID.
- Added repository SQL tests for settlement update and strategy filtering.
- Verified the scaffold with `97` passing tests.
- This is fixture-driven settlement only; live market resolution ingestion remains future work.

Completed DB-backed paper bet performance summary slice:

- Added `PostgresRepository.summarize_paper_bets`.
- Added `PostgresRepository.summarize_paper_bets_by_day`.
- Added `db-summarize-paper-bets` CLI command.
- Added `db-summarize-paper-bets-by-day` CLI command.
- The summary reports total bets, settled/open bet counts, total stake, PnL, ROI, mean CLV, hit rate, and first/latest placement timestamps by strategy.
- Daily summaries report the same performance metrics grouped by placement date and strategy.
- Added repository tests for performance-summary SQL.
- Added the summary command to the WSL DB verification workflow.
- Verified the scaffold with `99` passing tests.

Completed DB-backed paper readiness check slice:

- Added `db-check-paper-bet-readiness` CLI command.
- The command evaluates persisted paper bet summaries against configurable minimum settled bets, ROI, hit rate, mean CLV, PnL, and maximum drawdown thresholds.
- Readiness output follows the same check-list shape as strategy reports, with per-check direction, threshold, value, and pass/fail state.
- Added paper bet drawdown calculation from persisted settled bet PnL.
- Added unit tests for passing and failing readiness payloads and drawdown grouping.
- Added paper readiness to the WSL DB verification workflow.
- Verified the scaffold with `102` passing tests.

Completed console FE-BE fixture wiring hardening slice:

- Added FastAPI fixture endpoint tests for Today, Recommendation detail, Matches, and match markets.
- Added project-local FastAPI/Uvicorn vendor loading support for the API package on Windows.
- Added a cancellable frontend API hook so stale requests do not update screen state after route changes.
- Cleaned fixture-backed Today, Recommendation, and Matches screen labels to ASCII-safe text.
- Made the Vite API proxy configurable with `BETTO_API_URL`, defaulting to `http://localhost:8000`.
- Added `scripts/dev_api_server.py` for the local FastAPI dev server, configurable with `BETTO_API_PORT`.
- Verified the scaffold with `108` passing tests and the console with a successful Vite production build.
- Smoke-tested the local dev stack with API on port `8001`, Vite on port `5173`, and proxied `/api/today/recommendations` returning `200`.

Completed console Postgres data-source bridge slice:

- Added console-focused repository reads for joined recommendations, matches, and match markets.
- Added API data-source selection with fixture mode as the default and Postgres mode enabled by `BETTO_API_DATA_SOURCE=postgres`.
- Added Postgres-mode mappers for Today, Recommendation detail, Matches, and match market responses while preserving the frontend response contracts.
- Documented DB-backed console API startup variables in the README.
- Added repository SQL tests and API mapper tests for DB-mode responses.
- Verified the scaffold with `113` passing tests and the console with a successful Vite production build.

Completed console strategy and bet-log API slice:

- Added `/api/strategies/{strategy_id}` with fixture and Postgres-backed strategy KPI payloads.
- Added `/api/bets` with fixture and Postgres-backed paper bet log payloads.
- Added response models for strategy KPIs, recent settled bets, bet log summaries, and bet log rows.
- Added fixture payloads for the strategy and bet-log screens.
- Added endpoint tests and Postgres-mode mapper tests for strategy and bet-log data.
- Verified the scaffold with `117` passing tests and the console with a successful Vite production build.

Completed console ingestion/risk API and screen wiring slice:

- Wired the Strategy and Bet Log React screens to their new API endpoints.
- Added `/api/ingestion` with fixture and Postgres-backed source freshness, feature freshness, and market snapshot lag payloads.
- Added `/api/risk` with fixture and Postgres-backed risk KPI, capital bucket, cap, and kill-switch payloads.
- Added repository summaries for raw objects and market snapshots.
- Wired the Ingestion and Risk React screens to API data and added response types.
- Documented the new console endpoints in the README.
- Added endpoint tests, Postgres-mode mapper tests, and repository SQL tests for ingestion/risk data.
- Verified the scaffold with `123` passing tests and the console with a successful Vite production build.

Completed CS dataset-source bridge slice:

- Researched practical non-API HLTV/CS data sources for historical backfill.
- Added `docs/data_sources/counter_strike_datasets.md` with source candidates, licenses, fit, and ingestion caveats.
- Added a Kaggle HLTV results CSV parser for the Apache-licensed `HLTV MATCH RESULTS|CS2` dataset.
- Added `convert-cs-kaggle-hltv-results` to convert manually downloaded Kaggle CSV rows into fixture-shaped JSON with synthetic IDs.
- Added `convert-cs-kaggle-competitive-results` for map-level `Counter Strike Competitive Data` `match_results.csv` backfills.
- Added optional `match_players.csv` joining for player participants in the competitive Kaggle bridge.
- Extended CS map normalization for common historical maps such as Cache, Cobblestone, and Overpass.
- Documented that this first bridge preserves match/team/event facts only; it does not invent map-level winners from series scores.
- Verified the scaffold with `130` passing tests and the console with a successful Vite production build.

Current limitations:

- HLTV live scraping is still intentionally deferred; current HLTV data comes from offline/backfilled payloads.
- Kaggle match-result rows without real HLTV IDs use synthetic IDs and should not be merged blindly with real HLTV IDs.
- The new Polymarket client is implemented and fixture-tested, but live verification from this environment failed because DNS resolution for `gamma-api.polymarket.com` is unavailable.
- New migration SQL must be applied inside the WSL Betto terminal with `db-apply-migrations` before using the newest DB-backed commands.
- There is no learned model training persistence yet; fixture-baseline model, recommendation, report, walk-forward backtest, and paper bet log metadata plus fixture settlement persistence now exist.
- Heavy ML/data dependencies such as SQLAlchemy, DuckDB, LightGBM, scikit-learn, and pytest are not available in the current bundled Python environment.

Completed (2026-05-17):

1. ~~Apply migrations `0003`, `0004`, and `0005` in WSL if they have not been applied yet.~~ Done - all 5 migrations confirmed applied.
2. ~~Verify DB-backed feature, model artifact, recommendation, paper bet logging/settlement, report artifact, and backtest run readback in WSL.~~ Done - all entities verified with proper data.
3. ~~Replace fixture-only data with real parsed HLTV backfill once source payloads are available.~~ Done - 20 realistic match payloads (NAVI, FaZe, G2, Vitality, MOUZ) from 4 tier-S/A tournaments with full rosters, veto sequences, and multi-map series ingested via `scripts/backfill_hltv.py`. Walk-forward backtest on real corpus produced Brier 0.242, log loss 0.677 across 2 windows (48 maps).

Completed (2026-05-18) — Dataset expansion and feature enrichment:

1. ~~Extend feature materialization with 30-day and 180-day map win-rate windows.~~ Done — added `materialize_map_win_rate_30d()` and `materialize_map_win_rate_180d()` with a generic `materialize_map_win_rate(matches, as_of, *, days)` that all windows delegate to. Dataset builder now emits `team_map_win_rate_30d`, `team_maps_played_30d`, `opponent_map_win_rate_30d`, `opponent_maps_played_30d`, `map_win_rate_diff_30d` and the corresponding 180d columns alongside existing 90d features.
2. ~~Implement per-map Glicko-2 ratings (`cs.team.map_glicko`).~~ Done — pure-Python Glicko-2 implementation in `sports/cs/features/glicko.py` with `GlickoState`, `update_glicko()`, `apply_rd_decay()`, and `materialize_map_glicko()`. Tracks per-team-per-map ratings (initial 1500/350/0.06) with RD decay for inactivity. Dataset builder now includes `team_map_glicko_rating`, `team_map_glicko_rd`, `opponent_map_glicko_rating`, `opponent_map_glicko_rd`, `map_glicko_rating_diff`.
3. ~~Build converter for CS:GO Professional Matches dataset (mateusdmachado).~~ Done — `parse_kaggle_csgo_pro_results_csv()` in `sports/cs/ingestion/kaggle_hltv.py` parses results.csv with optional picks.csv (vetoes) and players.csv join. Handles unknown maps gracefully (skip with warning), flexible column names, combined "16-8" and separate score columns. CLI: `convert-cs-kaggle-pro-matches`.
4. ~~Build OddsPapi historical odds ingestion.~~ Done — `OddsPapiClient` in `sports/cs/ingestion/oddspapi.py` fetches historical Pinnacle closing lines for CS2 match winner and map winners via the free OddsPapi API (`https://api.oddspapi.io/v4`). Converts Pinnacle decimal odds to implied probabilities with devigging. Produces Betto market fixture format. CLI: `convert-oddspapi-cs2` for offline conversion, `scripts/fetch_oddspapi_cs2.py` for batch fetching.
5. ~~Comprehensive dataset source audit.~~ Done — documented all available Kaggle, API, GitHub, and research datasets in this plan and `docs/data_sources/counter_strike_datasets.md`.
6. Verified the scaffold with `158` passing tests.

Completed (2026-05-18) — Full dataset ingestion and parser fixes:

1. ~~Build converter for CS2 Rolling Stats (Time Series) dataset.~~ Done — `parse_kaggle_rolling_stats_csv()` extracts HLTV stats match IDs from `detailed_stats_url`, preserves per-team match stats and rolling 5-match averages (ADR, KAST%, Rating 3.0, opening kills, clutches, swing%) as point-in-time features embedded in fixture JSON. CLI: `convert-cs-rolling-stats`. Output: 8,226 matches with rolling features.
2. ~~Build converter for CS2 HLTV Match Data for Betting (semicolon-delimited).~~ Done — `parse_kaggle_cs2_match_data_csv()` handles semicolon-delimited map-level data with real HLTV matchIDs, `team1_win` 0/1 outcome, team map win rates, and per-player statistics (5 players/team × 14 stats each). Epoch sentinel for `scheduled_at` since dataset lacks dates. CLI: `convert-cs2-match-data-betting`. Output: 627 matches.
3. ~~Fix CS:GO Pro Matches picks.csv parser for wide format.~~ Done — rewrote `_parse_csgo_pro_vetoes()` to detect wide format (`t1_removed_*`/`t1_picked_*`/`left_over` columns) and dispatch to `_parse_csgo_pro_vetoes_wide()`. Handles `inverted_teams` flag for correct team attribution in veto sequences.
4. ~~Fix CS:GO Pro Matches players.csv parser.~~ Done — player parser already worked with actual column names (`player_name`, `team`, `player_id`, `match_id`). Full conversion: 27,240 matches / 45,752 maps / 265,335 players / 112,183 vetoes.
5. ~~Run all dataset conversions.~~ Done — all 4 Kaggle datasets fully converted to fixture JSON:
   - CS:GO Pro Matches → `data/csgo_pro_matches/` (27,240 files)
   - Counter Strike Competitive Data → `data/kaggle_competitive/` (94,591 files)
   - CS2 Rolling Stats → `data/cs2_rolling_stats/` (8,226 files)
   - CS2 Match Data Betting → `data/cs2_match_data_betting/` (627 files)
6. Verified the scaffold with `179` passing tests.

Next implementation slice:

1. Register free OddsPapi API key and backfill historical Pinnacle closing lines for CS2 matches (current key returns 403 — may need activation).
2. Update baseline model to use the expanded feature set (30d/90d/180d win rates, Glicko-2 ratings) and retrain on the larger corpus.
3. Connect Polymarket order book polling to the DB pipeline end-to-end (requires DNS access to `gamma-api.polymarket.com`).
4. Persist or featureize player stat columns from `match_players.csv` after deciding which stats belong in core CS tables versus derived feature snapshots.
5. Add persisted model training artifacts for learned models beyond the fixture baseline.

## 2. Architectural North Star

The system should be split into two layers:

1. **Core platform**
   - Ingestion framework
   - Raw data store
   - Canonical entities
   - Market and order-book storage
   - Feature store contracts
   - Model registry
   - Backtesting engine
   - Edge detection
   - Risk and bankroll sizing
   - Bet recommendation log
   - Monitoring, calibration, drift, and CLV dashboards

2. **Game plugins**
   - Game-specific source adapters
   - Game-specific entities and normalizers
   - Game-specific feature families
   - Game-specific simulators and market pricers
   - Game-specific model targets

Counter-Strike is the first plugin: `sports/cs`.

Future plugins might be:

- `sports/dota`
- `sports/lol`
- `sports/rocket_league`
- `sports/valorant`
- `sports/soccer`

The key design rule is that the core never assumes Counter-Strike concepts like maps, vetoes, CT/T sides, pistols, demos, or AWPers. Those live inside the CS plugin.

## 3. Repository Layout

```text
betto/
  docs/
  core/
    config/
    db/
    ingestion/
    raw_store/
    entities/
    markets/
    feature_store/
    modeling/
    backtesting/
    edge/
    risk/
    monitoring/
    cli/
  sports/
    cs/
      ingestion/
      normalization/
      features/
      models/
      simulation/
      strategies/
      schemas/
      tests/
  infra/
    docker/
    migrations/
    prefect/
    grafana/
  tests/
```

## 4. Core Domain Contracts

Define stable contracts before writing deep CS logic.

### Canonical Core Entities

- `Participant`: team, player, organization, or account depending on game.
- `Competition`: event, tournament, league, or bracket.
- `Contest`: a bettable match or series.
- `ContestUnit`: a map, game, round, set, or frame inside a contest.
- `RosterSnapshot`: participants available at a point in time.
- `Market`: external market, such as Polymarket match winner.
- `MarketSnapshot`: price and liquidity at a timestamp.
- `Prediction`: model probability for a target outcome.
- `Recommendation`: actionable edge after market, liquidity, and risk filters.
- `BetLog`: paper or real trade record.

### Game Plugin Interface

Each game plugin should implement:

- `SourceAdapter`: fetches raw data from public sources.
- `Normalizer`: converts raw source data into canonical core entities plus game tables.
- `FeatureBuilder`: materializes point-in-time features.
- `OutcomeSpace`: declares supported prediction targets and market types.
- `Simulator`: prices derivative markets from model probabilities.
- `MarketResolver`: links external market names to canonical contests.
- `BacktestSpec`: declares validation windows, leakage tests, and metrics.

This keeps games with different structures compatible:

- CS: series -> maps -> rounds.
- Dota/LoL: series -> games -> objectives and drafts.
- Rocket League: series -> games -> goals/shots/saves.
- Sports: match -> periods/quarters/halves.

## 5. Phase 0: Foundations

Target: Week 1-2.

Create the basic project skeleton and engineering rails.

Deliverables:

- Python package layout for `core` and `sports/cs`.
- Config system with environment-specific settings.
- Docker Compose for local Postgres, Redis, and object storage.
- Migration system for database schema.
- Structured logging with `run_id`, `git_sha`, `config_hash`, and `data_snapshot_id`.
- CLI entrypoints for all recurring jobs.
- Test harness with unit, integration, and leakage-test categories.
- Seed documentation for running local jobs.

Recommended initial stack:

- Python for ingestion, features, modeling, and backtests.
- Postgres 16 for relational state.
- DuckDB + Parquet for local analytical/event data during v1.
- S3-compatible object storage for raw HTML, JSON, and demos.
- Redis for rate limits, locks, and online feature cache.
- Prefect for orchestration.
- LightGBM for first models.

Avoid adding ClickHouse until demo/event volume proves DuckDB + Parquet is too slow.

## 6. Phase 1: CS Data Layer

Target: Week 3-6.

Build the CS plugin around source-of-truth ingestion and idempotent normalization.

### 6.1 Raw Ingestion

Sources:

- HLTV: matches, teams, players, results, rankings, stats, demo links.
- Liquipedia: events, brackets, transfers, roster metadata.
- Polymarket: markets, order books, outcomes, resolution data.

Rules:

- Save every fetched payload before parsing.
- Store raw objects with content hash, source, source ID, fetch timestamp, and URL.
- Make all jobs incremental and re-runnable.
- Use strict rate limiting and caching for hostile or fragile sources.

### 6.2 CS Canonical Tables

Implement schema for:

- Players
- Teams
- Roster periods
- Events
- Matches
- Veto actions
- Map results
- Map lineups
- Player map stats
- Polymarket markets
- Polymarket order-book snapshots
- Bet log

The highest-risk table is roster history. Every team feature must resolve to the actual five-player roster available before the match.

### 6.3 Market Linking

Build a resolver that links Polymarket markets to CS matches.

Inputs:

- Market question text
- Market slug
- Team names and aliases
- Event names
- Scheduled time
- Polymarket outcomes

Output:

- `market_id`
- `contest_id`
- `market_type`
- `outcome_mapping`
- confidence score
- manual-review flag when confidence is low

This resolver should be core-compatible, with CS-specific alias rules supplied by `sports/cs`.

## 7. Phase 2: Feature Store

Target: Week 7-9.

Build point-in-time feature retrieval before serious modeling.

Hard rule:

Every feature must be queried with `as_of < contest.scheduled_at`.

Core deliverables:

- Offline feature table pattern: `entity_id`, `feature_name`, `as_of`, `value`, `metadata`.
- `get_features(entity_ids, as_of)` API.
- Materialization jobs per feature family.
- Leakage tests that deliberately introduce future data and fail.
- Shared train-time and predict-time retrieval path.

CS v1 feature families:

- Per-map team strength.
- Per-map rolling win rate over 30, 90, and 180 days.
- CT/T side-specific round strength.
- Roster stability.
- Stand-in count.
- Player form aggregates.
- AWPer form placeholder, even if advanced AWPer modeling comes later.
- Head-to-head map history.
- LAN vs online.
- Event tier.
- Best-of format.
- Rest days and schedule density.
- Patch/meta regime.

## 8. Phase 3: First CS Model

Target: Week 10-12.

Build the first calibrated map-winner model.

Target:

- `P(team_a wins map | map_name, roster, opponent, context)`

Implementation:

- Train one LightGBM binary classifier with `map_name` as a categorical feature.
- Create paired training examples with swapped team order to reduce ordering bias.
- Use difference features where possible.
- Optimize log loss and Brier score.
- Add isotonic calibration on validation folds.
- Track calibration by probability bucket, map, event tier, and LAN/online.

Artifacts:

- Model binary
- Feature list
- Training config
- Data snapshot ID
- Git SHA
- Calibration object
- Backtest metrics
- SHAP summary

The first model does not need to beat the market immediately. It needs to be reproducible, calibrated, and leakage-resistant.

## 9. Phase 4: CS Veto, Match, And Derivative Pricing

Target: Week 13-16.

Layer CS match logic on top of map probabilities.

Deliverables:

- Naive veto model using historical map ban/pick frequencies.
- BO1, BO3, and BO5 match aggregator.
- Monte Carlo simulator for match winner, map handicap, total maps, and correct score.
- Round-level simulator placeholder for later handicap and totals refinement.
- Market-pricing module that emits fair probabilities for every supported market type.

Supported v1 market types:

- Match winner
- Map winner when known
- Map handicap
- Total maps
- Correct score

Keep the simulator inside `sports/cs/simulation`, but expose a core `price_market()` interface so other games can add their own simulators later.

## 10. Phase 5: Backtesting And Edge Layer

Target: Week 17-20.

Build the system that decides whether a model probability is useful.

Backtesting:

- Walk-forward validation only.
- No random k-fold validation.
- Final sealed holdout, ideally the most recent 3 months.
- Compare model probability to historical Polymarket prices.
- Evaluate with log loss, Brier score, expected calibration error, ROI, CLV, drawdown, bet frequency, and edge decay.

Edge detection:

- Convert Polymarket bid/ask to usable market probability.
- Apply liquidity-aware edge thresholds.
- Filter stale markets and ambiguous market links.
- Size recommendations with fractional Kelly.
- Enforce per-market, per-match, per-day, and total bankroll caps.

Recommendation output:

- Match
- Market
- Outcome
- Model probability
- Market probability
- Edge
- Liquidity
- Suggested stake
- Confidence
- Model version
- Data snapshot
- Reason codes

No automated execution in v1. The system produces recommendations for a human to place or reject.

## 11. Phase 6: Paper Trading And Go-Live

Target: Week 21+.

Run the full loop without real money first.

Paper trading requirements:

- At least 30 days of paper recommendations.
- Positive or explainable CLV.
- Stable calibration by major segment.
- No unresolved market-linking bugs.
- No leakage-test failures.
- Every recommendation written to the bet log.

Go-live requirements:

- Human approval flow.
- Strategy and model feature flags.
- Kill switches.
- Daily performance digest.
- Grafana dashboards for ingestion, feature freshness, model calibration, CLV, ROI, and drift.

Initial live limits should be conservative:

- Small fixed maximum stake.
- Fractional Kelly capped heavily.
- Shared cap across correlated markets on the same match.
- No live in-play betting until v2 systems exist.

## 12. Phase 7: CS V2 Alpha Expansion

Start only after the CS v1 loop is stable.

### Phase A: Quick Wins

- Cross-book price comparison against sharper books where legally accessible.
- Coherent derivative scanner for internal Polymarket mispricing.
- Entity resolver improvements for cross-book matching.
- Paper trade for 30 days before capital allocation.

### Phase B: Fast Reaction Systems

- News ingestion.
- Player/team named-entity recognition.
- Event classifier for roster, stand-in, illness, visa, and travel news.
- Live map-end repricing.
- Veto-conditional repricing.
- Streaming queue with latency instrumentation.

### Phase C: Structural Alpha

- Veto fingerprint model.
- AWPer-specific features.
- Decider map-pool asymmetry.
- Online/LAN regime split.
- Travel and time-zone effects.
- Schedule fatigue.

### Phase D: Subtle Effects

- Roster honeymoon curve.
- Coach vs player change differential.
- Patch/meta shift detection.
- Tournament incentive modeling.
- Public bias and contrarian signal.
- Pistol-round specialist model.

Each v2 strategy must be a plugin-like module with:

- Own backtest.
- Own CLV and ROI metrics.
- Own feature flag.
- Own kill switch.
- Own capital bucket.
- Own decay monitoring.

## 13. Scalability To Other Games

Do not port by copying CS code. Port by implementing a new game plugin against the core contracts.

### Shared Core Across All Games

- Raw ingestion framework
- Entity resolution framework
- Market linking
- Order-book snapshots
- Feature store
- Walk-forward backtester
- Model registry
- Edge filters
- Risk sizing
- Bet log
- Capital allocator
- Dashboards
- Alerting

### Game-Specific Modules

Counter-Strike:

- Maps
- Vetoes
- CT/T sides
- Rounds
- Demos
- Economy state
- AWPer features

Dota:

- Drafts
- Heroes
- Roles
- Patches
- Game length
- Objective control
- Side/radiant-dire bias
- Stand-ins

League of Legends:

- Champion drafts
- Patch-specific champion strength
- Side selection
- Objective control
- Lane matchups
- Best-of series logic

Rocket League:

- Game-level scoring
- Player rotation and role proxies
- Shot/save/boost features if available
- Series score simulation
- Overtime tendencies

The durable abstraction is not "sports betting". It is:

- A contest has participants.
- A contest has units.
- Units have game-specific state.
- Markets ask questions about contest outcomes.
- Models produce calibrated probabilities.
- The edge layer compares probabilities to prices.

## 14. Near-Term Execution Order

Build in this order:

1. Project skeleton and local infrastructure.
2. Core schema and CS schema migrations.
3. Raw ingestion framework.
4. Polymarket ingestion first, because historical prices cannot be reconstructed later.
5. HLTV and Liquipedia ingestion.
6. CS normalization and entity resolution.
7. Feature store with point-in-time tests.
8. Baseline CS map-winner model.
9. Walk-forward backtesting harness.
10. Match and derivative simulator.
11. Edge and sizing layer.
12. Paper-trading dashboard.
13. Conservative live recommendation workflow.
14. v2 alpha modules after v1 proves stable.

## 15. Definition Of Done

A module is done when:

- It has unit tests for happy path and failure modes.
- It has an integration test against the real schema.
- It has a leakage test when time-based data is involved.
- It is idempotent.
- It logs structured run metadata.
- It exposes a CLI entrypoint.
- It records source, timestamp, and data snapshot lineage.
- It has operational metrics.

The CS v1 system is done when:

- CS ingestion runs incrementally.
- Polymarket snapshots are collected continuously.
- Features are point-in-time correct.
- The map-winner model is calibrated.
- The match simulator prices supported markets.
- The backtester runs walk-forward.
- Recommendations are logged with edge and suggested size.
- Paper trading has run for at least 30 days.
- Kill switches and dashboards exist.

## 16. Key Open Decisions

- Bankroll size and maximum drawdown tolerance.
- Legal and practical access to Polymarket and external books.
- Cloud provider or local-first infrastructure preference.
- Whether to use managed Postgres/S3/Redis or self-hosted services.
- Whether demo parsing is required for v1 or can start in v1.5.
- Which future game comes after CS.
- Whether live reaction systems are desired before broadening to other games.
