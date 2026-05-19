-- Store walk-forward backtest run summaries and window-level metrics.

CREATE TABLE IF NOT EXISTS backtest_runs (
  backtest_run_id TEXT PRIMARY KEY,
  strategy_id     TEXT NOT NULL,
  game_id         TEXT NOT NULL,
  target          TEXT NOT NULL,
  data_snapshot_id TEXT REFERENCES data_snapshots(data_snapshot_id),
  run_config      JSONB NOT NULL,
  metrics         JSONB NOT NULL,
  window_results  JSONB NOT NULL,
  artifact_uri    TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS backtest_runs_strategy_created_idx
ON backtest_runs (strategy_id, created_at DESC);
