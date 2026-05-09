<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useUiStore } from "@/stores/ui";
import { useNewsStore } from "@/stores/news";
import { useWatchlistStore } from "@/stores/watchlist";
import { useCategoriesStore } from "@/stores/categories";
import type { CustomCategory, Theme } from "@/types";

const props = defineProps<{
  /** null = create a new one; non-null = edit existing */
  category: CustomCategory | null;
}>();
const emit = defineEmits<{
  close: [];
}>();

const ui = useUiStore();
const news = useNewsStore();
const watchlist = useWatchlistStore();
const categories = useCategoriesStore();

const name = ref(props.category?.name ?? "");
const selected = ref<Set<string>>(new Set(props.category?.symbols ?? []));

watch(
  () => props.category,
  (c) => {
    name.value = c?.name ?? "";
    selected.value = new Set(c?.symbols ?? []);
  }
);

const tr = (t: Theme) => (ui.lang === "zh" ? t.label_zh : t.label_en);

// Candidate tickers: union of (watchlist) and (preset Mag7/ELN tickers).
// Custom (BABA-like) tickers must be added to watchlist first via sidebar input.
const candidates = computed(() => {
  const set = new Set<string>(watchlist.symbols);
  for (const [key, theme] of Object.entries(news.themes)) {
    if (theme.groups?.some((g) => g === "mag7" || g === "eln")) {
      set.add(key.toUpperCase());
    }
  }
  return [...set].sort();
});

function symbolLabel(sym: string): string {
  const themeKey = sym.toLowerCase();
  const t = news.themes[themeKey];
  return t ? tr(t) : sym;
}

function toggle(sym: string) {
  const next = new Set(selected.value);
  if (next.has(sym)) next.delete(sym);
  else next.add(sym);
  selected.value = next;
}

const canSave = computed(() => name.value.trim().length > 0);

function save() {
  const trimmed = name.value.trim();
  if (!trimmed) return;
  const syms = [...selected.value];

  if (props.category) {
    categories.update(props.category.id, { name: trimmed, symbols: syms });
  } else {
    categories.create(trimmed, syms);
  }

  // Auto-add to watchlist so news flow includes them
  for (const sym of syms) {
    if (!watchlist.isWatched(sym)) watchlist.addLocal(sym);
  }

  emit("close");
}

function onDelete() {
  if (!props.category) return;
  const msg =
    ui.lang === "zh"
      ? `刪除類別「${props.category.name}」?(僅刪分組,標的還會留在你的關注清單)`
      : `Delete category "${props.category.name}"? Tickers stay in your watchlist.`;
  if (window.confirm(msg)) {
    categories.remove(props.category.id);
    emit("close");
  }
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
    @click="emit('close')"
  >
    <div
      class="bg-surface-1 border border-surface-border rounded-xl p-5 max-w-md w-full max-h-[80vh] overflow-y-auto"
      @click.stop
    >
      <h3 class="text-lg font-semibold mb-3 text-ink-high">
        {{
          category
            ? ui.lang === "zh" ? "編輯類別" : "Edit category"
            : ui.lang === "zh" ? "新增類別" : "New category"
        }}
      </h3>

      <div class="text-xs text-ink-low mb-1">
        {{ ui.lang === "zh" ? "類別名稱" : "Name" }}
      </div>
      <input
        v-model="name"
        type="text"
        :placeholder="
          ui.lang === 'zh' ? '例如:我的 AI 板塊' : 'e.g. My AI plays'
        "
        class="w-full px-3 py-2 rounded bg-surface-0 border border-surface-border text-sm mb-4 focus:border-brand outline-none text-ink-high"
        @keyup.enter="save"
      />

      <div class="text-xs text-ink-low mb-1">
        {{
          ui.lang === "zh"
            ? `選擇標的(${selected.size} / ${candidates.length})`
            : `Select tickers (${selected.size} / ${candidates.length})`
        }}
      </div>

      <div
        v-if="candidates.length === 0"
        class="text-xs text-ink-faint py-3 leading-relaxed"
      >
        {{
          ui.lang === "zh"
            ? "目前沒有可選標的。先到左邊 sidebar 用 ☆ 加入關注,或新增 ticker。"
            : "No tickers available yet. Star tickers in the sidebar first."
        }}
      </div>

      <div v-else class="grid grid-cols-3 gap-1.5 mb-5 max-h-60 overflow-y-auto">
        <label
          v-for="sym in candidates"
          :key="sym"
          class="flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer hover:bg-surface-2 text-sm"
          :class="selected.has(sym) ? 'bg-surface-2' : ''"
        >
          <input
            type="checkbox"
            :checked="selected.has(sym)"
            @change="toggle(sym)"
            class="cursor-pointer accent-brand"
          />
          <span class="truncate">{{ symbolLabel(sym) }}</span>
        </label>
      </div>

      <div class="flex gap-2 items-center">
        <button
          v-if="category"
          class="px-3 py-1.5 rounded text-rose-400 hover:bg-surface-2 text-sm"
          @click="onDelete"
        >
          {{ ui.lang === "zh" ? "刪除" : "Delete" }}
        </button>
        <div class="flex-1"></div>
        <button
          class="px-3 py-1.5 rounded text-ink-low hover:bg-surface-2 text-sm"
          @click="emit('close')"
        >
          {{ ui.lang === "zh" ? "取消" : "Cancel" }}
        </button>
        <button
          class="px-3 py-1.5 rounded bg-brand hover:bg-brand-dark text-white text-sm disabled:bg-surface-2 disabled:cursor-not-allowed"
          :disabled="!canSave"
          @click="save"
        >
          {{
            category
              ? ui.lang === "zh" ? "儲存" : "Save"
              : ui.lang === "zh" ? "建立" : "Create"
          }}
        </button>
      </div>
    </div>
  </div>
</template>
