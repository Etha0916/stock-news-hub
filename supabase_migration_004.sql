-- ============================================================
-- supabase_migration_004.sql
--   Phase 5 / Week 2: enable Realtime on articles + read-only RLS policy.
--   Run once in Supabase SQL Editor.
-- ============================================================

-- (1) Enable Postgres logical replication for the articles table.
-- This is what the Supabase Realtime server listens to.
ALTER PUBLICATION supabase_realtime ADD TABLE articles;

-- (2) Allow anon key to SELECT articles.
-- We already enabled RLS at table-creation time; without an explicit policy,
-- the anon role gets zero rows. This policy unlocks read-only access.
-- INSERT/UPDATE/DELETE remain blocked because we never create policies for them
-- — only the postgres superuser (used via DATABASE_URL in GitHub Actions) can write.
DROP POLICY IF EXISTS "public can read articles" ON articles;
CREATE POLICY "public can read articles"
    ON articles
    FOR SELECT
    TO anon, authenticated
    USING (true);

-- Verify:
--   SELECT * FROM pg_publication_tables WHERE pubname = 'supabase_realtime';
--   -- should show 'articles'
--
--   SELECT * FROM pg_policies WHERE tablename = 'articles';
--   -- should show the SELECT policy above
