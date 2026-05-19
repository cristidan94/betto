-- Make recommendation writes idempotent for repeated paper evaluation runs.

CREATE UNIQUE INDEX IF NOT EXISTS recommendations_market_outcome_time_strategy_idx
ON recommendations (market_id, outcome, taken_at, strategy_id);
