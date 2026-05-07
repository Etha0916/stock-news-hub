-- ============================================================
-- supabase_migration_003.sql
--   Phase 5 / Week 2: add MinHash signature column.
--   Run once in Supabase SQL Editor.
-- ============================================================

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS minhash_bytes BYTEA;

-- We don't index minhash_bytes itself (BYTEA isn't useful as a query key);
-- the LSH index lives in-memory in ingest.py (rebuilt each run from a 24h
-- window of these stored signatures).

-- Verify:
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = 'articles' ORDER BY ordinal_position;
