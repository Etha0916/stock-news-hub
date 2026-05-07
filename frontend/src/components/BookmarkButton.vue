<script setup lang="ts">
import { computed } from "vue";
import type { Article } from "@/types";
import { usePrefsStore } from "@/stores/prefs";
import { useUiStore } from "@/stores/ui";

const props = defineProps<{ article: Article }>();
const prefs = usePrefsStore();
const ui = useUiStore();

const bookmarked = computed(() => prefs.isBookmarked(props.article.id));

function onClick(e: MouseEvent) {
  // Prevent the click from bubbling to the article link
  e.stopPropagation();
  e.preventDefault();
  prefs.toggleBookmark(props.article);
}
</script>

<template>
  <button
    :title="
      bookmarked
        ? ui.lang === 'zh'
          ? '取消收藏'
          : 'Remove bookmark'
        : ui.lang === 'zh'
          ? '加入收藏'
          : 'Save'
    "
    class="p-1.5 rounded-md transition-colors"
    :class="
      bookmarked
        ? 'text-pink-400 hover:text-pink-300'
        : 'text-ink-faint hover:text-ink-low'
    "
    @click="onClick"
  >
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      :fill="bookmarked ? 'currentColor' : 'none'"
      stroke="currentColor"
      stroke-width="2"
      stroke-linejoin="round"
    >
      <path
        d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"
      />
    </svg>
  </button>
</template>
