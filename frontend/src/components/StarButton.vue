<script setup lang="ts">
import { computed } from "vue";
import { useWatchlistStore } from "@/stores/watchlist";

const props = defineProps<{ symbol: string }>();
const watchlist = useWatchlistStore();

const watched = computed(() => watchlist.isWatched(props.symbol));

function onClick(e: MouseEvent) {
  e.stopPropagation();
  e.preventDefault();
  if (watched.value) watchlist.remove(props.symbol);
  else watchlist.addLocal(props.symbol);
}
</script>

<template>
  <button
    class="text-base leading-none transition-colors p-0.5"
    :class="
      watched
        ? 'text-amber-400 hover:text-amber-300'
        : 'text-ink-faint hover:text-ink-low'
    "
    :title="watched ? '取消關注' : '加入關注'"
    @click="onClick"
  >
    {{ watched ? "★" : "☆" }}
  </button>
</template>
