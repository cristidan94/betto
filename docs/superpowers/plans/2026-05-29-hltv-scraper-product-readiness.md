# HLTV Scraper Product Readiness Plan

Date: 2026-05-29

## Product Goal

Turn the HLTV scraper from a working data collector into an unattended data product that can:

- Backfill all configured tier 1 and tier 2 matches without manual babysitting.
- Resume from the exact page and queue state after a VPS restart, deploy, daily cap, quiet hours, or proxy failure.
- Show progress, data quality, and recent failures from one command.
- Alert when the historical backfill finishes or when the operator should intervene.
- Produce fixture JSON with a stable enough contract for downstream model training.

## Current Strengths

- The scraper already has a VPS-friendly deployment flow, systemd units, proxy support, quiet hours, daily caps, and backups.
- Discovery is filtered by HLTV star pages and an event allow list, which gives practical tier 1 and tier 2 coverage.
- The queue is idempotent by `match_id`, so rediscovery does not create duplicates.
- Match lifecycle state exists: scheduled/live/finished/incomplete/final rows can be retried later.
- Raw HTML and parsed fixture JSON are both stored, which keeps debugging and reparsing possible.

## Product Gaps

1. **Progress visibility**
   - The operator needs a single command for queue totals, backfill cursor, request health, file counts, and latest outputs.
   - The status payload should answer: how many discovered, parsed, final, open, due, failed, and which page comes next.

2. **Data quality**
   - A scraper that writes files is not automatically useful training data.
   - It needs a quality report that flags missing teams, missing maps, finished matches with no maps, suspicious player counts, and missing player stats.

3. **Failure operations**
   - There should be admin commands to list failed rows and requeue them without touching SQLite directly.
   - Backfill state should be resettable from the CLI if the allow list or start page changes.

4. **Unattended historical backfill**
   - The backfill needs durable cursor state, configurable page bounds, empty-page stop rules, hourly systemd scheduling, and automatic stop when complete.
   - Completion should be visible and optionally sent to a webhook.

5. **Health checks and alerts**
   - The VPS needs a fast no-network health command suitable for cron/systemd checks.
   - Alerts should use a generic webhook so Discord, Slack, Telegram gateways, or custom endpoints can be added without changing scraper code.

6. **Tier classification**
   - Current tiering is pragmatic: HLTV 5-star results are treated as higher priority than 4-star results, plus an allow list for known event families.
   - A later phase should add explicit event-tier overrides by event name and year because HLTV stars are useful but not a full business definition of tier 1/tier 2.

7. **Stats completeness**
   - Match pages are being parsed successfully, but stats pages have been flaky on VPS.
   - This should be tracked as a quality metric and handled as an incremental improvement rather than blocking match-level backfill.

## Implementation Plan

### Slice 1: Operator Readiness

Deliver now:

- Add `quality-report` CLI command.
- Add `health` CLI command.
- Add `failed`, `retry-failed`, and `reset-backfill` admin commands.
- Include failed counts in queue stats.
- Fix due-count comparisons to use the same ISO timestamp format as stored queue rows.
- Add tests for the new commands and database operations.

### Slice 2: Unattended Backfill

Deliver now:

- Persist backfill start/completion timestamps.
- Add `HLTV_BACKFILL_MAX_PAGE` as a safety bound for historical scans.
- Send a single completion webhook if `HLTV_ALERT_WEBHOOK_URL` is configured.
- Keep the existing hourly systemd backfill timer as the automation engine.

### Slice 3: Documentation

Deliver now:

- Document the product readiness plan.
- Update scraper README/deploy notes with progress, quality, health, and admin commands.
- Keep all operational commands copy-paste friendly for the VPS.

### Slice 4: Next Product Upgrades

Do after this slice:

- Add event-tier override rules such as `tier_overrides.yml`.
- Improve HLTV stats-page collection and parse richer player fields.
- Add a summarized daily digest alert with discovered/fetched/final/failed deltas.
- Export a manifest file with schema version, row counts, and data snapshot hash.
- Add a small read-only web dashboard if command-line progress is not enough.

## Definition Of Done For This Slice

- `python -m scraper.cli quality-report` returns a JSON quality summary.
- `python -m scraper.cli health` returns nonzero when basic operational checks fail.
- `python -m scraper.cli failed` lists failed queue rows.
- `python -m scraper.cli retry-failed` requeues failed rows.
- `python -m scraper.cli reset-backfill --start-page N` resets the backfill cursor safely.
- Backfill marks started/completed timestamps and sends at most one completion alert.
- Scraper tests pass locally.

## VPS Runbook After Deploy

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli status --verbose
.venv/bin/python -m scraper.cli quality-report
.venv/bin/python -m scraper.cli health
.venv/bin/python -m scraper.cli failed --limit 20
```

To requeue failed matches:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli retry-failed --limit 100
sudo systemctl start hltv-backfill.service
```

To restart historical backfill from a page:

```bash
cd /opt/betto/scraper
.venv/bin/python -m scraper.cli reset-backfill --start-page 0
sudo systemctl enable --now hltv-backfill.timer
sudo systemctl start hltv-backfill.service
```
