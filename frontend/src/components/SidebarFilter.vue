<script setup lang="ts">
import { computed, ref } from "vue";
import { useUiStore } from "@/stores/ui";
import { useNewsStore } from "@/stores/news";
import { useWatchlistStore } from "@/stores/watchlist";
import { useCategoriesStore } from "@/stores/categories";
import type { Theme, ThemeGroup, CustomCategory } from "@/types";
import StarButton from "./StarButton.vue";
import WatchlistInput from "./WatchlistInput.vue";
import CategoryEditModal from "./CategoryEditModal.vue";

const ui = useUiStore();
const news = useNewsStore();
const watchlist = useWatchlistStore();
const categories = useCategoriesStore();

const tr = (t: { label_en: string; label_zh: string }) =>
  ui.lang === "zh" ? t.label_zh : t.label_en;

// ---- top-level (no group) themes ----
const flatThemes = computed(() =>
  Object.entries(news.themes).filter(
    ([, t]) => !t.groups || t.groups.length === 0
  )
);

// ---- preset groups (Mag7, ELN) ----
interface GroupView {
  gkey: string;
  group: ThemeGroup;
  children: { key: string; theme: Theme; symbol: string }[];
}
const groupedThemes = computed<GroupView[]>(() =>
  Object.entries(news.groups).map(([gkey, group]) => ({
    gkey,
    group,
    children: Object.entries(news.themes)
      .filter(([, t]) => t.groups?.includes(gkey))
      .map(([key, theme]) => ({
        key,
        theme,
        symbol: key.toUpperCase(),
      })),
  }))
);

const isAllSelected = (childKeys: string[]) =>
  childKeys.length > 0 && childKeys.every((k) => ui.selectedThemes.has(k));

const isShared = (theme: Theme) => (theme.groups?.length ?? 0) > 1;

// ---- watchlist (flat) ----
const watchedItems = computed(() =>
  watchlist.symbols.map((sym) => {
    const themeKey = sym.toLowerCase();
    const t = news.themes[themeKey];
    return {
      key: themeKey,
      symbol: sym,
      label: t ? tr(t) : sym,
      isCustom: !t,
    };
  })
);

function addAllFromGroup(symbols: string[]) {
  watchlist.addLocalMany(symbols);
}

// ---- custom categories (user-created) ----
interface CategoryChild {
  key: string;       // theme key (lowercase)
  symbol: string;    // ticker (uppercase)
  label: string;     // display label
}
const categoryViews = computed(() =>
  categories.list.map((cat) => ({
    cat,
    children: cat.symbols.map<CategoryChild>((sym) => {
      const themeKey = sym.toLowerCase();
      const t = news.themes[themeKey];
      return {
        key: themeKey,
        symbol: sym,
        label: t ? tr(t) : sym,
      };
    }),
  }))
);

// modal state
const editing = ref<CustomCategory | null>(null);
const showModal = ref(false);

function openCreate() {
  editing.value = null;
  showModal.value = true;
}
function openEdit(cat: CustomCategory) {
  editing.value = cat;
  showModal.value = true;
}
function closeModal() {
  showModal.value = false;
  editing.value = null;
}
</script>

