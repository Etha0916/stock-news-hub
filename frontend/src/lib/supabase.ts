/**
 * Singleton Supabase client.
 * The anon key is safe to ship in client bundles — Row Level Security on the
 * articles table caps it to read-only. Writes are only possible via the
 * postgres role (DATABASE_URL) used server-side by GitHub Actions.
 */
import { createClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;

export const supabaseEnabled = Boolean(url && anonKey);

export const supabase = supabaseEnabled
  ? createClient(url, anonKey, {
      realtime: {
        params: {
          eventsPerSecond: 10, // bound burst rate (mostly irrelevant for us)
        },
      },
      auth: {
        persistSession: false, // we don't use Supabase Auth (yet)
      },
    })
  : null;
