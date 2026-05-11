<script setup lang="ts">
import { computed } from "vue";
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
</script>

<template>
  <article
    class="group bg-surface-1 border border-surface-border rounded-xl p-4 sm:p-5 transition-all hover:border-brand"
    :class="{ 'opacity-60': isRead }"
  >
    <div class="flex items-start gap-2">
      <div class="flex-1 min-w-0">
        <h3 class="text-base font-semibold leading-snug mb-1.5">
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
