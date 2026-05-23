<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import type { Article, Theme } from "@/types";
import { useUiStore } from "@/stores/ui";
import { useNewsStore } from "@/stores/news";
import { usePrefsStore } from "@/stores/prefs";
import { safeUrl } from "@/composables/safeUrl";
import BookmarkButton from "./BookmarkButton.vue";

const props = defineProps<{ article: Article }>();

const ui = useUiStore();
const news = useNewsStore();
const prefs = usePrefsStore();

// A label key is a "ticker" iff:
//   (a) it's in news.themes AND belongs to a stock-listing group (mag7/eln), OR
//   (b) it's a 1-6 lowercase-letter label not registered in themes
//       (= a custom watchlist ticker auto-tagged from per-ticker RSS).
// Either way, badge becomes a clickable RouterLink to /ticker/:symbol.
const TICKER_GROUPS = new Set(["mag7", "eln"]);
const CUSTOM_TICKER_RE = /^[a-z]{1,6}$/;
function isTicker(themeKey: string): boolean {
  const t = news.themes[themeKey];
  if (t && t.groups) return t.groups.some((g) => TICKER_GROUPS.has(g));
  if (!t && CUSTOM_TICKER_RE.test(themeKey)) return true; // custom watchlist ticker
  return false;
}

function labelText(L: string): string {
  const t = news.themes[L];
  return t ? tr(t) : L.toUpperCase();
}

const tr = (t: Theme) => (ui.lang === "zh" ? t.label_zh : t.label_en);

const dateText = computed(() => {
  if (!props.article.published) return "";
  try {
    return new Date(props.article.published).toLocaleString();
  } catch {
    return "";
  }
});

const isRead = computed(() => prefs.isRead(props.article.id));

function onTitleClick() {
  prefs.markRead(props.article.id);
}

// ----- Sentiment indicator -----
// score ∈ [-1, +1]; we colour-band it conservatively so only clearly
// directional articles get a coloured dot (most news is mildly mixed).
const sentiment = computed(() => {
  const s = props.article.sentiment_score;
  if (s == null) {
    return { show: false, colour: "", emoji: "", label: "" };
  }
  if (s >= 0.3) {
    return {
      show: true,
      colour: "bg-emerald-500",
      emoji: "🟢",
      label: ui.lang === "zh" ? `偏多 (${s.toFixed(2)})` : `Bullish (${s.toFixed(2)})`,
    };
  }
  if (s <= -0.3) {
    return {
      show: true,
      colour: "bg-rose-500",
      emoji: "🔴",
      label: ui.lang === "zh" ? `偏空 (${s.toFixed(2)})` : `Bearish (${s.toFixed(2)})`,
    };
  }
  return {
    show: true,
    colour: "bg-slate-400",
    emoji: "⚪",
    label: ui.lang === "zh" ? `中性 (${s.toFixed(2)})` : `Neutral (${s.toFixed(2)})`,
  };
});

const sentimentTooltip = computed(() => {
  const r = props.article.sentiment_rationale;
  const base = sentiment.value.label;
  return r ? `${base} — ${r}` : base;
});

// Mobile-friendly: click the dot to toggle a detail panel below the title.
// Desktop users get the same info via the :title attribute hover.
const showSentimentDetail = ref(false);

const sentimentBorderClass = computed(() => {
  const s = props.article.sentiment_score;
  if (s == null) return "";
  if (s >= 0.3) return "border-emerald-500";
  if (s <= -0.3) return "border-rose-500";
  return "border-slate-400";
});
</script>

<template>
  <article
    class="group bg-surface-1 border border-surface-border rounded-xl p-4 sm:p-5 transition-all hover:border-brand"
    :class="{ 'opacity-60': isRead }"
  >
    <div class="flex items-start gap-2">
      <div class="flex-1 min-w-0">
        <h3 class="text-base font-semibold leading-snug mb-1.5 flex items-start gap-2">
          <button
            v-if="sentiment.show"
            type="button"
            class="-m-2 p-2 mt-0 flex-shrink-0 rounded hover:bg-surface-2 transition-colors"
            :title="sentimentTooltip"
            :aria-label="sentimentTooltip"
            :aria-expanded="showSentimentDetail"
            @click.stop.prevent="showSentimentDetail = !showSentimentDetail"
          >
            <span
              :class="['inline-block rounded-full', sentiment.colour]"
              style="width: 8px; height: 8px;"
              aria-hidden="true"
            />
          </button>
          <a
            :href="safeUrl(article.url)"
            target="_blank"
            rel="noopener noreferrer"
            class="hover:text-brand-subtle"
            :class="isRead ? 'text-ink-mid' : 'text-ink-high'"
            @click="onTitleClick"
          >
            {{ article.title }}
          </a>
        </h3>
        <!-- Sentiment detail panel — tap dot to toggle. Mobile-friendly,
             desktop users can still hover the dot for the same info. -->
        <div
          v-if="showSentimentDetail && sentiment.show"
          class="text-xs text-ink-mid mb-2 mt-0.5 border-l-2 pl-2 py-0.5"
          :class="sentimentBorderClass"
        >
          <span class="font-medium">{{ sentiment.label }}</span>
          <template v-if="article.sentiment_rationale">
            <span class="text-ink-low"> — {{ article.sentiment_rationale }}</span>
          </template>
        </div>
        <div class="text-xs text-ink-low mb-2">
          <span v-if="isRead" class="text-ink-faint mr-1.5">
            {{ ui.lang === "zh" ? "已讀 ·" : "read ·" }}
          </span>
          {{ article.source }} · {{ dateText }}
        </div>
        <p
          v-if="article.summary"
          class="text-sm leading-relaxed line-clamp-3"
          :class="isRead ? 'text-ink-low' : 'text-ink-mid'"
        >
          {{ article.summary }}
        </p>
        <div class="mt-2.5 flex flex-wrap gap-1.5">
          <template v-for="L in article.labels" :key="L">
            <RouterLink
              v-if="isTicker(L)"
              :to="{ name: 'ticker', params: { symbol: L.toUpperCase() } }"
              class="text-[11px] px-2 py-0.5 rounded-full bg-surface-2 text-brand-subtle hover:bg-brand hover:text-white transition-colors"
            >
              {{ labelText(L) }}
            </RouterLink>
            <span
              v-else
              class="text-[11px] px-2 py-0.5 rounded-full bg-surface-2 text-brand-subtle"
            >
              {{ labelText(L) }}
            </span>
          </template>
        </div>
      </div>
      <BookmarkButton :article="article" class="-mt-1 -mr-1 flex-shrink-0" />
    </div>
  </article>
</template>

<style scoped>
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
