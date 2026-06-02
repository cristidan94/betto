-- Authenticated Polymarket account history.

CREATE TABLE IF NOT EXISTS polymarket_account_orders (
  order_id       TEXT PRIMARY KEY,
  market_id      TEXT,
  token_id       TEXT,
  side           TEXT,
  outcome        TEXT,
  original_size  NUMERIC,
  size_matched   NUMERIC,
  price          NUMERIC,
  status         TEXT,
  order_type     TEXT,
  created_at     TIMESTAMPTZ,
  raw            JSONB NOT NULL,
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS polymarket_account_orders_market_idx ON polymarket_account_orders (market_id);
CREATE INDEX IF NOT EXISTS polymarket_account_orders_created_idx ON polymarket_account_orders (created_at DESC);

CREATE TABLE IF NOT EXISTS polymarket_trades (
  trade_id       TEXT PRIMARY KEY,
  order_id       TEXT,
  market_id      TEXT,
  token_id       TEXT,
  side           TEXT,
  outcome        TEXT,
  size           NUMERIC,
  price          NUMERIC,
  status         TEXT,
  tx_hash        TEXT,
  matched_at     TIMESTAMPTZ,
  raw            JSONB NOT NULL,
  ingested_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS polymarket_trades_order_idx ON polymarket_trades (order_id);
CREATE INDEX IF NOT EXISTS polymarket_trades_market_idx ON polymarket_trades (market_id);
CREATE INDEX IF NOT EXISTS polymarket_trades_matched_at_idx ON polymarket_trades (matched_at DESC);
