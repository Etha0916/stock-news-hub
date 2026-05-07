<script setup lang="ts">
import { RouterView, RouterLink } from "vue-router";
import { BRAND } from "@/branding";
import LangToggle from "@/components/LangToggle.vue";
</script>

<template>
  <div class="min-h-full flex flex-col bg-surface-0 text-ink-high">
    <header
      class="sticky top-0 z-10 bg-surface-1 border-b border-surface-border px-4 sm:px-6 py-3 flex items-center gap-4"
    >
      <RouterLink to="/" class="flex items-center gap-2 hover:opacity-80">
        <span class="text-xl">{{ BRAND.emoji }}</span>
        <h1 class="text-lg font-semibold">{{ BRAND.appName_zh }}</h1>
      </RouterLink>

      <nav class="ml-auto flex items-center gap-4 text-sm">
        <RouterLink
          to="/bookmarks"
          class="text-ink-low hover:text-ink-high"
          active-class="text-ink-high"
        >
          {{ "收藏" }}
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
