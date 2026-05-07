<script setup lang="ts">
import { useUiStore } from "@/stores/ui";
const ui = useUiStore();
</script>

<template>
  <div class="flex items-center text-xs gap-3">
    <label
      class="cursor-pointer flex items-center gap-1"
      :class="ui.lang === 'zh' ? 'text-ink-high' : 'text-ink-low'"
    >
      <input
        type="radio"
        name="lang"
        value="zh"
        :checked="ui.lang === 'zh'"
        @change="ui.setLang('zh')"
        class="cursor-pointer accent-brand"
      />
      中文
    </label>
    <label
      class="cursor-pointer flex items-center gap-1"
      :class="ui.lang === 'en' ? 'text-ink-high' : 'text-ink-low'"
    >
      <input
        type="radio"
        name="lang"
        value="en"
        :checked="ui.lang === 'en'"
        @change="ui.setLang('en')"
        class="cursor-pointer accent-brand"
      />
      EN
    </label>
  </div>
</template>
