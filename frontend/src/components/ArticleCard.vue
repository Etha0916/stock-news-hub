<script setup lang="ts">
import { computed } from "vue";
import { RouterLink } from "vue-router";
import type { Article, Theme } from "@/types";
import { useUiStore } from "@/stores/ui";
import { useNewsStore } from "@/stores/news";
import { usePrefsStore } from "@/stores/prefs";
import BookmarkButton from "./BookmarkButton.vue";

const props = defineProps<{ article: Article }>();

const ui = useUiStore();
const news = useNewsStore();
const prefs = usePrefsStore();

// A theme is a "ticker" iff it belongs to one of the stock-listing groups.
// Used to decide whether a label badge becomes a clickable RouterLink to /ticker/:symbol.
const TICKER_GROUPS = new Set(["mag7", "eln"]);
function isTicker(themeKey: string): boolean {
  const t = news.themes[themeKey];
  if (!t || !t.groups) return false;
  return t.groups.some((g) => TICKER_GROUPS.has(g));
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
            :href="article.url"
            target="_blank"
            rel="noopener"
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
              {{ news.themes[L] ? tr(news.themes[L]) : L }}
            </RouterLink>
            <span
              v-else
              class="text-[11px] px-2 py-0.5 rounded-full bg-surface-2 text-brand-subtle"
            >
              {{ news.themes[L] ? tr(news.themes[L]) : L }}
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
