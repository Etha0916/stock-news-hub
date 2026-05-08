<script setup lang="ts">
import { onMounted, computed } from "vue";
import { useNewsStore } from "@/stores/news";
import { useUiStore } from "@/stores/ui";
import { useRealtimeStore } from "@/stores/realtime";
import SidebarFilter from "@/components/SidebarFilter.vue";
import ArticleFeed from "@/components/ArticleFeed.vue";
import SortToggle from "@/components/SortToggle.vue";

const news = useNewsStore();
const ui = useUiStore();
const realtime = useRealtimeStore();

const stats = computed(() => {
  if (!news.updatedAt) return "";
  let when = "";
  try {
    when = new Date(news.updatedAt).toLocaleString();
  } catch {
    when = news.updatedAt;
  }
  const total = news.articles.length;
  return ui.lang === "zh"
    ? `${total} 篇 · 更新 ${when}`
    : `${total} articles · updated ${when}`;
});

function showNewArticles() {
  realtime.clearNewCount();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

onMounted(async () => {
  if (news.articles.length === 0) await news.fetchAll();
});

setInterval(() => {
  if (!document.hidden) news.fetchAll();
}, 5 * 60 * 1000);
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 sm:px-6 py-3 sm:py-5">
    <!-- "Live: N new articles" banner — only shows when realtime delivers updates -->
    <button
      v-if="realtime.newCount > 0"
      class="w-full mb-3 py-2 rounded-md bg-brand text-white text-sm flex items-center justify-center gap-2 hover:bg-brand-dark transition-colors animate-pulse-once"
      @click="showNewArticles"
    >
      <span class="text-base">↑</span>
      <span>
        {{
          ui.lang === "zh"
            ? `${realtime.newCount} 篇新文章 — 點擊查看`
            : `${realtime.newCount} new — click to view`
        }}
      </span>
    </button>

    <div class="flex items-center text-xs text-ink-low mb-3 gap-3 flex-wrap">
      <span>{{ stats }}</span>
      <SortToggle class="ml-auto" />
      <button
        class="px-3 py-1.5 rounded-md bg-brand hover:bg-brand-dark text-white disabled:bg-surface-2 disabled:cursor-wait"
        :disabled="news.loading"
        @click="news.fetchAll()"
      >
        {{
          news.loading
            ? ui.lang === "zh"
              ? "載入中…"
              : "Loading…"
            : ui.lang === "zh"
              ? "重新載入"
              : "Reload"
        }}
      </button>
    </div>

    <div class="grid md:grid-cols-[240px_1fr] gap-4 sm:gap-6">
      <SidebarFilter />
      <ArticleFeed />
    </div>
  </div>
</template>

<style scoped>
@keyframes pulse-once {
  0% { transform: scale(1); }
  50% { transform: scale(1.02); }
  100% { transform: scale(1); }
}
.animate-pulse-once {
  animation: pulse-once 0.6s ease-out;
}
</style>
