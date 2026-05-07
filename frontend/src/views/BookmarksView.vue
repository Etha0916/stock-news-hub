<script setup lang="ts">
import { computed } from "vue";
import { usePrefsStore } from "@/stores/prefs";
import { useUiStore } from "@/stores/ui";
import ArticleCard from "@/components/ArticleCard.vue";

const prefs = usePrefsStore();
const ui = useUiStore();

const count = computed(() => prefs.bookmarks.length);

function onClearAll() {
  const confirm_msg =
    ui.lang === "zh"
      ? `確定清除全部 ${count.value} 筆收藏?此動作無法復原。`
      : `Clear all ${count.value} bookmarks? This cannot be undone.`;
  if (window.confirm(confirm_msg)) prefs.clearBookmarks();
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
    <div class="flex items-center text-xs text-ink-low mb-4 gap-3">
      <h2 class="text-lg font-semibold text-ink-high">
        {{ ui.lang === "zh" ? "我的收藏" : "Bookmarks" }}
      </h2>
      <span class="ml-1">{{ count }}</span>
      <button
        v-if="count > 0"
        class="ml-auto text-xs text-ink-low hover:text-red-400"
        @click="onClearAll"
      >
        {{ ui.lang === "zh" ? "全部清除" : "Clear all" }}
      </button>
    </div>

    <div
      v-if="count === 0"
      class="text-center py-20 text-ink-low text-sm leading-relaxed"
    >
      <p class="text-3xl mb-3">🔖</p>
      <p class="mb-1">
        {{
          ui.lang === "zh" ? "還沒有收藏任何文章。" : "No bookmarks yet."
        }}
      </p>
      <p class="text-ink-faint">
        {{
          ui.lang === "zh"
            ? "回首頁,點文章右上角的愛心收藏。"
            : "Tap the heart on any article to save it."
        }}
      </p>
    </div>

    <div v-else class="space-y-3">
      <ArticleCard
        v-for="article in prefs.bookmarks"
        :key="article.id"
        :article="article"
      />
    </div>
  </div>
</template>
