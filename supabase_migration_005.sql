-- ============================================================
-- supabase_migration_005.sql
--   Phase 5 / Watchlist: dynamic ticker registry.
--   When a frontend user adds an arbitrary US ticker (e.g. BABA),
--   it lands here. ingest.py reads this table on each cron run and
--   pulls Yahoo Finance RSS for every registered symbol.
-- ============================================================

CREATE TABLE IF NOT EXISTS watchlist_tickers (
    symbol           TEXT PRIMARY KEY,
    added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Diagnostics: track how productive each ticker is
    article_count    INTEGER NOT NULL DEFAULT 0,
    last_fetched_at  TIMESTAMPTZ
);

-- Allow anon/authenticated to SELECT (so frontend can list registered tickers
-- if we want to show "popular community-added tickers" later).
ALTER TABLE watchlist_tickers ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "public can read watchlist tickers" ON watchlist_tickers;
CREATE POLICY "public can read watchlist tickers"
    ON watchlist_tickers FOR SELECT TO anon, authenticated USING (true);
