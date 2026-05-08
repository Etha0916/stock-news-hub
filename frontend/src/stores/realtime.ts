/**
 * Realtime store — subscribes to Postgres `INSERT` events on the `articles`
 * table via Supabase Realtime, prepends new rows into the news store, and
 * exposes a `newCount` for the header badge.
 *
 * If env vars aren't set (or supabase client isn't initialized), the store
 * is a no-op — the rest of the app keeps working with periodic polling.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import type { RealtimeChannel } from "@supabase/supabase-js";

import { supabase, supabaseEnabled } from "@/lib/supabase";
import type { Article } from "@/types";
import { useNewsStore } from "./news";

type Status = "disabled" | "disconnected" | "connecting" | "connected" | "error";

export const useRealtimeStore = defineStore("realtime", () => {
  const status = ref<Status>(supabaseEnabled ? "disconnected" : "disabled");
  const newCount = ref(0);
  let channel: RealtimeChannel | null = null;

  function subscribe() {
    if (!supabase || !supabaseEnabled) return;
    if (channel) return; // already subscribed

    status.value = "connecting";
    const news = useNewsStore();

    channel = supabase
      .channel("articles-feed")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "articles" },
        (payload) => {
          // Postgres column names → API field names mapping
          const row = payload.new as Record<string, unknown>;
          const a: Article = {
            id: row.id as number,
            url: row.url as string,
            title: row.title as string,
            summary: (row.summary as string) ?? null,
            published: row.published_at as string | null,
            source: row.source as string,
            labels: (row.labels as string[]) ?? [],
            scores: (row.scores as Record<string, number>) ?? {},
          };
          if (news.handleNewArticle(a)) {
            newCount.value += 1;
          }
        }
      )
      .subscribe((s) => {
        if (s === "SUBSCRIBED") status.value = "connected";
        else if (s === "CHANNEL_ERROR" || s === "TIMED_OUT")
          status.value = "error";
        else if (s === "CLOSED") status.value = "disconnected";
      });
  }

  function unsubscribe() {
    if (channel && supabase) {
      supabase.removeChannel(channel);
      channel = null;
      status.value = supabaseEnabled ? "disconnected" : "disabled";
    }
  }

  function clearNewCount() {
    newCount.value = 0;
  }

  return { status, newCount, subscribe, unsubscribe, clearNewCount };
});
