<script setup lang="ts">
// Stage 3-4 placeholder
import { useRoute } from "vue-router";
const route = useRoute();
const symbol = (route.params.symbol as string)?.toUpperCase() ?? "";
</script>

<template>
  <div class="px-4 sm:px-6 py-12 max-w-3xl mx-auto text-center text-ink-low">
    個股頁:{{ symbol }} (Stage 3-4 實作)
  </div>
</template>
