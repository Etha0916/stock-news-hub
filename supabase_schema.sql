-- ============================================================
-- supabase_schema.sql
--   Run this once in your Supabase project's SQL Editor:
--   https://supabase.com/dashboard → SQL Editor → New query → paste → Run
-- ============================================================

CREATE TABLE IF NOT EXISTS articles (
    id           BIGSERIAL PRIMARY KEY,
    -- sha256(url)[:16] — gives stable URL-based dedupe key
    url_hash     CHAR(16) UNIQUE NOT NULL,
    url          TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    source       TEXT NOT NULL,
    -- Multi-label tagging stored as PG array (mag7→stripped, leaf-level only)
    labels       TEXT[] NOT NULL DEFAULT '{}',
    -- Per-theme classifier scores; useful for tuning later
    scores       JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_published
    ON articles (published_at DESC);

CREATE INDEX IF NOT EXISTS idx_articles_labels
    ON articles USING GIN (labels);

-- Sanity-check query you can run after first ingest:
-- SELECT count(*) AS total,
--        count(DISTINCT unnest(labels)) AS distinct_themes,
--        max(published_at) AS newest
-- FROM articles;
