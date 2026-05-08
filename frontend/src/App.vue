<script setup lang="ts">
import { onMounted, onBeforeUnmount, computed } from "vue";
import { RouterView, RouterLink } from "vue-router";
import { BRAND } from "@/branding";
import LangToggle from "@/components/LangToggle.vue";
import { useRealtimeStore } from "@/stores/realtime";

const realtime = useRealtimeStore();

onMounted(() => {
  realtime.subscribe();
});

onBeforeUnmount(() => {
  realtime.unsubscribe();
});

// Map status → dot color for the live indicator
const statusColor = computed(() => {
  switch (realtime.status) {
    case "connected":    return "bg-emerald-400";
    case "connecting":   return "bg-amber-400 animate-pulse";
    case "error":        return "bg-rose-400";
    case "disabled":     return "bg-ink-faint";
    default:             return "bg-ink-faint";
  }
});

const statusTitle = computed(() => {
  switch (realtime.status) {
    case "connected":    return "即時連線中";
    case "connecting":   return "連線中…";
    case "error":        return "連線錯誤(自動降級為輪詢)";
    case "disabled":     return "未啟用即時推送";
    default:             return "未連線";
  }
});
</script>

<template>
  <div class="min-h-full flex flex-col bg-surface-0 text-ink-high">
    <header
      class="sticky top-0 z-10 bg-surface-1 border-b border-surface-border px-4 sm:px-6 py-3 flex items-center gap-4"
    >
      <RouterLink to="/" class="flex items-center gap-2 hover:opacity-80">
        <span class="text-xl">{{ BRAND.emoji }}</span>
        <h1 class="text-lg font-semibold">{{ BRAND.appName_zh }}</h1>
        <span
          class="inline-block w-2 h-2 rounded-full"
          :class="statusColor"
          :title="statusTitle"
        ></span>
      </RouterLink>

      <nav class="ml-auto flex items-center gap-4 text-sm">
        <RouterLink
          to="/bookmarks"
          class="text-ink-low hover:text-ink-high"
          active-class="text-ink-high"
        >
          收藏
        </RouterLink>
        <span class="text-ink-faint">|</span>
        <LangToggle />
      </nav>
    </header>

    <main class="flex-1">
      <RouterView />
    </main>
  </div>
</template>
