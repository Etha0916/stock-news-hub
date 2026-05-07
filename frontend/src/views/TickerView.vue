<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter, RouterLink } from "vue-router";
import { useNewsStore } from "@/stores/news";
import { useUiStore } from "@/stores/ui";
import { useQuoteStore } from "@/stores/quote";
import QuoteHeader from "@/components/QuoteHeader.vue";
import PriceChart from "@/components/PriceChart.vue";
import ArticleCard from "@/components/ArticleCard.vue";

const route = useRoute();
const router = useRouter();
const news = useNewsStore();
const ui = useUiStore();
const quoteStore = useQuoteStore();

const symbol = computed(() => (route.params.symbol as string).toUpperCase());
const themeKey = computed(() => symbol.value.toLowerCase());

const days = ref(90);
const dayOptions = [7, 30, 90, 180, 365];

const themeName = computed(() => {
  const t = news.themes[themeKey.value];
  if (!t) return symbol.value;
  return ui.lang === "zh" ? t.label_zh : t.label_en;
});

const tickerArticles = computed(() =>
  news.articles.filter((a) => a.labels.includes(themeKey.value))
);

const quote = computed(() => quoteStore.quotes[symbol.value]);
const candles = computed(() => quoteStore.candles[symbol.value] ?? []);

async function loadAll() {
  if (news.articles.length === 0) news.fetchAll();
  await Promise.all([
    quoteStore.fetchQuote(symbol.value),
    quoteStore.fetchCandles(symbol.value, days.value),
  ]);
}

onMounted(loadAll);

watch(symbol, loadAll);
watch(days, () => quoteStore.fetchCandles(symbol.value, days.value));
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 sm:px-6 py-4 sm:py-6">
    <!-- Breadcrumb / nav -->
    <div class="flex items-center text-xs text-ink-low mb-3">
      <RouterLink to="/" class="hover:text-ink-high">
        ← {{ ui.lang === "zh" ? "回首頁" : "Home" }}
      </RouterLink>
      <span class="ml-auto text-ink-faint">
        {{ tickerArticles.length }}
        {{ ui.lang === "zh" ? "篇相關新聞" : "related articles" }}
      </span>
    </div>

    <!-- Header: symbol + theme name -->
    <div class="mb-4 flex items-baseline gap-3">
      <h2 class="text-2xl font-bold text-ink-high">{{ symbol }}</h2>
      <span v-if="themeName !== symbol" class="text-ink-low">{{ themeName }}</span>
    </div>

    <!-- Quote -->
    <QuoteHeader
      :quote="quote"
      :loading="quoteStore.isLoadingQuote(symbol)"
      :error="quoteStore.quoteError(symbol)"
      class="mb-3"
    />

    <!-- Range selector + chart -->
    <div class="flex items-center gap-1 mb-2 text-xs">
      <span class="text-ink-faint mr-1">
        {{ ui.lang === "zh" ? "區間" : "Range" }}:
      </span>
      <button
        v-for="d in dayOptions"
        :key="d"
        class="px-2 py-1 rounded transition-colors"
        :class="
          days === d
            ? 'bg-brand text-white'
            : 'text-ink-low hover:bg-surface-2'
        "
        @click="days = d"
      >
        {{ d < 30 ? `${d}d` : d < 365 ? `${d / 30 | 0}M` : `${d / 365}Y` }}
      </button>
    </div>

    <PriceChart
      :candles="candles"
      :loading="quoteStore.isLoadingCandles(symbol)"
      :error="quoteStore.candleError(symbol)"
      class="mb-6"
    />

    <!-- News list -->
    <h3 class="text-sm font-semibold text-ink-low uppercase tracking-wider mb-3">
      {{ ui.lang === "zh" ? "相關新聞" : "Related news" }}
    </h3>

    <div
      v-if="news.loading && tickerArticles.length === 0"
      class="text-center py-12 text-ink-low text-sm"
    >
      {{ ui.lang === "zh" ? "載入中…" : "Loading…" }}
    </div>
    <div
      v-else-if="tickerArticles.length === 0"
      class="text-center py-12 text-ink-low text-sm"
    >
      {{
        ui.lang === "zh"
          ? `近 14 天沒有 ${symbol} 相關新聞`
          : `No ${symbol} news in last 14 days`
      }}
    </div>
    <div v-else class="space-y-3">
      <ArticleCard
        v-for="article in tickerArticles"
        :key="article.id"
        :article="article"
      />
    </div>
  </div>
</template>
