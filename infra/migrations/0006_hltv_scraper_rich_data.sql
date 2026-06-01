-- Extend CS tables for full-fidelity HLTV scraper data.

ALTER TABLE cs_map_results
  ADD COLUMN IF NOT EXISTS map_stats_id TEXT,
  ADD COLUMN IF NOT EXISTS overtime BOOLEAN,
  ADD COLUMN IF NOT EXISTS team_a_first_half INT,
  ADD COLUMN IF NOT EXISTS team_a_second_half INT,
  ADD COLUMN IF NOT EXISTS team_b_first_half INT,
  ADD COLUMN IF NOT EXISTS team_b_second_half INT;

ALTER TABLE cs_player_map_stats
  ADD COLUMN IF NOT EXISTS ct_kills INT,
  ADD COLUMN IF NOT EXISTS ct_deaths INT,
  ADD COLUMN IF NOT EXISTS t_kills INT,
  ADD COLUMN IF NOT EXISTS t_deaths INT,
  ADD COLUMN IF NOT EXISTS flash_assists INT,
  ADD COLUMN IF NOT EXISTS trade_deaths INT;

ALTER TABLE contests
  ADD COLUMN IF NOT EXISTS match_stage TEXT,
  ADD COLUMN IF NOT EXISTS head_to_head JSONB;
