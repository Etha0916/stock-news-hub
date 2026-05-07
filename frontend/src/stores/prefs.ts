/**
 * User preference store — bookmarks + read tracking.
 * Persisted to localStorage. In Phase 5 (Auth) we'll point persistence at
 * a server endpoint per user, keeping the same store API so components
 * stay untouched.
 *
 * Design notes:
 *  - Bookmarks store the FULL article object so old items stay accessible
 *    after they roll out of the 14-day API window.
 *  - Read tracking only needs IDs (article body lives in news.articles or
 *    in bookmarks).
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { Article } from "@/types";

export const usePrefsStore = defineStore(
  "prefs",
  () => {
    // Newest-bookmarked-first ordering
    const bookmarks = ref<Article[]>([]);
    const readSet = ref<Set<number>>(new Set());

    // O(1) lookup helpers via computed
    const bookmarkedIds = computed(
      () => new Set(bookmarks.value.map((a) => a.id))
    );

    function isBookmarked(id: number) {
      return bookmarkedIds.value.has(id);
    }

    function toggleBookmark(article: Article) {
      const idx = bookmarks.value.findIndex((a) => a.id === article.id);
      if (idx >= 0) {
        bookmarks.value = bookmarks.value.filter((_, i) => i !== idx);
      } else {
        bookmarks.value = [article, ...bookmarks.value];
      }
    }

    function clearBookmarks() {
      bookmarks.value = [];
    }

    function isRead(id: number) {
      return readSet.value.has(id);
    }

    function markRead(id: number) {
      if (readSet.value.has(id)) return;
      const next = new Set(readSet.value);
      next.add(id);
      readSet.value = next;
    }

    function clearReadHistory() {
      readSet.value = new Set();
    }

    return {
      bookmarks,
      readSet,
      bookmarkedIds,
      isBookmarked,
      toggleBookmark,
      clearBookmarks,
      isRead,
      markRead,
      clearReadHistory,
    };
  },
  {
    persist: {
      storage: localStorage,
      serializer: {
        serialize: (state: Record<string, unknown>) =>
          JSON.stringify({
            bookmarks: state.bookmarks,
            readSet: [...(state.readSet as Set<number>)],
          }),
        deserialize: (s: string) => {
          try {
            const obj = JSON.parse(s);
            return {
              bookmarks: Array.isArray(obj.bookmarks) ? obj.bookmarks : [],
              readSet: new Set<number>(obj.readSet ?? []),
            };
          } catch {
            return { bookmarks: [], readSet: new Set<number>() };
          }
        },
      },
    },
  }
);
