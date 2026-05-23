-- ============================================================
-- supabase_migration_006.sql
--   Phase 6 / Sentiment: add per-article sentiment scoring.
--   Backfills are nullable — articles ingested before this migration
--   simply have NULL until the next ingest cycle re-scores them
--   (or you batch-backfill via scripts/backfill_sentiment.py).
--
--   Score range: [-1.0, +1.0]
--     -1.0 = strongly bearish
--      0.0 = neutral
--     +1.0 = strongly bullish
-- ============================================================

ALTER TABLE articles
    ADD COLUMN IF NOT EXISTS sentiment_score        REAL,
    ADD COLUMN IF NOT EXISTS sentiment_confidence   REAL,
    ADD COLUMN IF NOT EXISTS sentiment_rationale    TEXT,
    ADD COLUMN IF NOT EXISTS sentiment_model        TEXT,
    ADD COLUMN IF NOT EXISTS sentiment_scored_at    TIMESTAMPTZ;

-- Partial index — only over rows that have a score, so the index stays
-- small and is useful for queries like "top bullish news today".
CREATE INDEX IF NOT EXISTS idx_articles_sentiment_recent
    ON articles (published_at DESC, sentiment_score)
    WHERE sentiment_score IS NOT NULL;

-- Sanity-check query post-migration:
-- SELECT
--     count(*)                                       AS total,
--     count(sentiment_score)                         AS scored,
--     round(avg(sentiment_score)::numeric, 3)        AS mean_sentiment,
--     count(*) FILTER (WHERE sentiment_score >  0.3) AS bullish,
--     count(*) FILTER (WHERE sentiment_score < -0.3) AS bearish
-- FROM articles
-- WHERE published_at > NOW() - INTERVAL '24 hours';
