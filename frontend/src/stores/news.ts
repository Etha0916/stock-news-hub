/**
 * News store — server-backed data: themes, articles. Not persisted.
 *
 * filteredArticles is a computed that respects the UI store's filter state,
 * so components just consume it without doing filter logic themselves.
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type {
  Article,
  Theme,
  ThemeGroup,
  ThemesPayload,
  ArticlesPayload,
} from "@/types";
import { apiGet } from "@/composables/useApi";
import { useUiStore } from "./ui";

export const useNewsStore = defineStore("news", () => {
  const themes = ref<Record<string, Theme>>({});
  const groups = ref<Record<string, ThemeGroup>>({});
  const articles = ref<Article[]>([]);
  const updatedAt = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const ui = useUiStore();

  const filteredArticles = computed<Article[]>(() => {
    if (ui.selectedThemes.size === 0) return articles.value;
    return articles.value.filter((a) =>
      a.labels.some((l) => ui.selectedThemes.has(l))
    );
  });

  async function fetchAll() {
    if (loading.value) return;
    loading.value = true;
    error.value = null;
    try {
      const [t, a] = await Promise.all([
        apiGet<ThemesPayload>("/api/themes"),
        apiGet<ArticlesPayload>("/api/articles?days=14&limit=500"),
      ]);
      themes.value = t.themes;
      groups.value = t.groups;
      articles.value = a.articles ?? [];
      updatedAt.value = a.updated_at;
    } catch (e) {
      error.value = e instanceof Error ? e.message : "Unknown error";
    } finally {
      loading.value = false;
    }
  }

  return {
    themes,
    groups,
    articles,
    updatedAt,
    loading,
    error,
    filteredArticles,
    fetchAll,
  };
});
