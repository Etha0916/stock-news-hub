-- ============================================================
-- supabase_migration_002.sql
--   Phase 3: add SimHash column for semantic deduplication.
--   Run once in Supabase SQL Editor after Phase 1 schema is in place.
-- ============================================================

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS simhash BIGINT;

CREATE INDEX IF NOT EXISTS idx_articles_simhash
    ON articles (simhash);

-- Verify:
-- SELECT column_name, data_type FROM information_schema.columns
--   WHERE table_name = 'articles' ORDER BY ordinal_position;
