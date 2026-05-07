/**
 * News store — server-backed data: themes, articles. Not persisted.
 *
 * displayedArticles applies the UI store's filters AND sort mode:
 *   - "time"      → chronological (newest first), default
 *   - "relevance" → exponential time-decay × theme score
 *
 * Time-decay model:
 *   recency(Δt) = exp(-λ Δt)        where Δt is hours since publication
 *   λ = ln(2) / T_half               with T_half = 24h
 *   relevance = max(theme_scores) * recency
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

const HALF_LIFE_HOURS = 24;
const LAMBDA = Math.LN2 / HALF_LIFE_HOURS;

function relevanceScore(
  a: Article,
  selectedThemes: Set<string>,
  nowSec: number
): number {
  const ageHours = a.published
    ? Math.max(0, (nowSec - new Date(a.published).getTime() / 1000) / 3600)
    : 999;
  const recency = Math.exp(-LAMBDA * ageHours);

  // Theme score: when filter active, use max score across selected themes.
  // When no filter, use max across all themes (so strong-signal articles win).
  const scores = a.scores ?? {};
  let themeScore: number;
  if (selectedThemes.size > 0) {
    themeScore = 0;
    for (const t of selectedThemes) themeScore = Math.max(themeScore, scores[t] ?? 0);
    if (themeScore === 0) themeScore = 0.1; // floor to avoid zeroing-out
  } else {
    const all = Object.values(scores);
    themeScore = all.length ? Math.max(...all) : 1;
  }

  return themeScore * recency;
}

export const useNewsStore = defineStore("news", () => {
  const themes = ref<Record<string, Theme>>({});
  const groups = ref<Record<string, ThemeGroup>>({});
  const articles = ref<Article[]>([]);
  const updatedAt = ref<string | null>(null);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const ui = useUiStore();

  // Step 1: filter by selected themes (or pass-through if none)
  const filteredArticles = computed<Article[]>(() => {
    if (ui.selectedThemes.size === 0) return articles.value;
    return articles.value.filter((a) =>
      a.labels.some((l) => ui.selectedThemes.has(l))
    );
  });

  // Step 2: apply sort mode
  const displayedArticles = computed<Article[]>(() => {
    const arts = filteredArticles.value;
    if (ui.sortMode === "time") return arts; // already DESC by published from API
    const now = Date.now() / 1000;
    return [...arts].sort((a, b) => {
      return (
        relevanceScore(b, ui.selectedThemes, now) -
        relevanceScore(a, ui.selectedThemes, now)
      );
    });
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
    displayedArticles,
    fetchAll,
  };
});
