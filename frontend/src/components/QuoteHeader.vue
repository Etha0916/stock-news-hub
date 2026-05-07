<script setup lang="ts">
import { computed } from "vue";
import type { Quote } from "@/types";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{
  quote: Quote | undefined;
  loading?: boolean;
  error?: string | null;
}>();

const ui = useUiStore();

const isUp = computed(() => (props.quote?.change ?? 0) >= 0);

const fmt = (n: number | null | undefined, digits = 2) =>
  n == null ? "—" : n.toFixed(digits);

const tsLocal = computed(() => {
  if (!props.quote?.ts) return "";
  try {
    return new Date(props.quote.ts).toLocaleString();
  } catch {
    return props.quote.ts;
  }
});
</script>

<template>
  <div class="bg-surface-1 border border-surface-border rounded-xl p-4 sm:p-5">
    <div v-if="error" class="text-red-400 text-sm">
      {{ ui.lang === "zh" ? "讀取股價失敗:" : "Failed to load quote:" }}
      {{ error }}
    </div>
    <div v-else-if="loading && !quote" class="text-ink-low text-sm">
      {{ ui.lang === "zh" ? "讀取股價中…" : "Loading quote…" }}
    </div>
    <div v-else-if="quote">
      <div class="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span class="text-3xl font-semibold text-ink-high">
          {{ fmt(quote.price) }}
        </span>
        <span
          class="text-base font-medium"
          :class="isUp ? 'text-emerald-400' : 'text-rose-400'"
        >
          {{ isUp ? "▲" : "▼" }} {{ fmt(Math.abs(quote.change ?? 0)) }}
          ({{ fmt(quote.change_pct ?? 0) }}%)
        </span>
        <span class="text-xs text-ink-faint ml-auto">
          {{ tsLocal }}
        </span>
      </div>
      <div class="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-y-2 gap-x-4 text-xs">
        <div>
          <div class="text-ink-faint">{{ ui.lang === "zh" ? "開盤" : "Open" }}</div>
          <div class="text-ink-mid font-medium">{{ fmt(quote.open) }}</div>
        </div>
        <div>
          <div class="text-ink-faint">{{ ui.lang === "zh" ? "昨收" : "Prev close" }}</div>
          <div class="text-ink-mid font-medium">{{ fmt(quote.prev_close) }}</div>
        </div>
        <div>
          <div class="text-ink-faint">{{ ui.lang === "zh" ? "高" : "High" }}</div>
          <div class="text-emerald-400 font-medium">{{ fmt(quote.high) }}</div>
        </div>
        <div>
          <div class="text-ink-faint">{{ ui.lang === "zh" ? "低" : "Low" }}</div>
          <div class="text-rose-400 font-medium">{{ fmt(quote.low) }}</div>
        </div>
      </div>
    </div>
  </div>
</template>
