# Counter-Strike Schema

The Postgres migration in `infra/migrations/0001_core_cs_schema.sql` owns the current core and CS schema.

CS-specific tables are prefixed with `cs_`. Core tables intentionally avoid map, veto, side, round, or demo assumptions so future games can plug in without inheriting Counter-Strike concepts.

