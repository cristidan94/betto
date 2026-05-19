-- Core and Counter-Strike v1 schema.
-- Target database: Postgres 16.

CREATE TABLE IF NOT EXISTS data_snapshots (
  data_snapshot_id TEXT PRIMARY KEY,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  description      TEXT
);

CREATE TABLE IF NOT EXISTS raw_objects (
  raw_object_id BIGSERIAL PRIMARY KEY,
  source        TEXT NOT NULL,
  source_id     TEXT NOT NULL,
  url           TEXT NOT NULL,
  content_hash  TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  fetched_at    TIMESTAMPTZ NOT NULL,
  storage_uri   TEXT NOT NULL,
  UNIQUE (source, source_id, content_hash)
);

CREATE TABLE IF NOT EXISTS participants (
  participant_id TEXT PRIMARY KEY,
  game_id        TEXT NOT NULL,
  kind           TEXT NOT NULL,
  display_name   TEXT NOT NULL,
  source         TEXT NOT NULL,
  source_id      TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (game_id, source, source_id)
);

CREATE TABLE IF NOT EXISTS competitions (
  competition_id TEXT PRIMARY KEY,
  game_id        TEXT NOT NULL,
  name           TEXT NOT NULL,
  tier           TEXT,
  starts_at      TIMESTAMPTZ,
  ends_at        TIMESTAMPTZ,
  source         TEXT,
  source_id      TEXT,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contests (
  contest_id       TEXT PRIMARY KEY,
  game_id          TEXT NOT NULL,
  competition_id   TEXT REFERENCES competitions(competition_id),
  starts_at        TIMESTAMPTZ NOT NULL,
  participant_a_id TEXT NOT NULL REFERENCES participants(participant_id),
  participant_b_id TEXT NOT NULL REFERENCES participants(participant_id),
  format           TEXT NOT NULL,
  status           TEXT NOT NULL,
  winner_id        TEXT REFERENCES participants(participant_id),
  source           TEXT,
  source_id        TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS contests_game_starts_idx ON contests (game_id, starts_at);

CREATE TABLE IF NOT EXISTS contest_units (
  unit_id         TEXT PRIMARY KEY,
  contest_id      TEXT NOT NULL REFERENCES contests(contest_id),
  sequence_number INT NOT NULL,
  unit_type       TEXT NOT NULL,
  name            TEXT,
  winner_id       TEXT REFERENCES participants(participant_id),
  UNIQUE (contest_id, sequence_number)
);

CREATE TABLE IF NOT EXISTS markets (
  market_id        TEXT PRIMARY KEY,
  source           TEXT NOT NULL,
  question         TEXT NOT NULL,
  market_type      TEXT NOT NULL,
  contest_id       TEXT REFERENCES contests(contest_id),
  outcomes         JSONB NOT NULL,
  outcome_mapping  JSONB,
  link_confidence  NUMERIC,
  created_at       TIMESTAMPTZ,
  resolved_at      TIMESTAMPTZ,
  resolved_outcome TEXT
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  snapshot_id     BIGSERIAL PRIMARY KEY,
  market_id       TEXT NOT NULL REFERENCES markets(market_id),
  outcome         TEXT NOT NULL,
  taken_at        TIMESTAMPTZ NOT NULL,
  best_bid        NUMERIC,
  best_ask        NUMERIC,
  last_trade_price NUMERIC,
  depth_bid_1pct  NUMERIC,
  depth_ask_1pct  NUMERIC
);

CREATE INDEX IF NOT EXISTS market_snapshots_market_time_idx ON market_snapshots (market_id, taken_at DESC);

CREATE TABLE IF NOT EXISTS feature_values (
  feature_value_id BIGSERIAL PRIMARY KEY,
  entity_id        TEXT NOT NULL,
  feature_name     TEXT NOT NULL,
  as_of            TIMESTAMPTZ NOT NULL,
  value            JSONB NOT NULL,
  metadata         JSONB NOT NULL DEFAULT '{}'::JSONB,
  data_snapshot_id TEXT REFERENCES data_snapshots(data_snapshot_id),
  UNIQUE (entity_id, feature_name, as_of)
);

CREATE INDEX IF NOT EXISTS feature_values_lookup_idx ON feature_values (entity_id, feature_name, as_of DESC);

CREATE TABLE IF NOT EXISTS model_artifacts (
  model_id         TEXT PRIMARY KEY,
  game_id          TEXT NOT NULL,
  target           TEXT NOT NULL,
  git_sha          TEXT NOT NULL,
  data_snapshot_id TEXT NOT NULL,
  config_hash      TEXT NOT NULL,
  feature_names    JSONB NOT NULL,
  metrics          JSONB NOT NULL,
  artifact_uri     TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recommendations (
  recommendation_id BIGSERIAL PRIMARY KEY,
  market_id         TEXT NOT NULL REFERENCES markets(market_id),
  outcome           TEXT NOT NULL,
  taken_at          TIMESTAMPTZ NOT NULL,
  model_id          TEXT REFERENCES model_artifacts(model_id),
  model_prob        NUMERIC NOT NULL,
  market_prob       NUMERIC NOT NULL,
  edge              NUMERIC NOT NULL,
  bankroll_fraction NUMERIC NOT NULL,
  passes_filter     BOOLEAN NOT NULL,
  reason            TEXT NOT NULL,
  strategy_id       TEXT NOT NULL DEFAULT 'core_v1'
);

CREATE TABLE IF NOT EXISTS bets (
  bet_id           BIGSERIAL PRIMARY KEY,
  recommendation_id BIGINT REFERENCES recommendations(recommendation_id),
  market_id        TEXT NOT NULL REFERENCES markets(market_id),
  outcome          TEXT NOT NULL,
  placed_at        TIMESTAMPTZ,
  model_prob       NUMERIC,
  market_prob      NUMERIC,
  edge             NUMERIC,
  kelly_fraction   NUMERIC,
  stake_usd        NUMERIC,
  price_in         NUMERIC,
  price_close      NUMERIC,
  clv              NUMERIC,
  resolved_outcome TEXT,
  pnl_usd          NUMERIC,
  model_version    TEXT,
  config_hash      TEXT,
  strategy_id      TEXT NOT NULL DEFAULT 'core_v1',
  latency_ms       INT
);

CREATE TABLE IF NOT EXISTS cs_roster_periods (
  roster_period_id BIGSERIAL PRIMARY KEY,
  team_id          TEXT NOT NULL REFERENCES participants(participant_id),
  player_id        TEXT NOT NULL REFERENCES participants(participant_id),
  role             TEXT,
  start_date       DATE NOT NULL,
  end_date         DATE,
  is_stand_in      BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (team_id, player_id, start_date)
);

CREATE TABLE IF NOT EXISTS cs_veto_actions (
  contest_id TEXT NOT NULL REFERENCES contests(contest_id),
  order_idx  INT NOT NULL,
  team_id    TEXT REFERENCES participants(participant_id),
  action     TEXT NOT NULL,
  map_name   TEXT NOT NULL,
  PRIMARY KEY (contest_id, order_idx)
);

CREATE TABLE IF NOT EXISTS cs_map_results (
  unit_id          TEXT PRIMARY KEY REFERENCES contest_units(unit_id),
  map_name         TEXT NOT NULL,
  team_a_score     INT,
  team_b_score     INT,
  team_a_ct_rounds INT,
  team_a_t_rounds  INT,
  duration_sec     INT,
  demo_uri         TEXT
);

CREATE TABLE IF NOT EXISTS cs_map_lineups (
  unit_id   TEXT NOT NULL REFERENCES contest_units(unit_id),
  team_id   TEXT NOT NULL REFERENCES participants(participant_id),
  player_id TEXT NOT NULL REFERENCES participants(participant_id),
  PRIMARY KEY (unit_id, player_id)
);

CREATE TABLE IF NOT EXISTS cs_player_map_stats (
  unit_id       TEXT NOT NULL REFERENCES contest_units(unit_id),
  player_id     TEXT NOT NULL REFERENCES participants(participant_id),
  team_id       TEXT NOT NULL REFERENCES participants(participant_id),
  kills         INT,
  deaths        INT,
  assists       INT,
  adr           NUMERIC,
  kast          NUMERIC,
  rating_2_0    NUMERIC,
  hs_pct        NUMERIC,
  first_kills   INT,
  first_deaths  INT,
  clutches_won  INT,
  PRIMARY KEY (unit_id, player_id)
);

