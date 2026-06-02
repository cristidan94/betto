-- Repair early 0007 runs where orders.bet_id may have been created as TEXT.

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'orders'
      AND column_name = 'bet_id'
      AND data_type = 'text'
  ) THEN
    ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_bet_id_fkey;
    ALTER TABLE orders
      ALTER COLUMN bet_id TYPE BIGINT USING NULLIF(bet_id, '')::BIGINT;
    ALTER TABLE orders
      ADD CONSTRAINT orders_bet_id_fkey FOREIGN KEY (bet_id) REFERENCES bets(bet_id);
  END IF;
END $$;