<template>
  <aside
    class="bg-surface-1 rounded-xl p-4 md:sticky md:top-20 md:self-start"
  >
    <div class="flex items-center mb-2">
      <span
        class="text-[11px] uppercase tracking-wider font-semibold text-ink-low"
      >
        {{ ui.lang === "zh" ? "分類篩選" : "Filters" }}
      </span>
      <button
        class="ml-auto text-[11px] text-ink-low hover:text-ink-high"
        @click="ui.clearFilters()"
      >
        {{ ui.lang === "zh" ? "清除" : "Clear" }}
      </button>
    </div>

    <!-- =============================================================== -->
    <!-- Watchlist (always at top) -->
    <!-- =============================================================== -->
    <div class="pb-3 border-b border-surface-border mb-2">
      <div
        class="flex items-center gap-2 px-1 py-1 cursor-pointer text-sm text-ink-mid select-none"
        @click="ui.toggleGroupCollapse('__watchlist__')"
      >
        <span
          class="text-[10px] text-ink-faint w-2.5 inline-block transition-transform"
          :style="{
            transform: ui.collapsedGroups.has('__watchlist__')
              ? 'rotate(-90deg)' : 'rotate(0deg)',
          }"
        >▼</span>
        <input
          type="checkbox"
          :checked="
            watchedItems.length > 0 &&
            watchedItems.every((w) => ui.selectedThemes.has(w.key))
          "
          :disabled="watchedItems.length === 0"
          @change.stop="
            ui.toggleGroup(watchedItems.map((w) => w.key))
          "
          @click.stop
          class="cursor-pointer accent-brand"
        />
        <strong class="font-semibold">
          {{ ui.lang === "zh" ? "我的關注" : "Watchlist" }}
        </strong>
        <span class="ml-auto text-[11px] text-ink-faint">
          {{ watchedItems.length }}
        </span>
      </div>

      <div v-show="!ui.collapsedGroups.has('__watchlist__')" class="pl-4 pt-1">
        <div
          v-if="watchedItems.length === 0"
          class="text-[11px] text-ink-faint px-1 py-1.5 leading-relaxed"
        >
          {{ ui.lang === "zh"
            ? "點擊預設分類旁的 ☆ 加入,或下方新增任意美股代號。"
            : "Star preset tickers below, or add any US ticker." }}
        </div>
        <label
          v-for="w in watchedItems"
          :key="w.key"
          class="flex items-center gap-2 px-1.5 py-1 rounded-md cursor-pointer hover:bg-surface-2 text-[13.5px] select-none"
        >
          <input
            type="checkbox"
            :checked="ui.selectedThemes.has(w.key)"
            @change="ui.toggleTheme(w.key)"
            class="cursor-pointer accent-brand"
          />
          <span>{{ w.label }}</span>
          <span
            v-if="w.isCustom"
            class="text-[10px] px-1 rounded bg-surface-2 text-ink-faint"
          >自訂</span>
          <span class="ml-auto">
            <StarButton :symbol="w.symbol" />
          </span>
        </label>

        <WatchlistInput />
      </div>
    </div>

    <!-- =============================================================== -->
    <!-- Standalone (top-level) themes -->
    <!-- =============================================================== -->
    <label
      v-for="[key, t] in flatThemes"
      :key="key"
      class="flex items-center gap-2 px-1.5 py-1.5 rounded-md cursor-pointer hover:bg-surface-2 text-sm select-none"
    >
      <input
        type="checkbox"
        :checked="ui.selectedThemes.has(key)"
        @change="ui.toggleTheme(key)"
        class="cursor-pointer accent-brand"
      />
      <span>{{ tr(t) }}</span>
    </label>

    <!-- =============================================================== -->
    <!-- Custom categories (user-created) -->
    <!-- =============================================================== -->
    <div
      v-for="{ cat, children } in categoryViews"
      :key="cat.id"
      class="mt-3 pt-2.5 border-t border-surface-border"
    >
      <div class="flex items-center gap-2 px-1 py-1 text-sm text-ink-mid select-none">
        <span
          class="text-[10px] text-ink-faint w-2.5 inline-block transition-transform cursor-pointer"
          :style="{
            transform: ui.collapsedGroups.has('cat:' + cat.id)
              ? 'rotate(-90deg)' : 'rotate(0deg)',
          }"
          @click="ui.toggleGroupCollapse('cat:' + cat.id)"
        >▼</span>
        <input
          type="checkbox"
          :checked="
            children.length > 0 &&
            children.every((c) => ui.selectedThemes.has(c.key))
          "
          :disabled="children.length === 0"
          @change.stop="ui.toggleGroup(children.map((c) => c.key))"
          @click.stop
          class="cursor-pointer accent-brand"
        />
        <strong
          class="font-semibold cursor-pointer truncate"
          @click="ui.toggleGroupCollapse('cat:' + cat.id)"
        >{{ cat.name }}</strong>
        <button
          class="text-[10px] text-ink-faint hover:text-ink-high"
          :title="ui.lang === 'zh' ? '編輯類別' : 'Edit category'"
          @click.stop="openEdit(cat)"
        >⋯</button>
        <span class="ml-auto text-[11px] text-ink-faint">{{ children.length }}</span>
      </div>

      <div v-show="!ui.collapsedGroups.has('cat:' + cat.id)" class="pl-4 pt-1">
        <div
          v-if="children.length === 0"
          class="text-[11px] text-ink-faint px-1 py-1"
        >
          {{ ui.lang === "zh" ? "(空)點 ⋯ 編輯加入標的" : "(empty) click ⋯ to add" }}
        </div>
        <label
          v-for="c in children"
          :key="c.key"
          class="flex items-center gap-2 px-1.5 py-1 rounded-md cursor-pointer hover:bg-surface-2 text-[13.5px] select-none"
        >
          <input
            type="checkbox"
            :checked="ui.selectedThemes.has(c.key)"
            @change="ui.toggleTheme(c.key)"
            class="cursor-pointer accent-brand"
          />
          <span>{{ c.label }}</span>
          <span class="ml-auto">
            <StarButton :symbol="c.symbol" />
          </span>
        </label>
      </div>
    </div>

    <!-- "+ 新增類別" button (always at end of custom section) -->
    <button
      class="w-full mt-2 text-left text-xs px-2 py-1.5 rounded-md bg-surface-2 hover:bg-surface-border text-ink-low hover:text-ink-mid"
      @click="openCreate"
    >
      {{ ui.lang === "zh" ? "+ 新增自創類別" : "+ New category" }}
    </button>

    <!-- =============================================================== -->
    <!-- Preset groups (Mag7 / ELN) — shown last as templates -->
    <!-- =============================================================== -->
    <div
      v-for="{ gkey, group, children } in groupedThemes"
      :key="gkey"
      class="mt-3 pt-2.5 border-t border-surface-border"
    >
      <div class="flex items-center gap-2 px-1 py-1 text-sm text-ink-mid select-none">
        <span
          class="text-[10px] text-ink-faint w-2.5 inline-block transition-transform cursor-pointer"
          :style="{
            transform: ui.collapsedGroups.has(gkey)
              ? 'rotate(-90deg)' : 'rotate(0deg)',
          }"
          @click="ui.toggleGroupCollapse(gkey)"
        >▼</span>
        <input
          type="checkbox"
          :checked="isAllSelected(children.map((c) => c.key))"
          @change.stop="ui.toggleGroup(children.map((c) => c.key))"
          @click.stop
          class="cursor-pointer accent-brand"
        />
        <strong
          class="font-semibold cursor-pointer"
          @click="ui.toggleGroupCollapse(gkey)"
        >{{ tr(group) }}</strong>
        <button
          class="text-[10px] text-ink-faint hover:text-amber-400"
          :title="ui.lang === 'zh' ? '把整組加進關注' : 'Star all in group'"
          @click.stop="addAllFromGroup(children.map((c) => c.symbol))"
        >+全部</button>
        <span class="ml-auto text-[11px] text-ink-faint">{{ children.length }}</span>
      </div>

      <div v-show="!ui.collapsedGroups.has(gkey)" class="pl-4 pt-1">
        <label
          v-for="c in children"
          :key="c.key"
          class="flex items-center gap-2 px-1.5 py-1 rounded-md cursor-pointer hover:bg-surface-2 text-[13.5px] select-none"
          :title="
            isShared(c.theme)
              ? ui.lang === 'zh' ? '此標的同時屬於多組' : 'Shared across groups'
              : ''
          "
        >
          <input
            type="checkbox"
            :checked="ui.selectedThemes.has(c.key)"
            @change="ui.toggleTheme(c.key)"
            class="cursor-pointer accent-brand"
          />
          <span>{{ tr(c.theme) }}</span>
          <span
            v-if="isShared(c.theme)"
            class="text-[11px] text-ink-faint"
          >↔</span>
          <span class="ml-auto">
            <StarButton :symbol="c.symbol" />
          </span>
        </label>
      </div>
    </div>

    <!-- Modal: create/edit custom category -->
    <CategoryEditModal
      v-if="showModal"
      :category="editing"
      @close="closeModal"
    />
  </aside>
</template>
