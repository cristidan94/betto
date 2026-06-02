-- Polymarket enriched market data and order tracking.

-- Store Polymarket-specific metadata as JSONB to avoid schema churn for source-specific fields.
ALTER TABLE markets
  ADD COLUMN IF NOT EXISTS polymarket_meta JSONB,
  ADD COLUMN IF NOT EXISTS description TEXT;

-- Order tracking for live and paper bet placement.
CREATE TABLE IF NOT EXISTS orders (
  order_id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
  bet_id            BIGINT REFERENCES bets(bet_id),
  market_id         TEXT NOT NULL REFERENCES markets(market_id),
  outcome           TEXT NOT NULL,
  mode              TEXT NOT NULL DEFAULT 'paper' CHECK (mode IN ('paper', 'live')),
  order_type        TEXT NOT NULL DEFAULT 'market' CHECK (order_type IN ('market', 'limit')),
  side              TEXT NOT NULL DEFAULT 'buy' CHECK (side IN ('buy', 'sell')),
  limit_price       NUMERIC,
  fill_price        NUMERIC,
  size_usd          NUMERIC NOT NULL,
  fill_size_usd     NUMERIC,
  order_status      TEXT NOT NULL DEFAULT 'pending' CHECK (order_status IN ('pending', 'open', 'filled', 'partial', 'cancelled', 'expired')),
  polymarket_token_id TEXT,
  polymarket_order_id TEXT,
  tx_hash           TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS orders_market_id_idx ON orders (market_id);
CREATE INDEX IF NOT EXISTS orders_mode_status_idx ON orders (mode, order_status);
CREATE INDEX IF NOT EXISTS orders_bet_id_idx ON orders (bet_id);

-- Add mode column to bets table for paper/live distinction.
ALTER TABLE bets
  ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'paper' CHECK (mode IN ('paper', 'live'));
