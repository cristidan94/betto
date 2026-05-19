-- Store generated strategy report artifact metadata.

CREATE TABLE IF NOT EXISTS report_artifacts (
  report_id        TEXT PRIMARY KEY,
  strategy_id      TEXT NOT NULL,
  report_type      TEXT NOT NULL,
  artifact_uri     TEXT NOT NULL,
  metrics          JSONB NOT NULL,
  readiness        JSONB NOT NULL,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS report_artifacts_strategy_created_idx
ON report_artifacts (strategy_id, created_at DESC);
