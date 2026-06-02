-- Make historical price snapshot backfills re-runnable.

DELETE FROM market_snapshots newer
USING market_snapshots older
WHERE newer.snapshot_id > older.snapshot_id
  AND newer.market_id = older.market_id
  AND newer.outcome = older.outcome
  AND newer.taken_at = older.taken_at;

CREATE UNIQUE INDEX IF NOT EXISTS market_snapshots_market_outcome_time_unique
ON market_snapshots (market_id, outcome, taken_at);
