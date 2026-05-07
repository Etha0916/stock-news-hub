<script setup lang="ts">
import { useUiStore } from "@/stores/ui";
import type { SortMode } from "@/types";

const ui = useUiStore();

const options: { value: SortMode; label_zh: string; label_en: string }[] = [
  { value: "time",      label_zh: "時序",  label_en: "Latest" },
  { value: "relevance", label_zh: "熱度",  label_en: "Top" },
];
</script>

<template>
  <div class="inline-flex bg-surface-2 rounded-md p-0.5 text-xs">
    <button
      v-for="opt in options"
      :key="opt.value"
      class="px-2.5 py-1 rounded transition-colors"
      :class="
        ui.sortMode === opt.value
          ? 'bg-brand text-white'
          : 'text-ink-low hover:text-ink-high'
      "
      @click="ui.setSortMode(opt.value)"
    >
      {{ ui.lang === "zh" ? opt.label_zh : opt.label_en }}
    </button>
  </div>
</template>
