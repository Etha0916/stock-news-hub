<script setup lang="ts">
import { useNewsStore } from "@/stores/news";
import { useUiStore } from "@/stores/ui";
import ArticleCard from "./ArticleCard.vue";

const news = useNewsStore();
const ui = useUiStore();
</script>

<template>
  <section>
    <div
      v-if="news.loading && news.articles.length === 0"
      class="text-center py-16 text-ink-low"
    >
      {{ ui.lang === "zh" ? "載入中…" : "Loading…" }}
    </div>

    <div
      v-else-if="news.error"
      class="text-center py-16 text-red-400 text-sm"
    >
      {{ news.error }}
    </div>

    <div
      v-else-if="news.filteredArticles.length === 0"
      class="text-center py-16 text-ink-low"
    >
      {{ ui.lang === "zh" ? "暫無符合條件的文章" : "No matching articles" }}
    </div>

    <div v-else class="space-y-3">
      <ArticleCard
        v-for="article in news.filteredArticles"
        :key="article.id"
        :article="article"
      />
    </div>
  </section>
</template>
