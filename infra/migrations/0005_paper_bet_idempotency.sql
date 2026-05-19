-- Make paper bet logging idempotent for recommendations replayed from the DB.

CREATE UNIQUE INDEX IF NOT EXISTS bets_recommendation_strategy_idx
ON bets (recommendation_id, strategy_id)
WHERE recommendation_id IS NOT NULL;
