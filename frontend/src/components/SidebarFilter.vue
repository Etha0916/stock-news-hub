<script setup lang="ts">
import { computed } from "vue";
import { useUiStore } from "@/stores/ui";
import { useNewsStore } from "@/stores/news";
import type { Theme, ThemeGroup } from "@/types";

const ui = useUiStore();
const news = useNewsStore();

const tr = (t: { label_en: string; label_zh: string }) =>
  ui.lang === "zh" ? t.label_zh : t.label_en;

// Themes that don't belong to any group → render flat at top
const flatThemes = computed(() =>
  Object.entries(news.themes).filter(
    ([, t]) => !t.groups || t.groups.length === 0
  )
);

// Groups with their child themes
interface GroupView {
  gkey: string;
  group: ThemeGroup;
  children: { key: string; theme: Theme }[];
}
const groupedThemes = computed<GroupView[]>(() =>
  Object.entries(news.groups).map(([gkey, group]) => ({
    gkey,
    group,
    children: Object.entries(news.themes)
      .filter(([, t]) => t.groups?.includes(gkey))
      .map(([key, theme]) => ({ key, theme })),
  }))
);

const isAllSelected = (childKeys: string[]) =>
  childKeys.length > 0 && childKeys.every((k) => ui.selectedThemes.has(k));

const isShared = (theme: Theme) => (theme.groups?.length ?? 0) > 1;
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

    <!-- Standalone themes (top-level checkboxes) -->
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

    <!-- Groups with children -->
    <div
      v-for="{ gkey, group, children } in groupedThemes"
      :key="gkey"
      class="mt-3 pt-2.5 border-t border-surface-border"
    >
      <div
        class="flex items-center gap-2 px-1 py-1 cursor-pointer text-sm text-ink-mid select-none"
        @click="ui.toggleGroupCollapse(gkey)"
      >
        <span
          class="text-[10px] text-ink-faint w-2.5 inline-block transition-transform"
          :style="{
            transform: ui.collapsedGroups.has(gkey)
              ? 'rotate(-90deg)'
              : 'rotate(0deg)',
          }"
        >
          ▼
        </span>
        <input
          type="checkbox"
          :checked="isAllSelected(children.map((c) => c.key))"
          @change.stop="ui.toggleGroup(children.map((c) => c.key))"
          @click.stop
          class="cursor-pointer accent-brand"
        />
        <strong class="font-semibold">{{ tr(group) }}</strong>
        <span class="ml-auto text-[11px] text-ink-faint">
          {{ children.length }}
        </span>
      </div>

      <div v-show="!ui.collapsedGroups.has(gkey)" class="pl-4 pt-1">
        <label
          v-for="c in children"
          :key="c.key"
          class="flex items-center gap-2 px-1.5 py-1 rounded-md cursor-pointer hover:bg-surface-2 text-[13.5px] select-none"
          :title="
            isShared(c.theme)
              ? ui.lang === 'zh'
                ? '此標的同時屬於多組'
                : 'Shared across groups'
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
            class="ml-auto text-[11px] text-ink-faint"
            >↔</span
          >
        </label>
      </div>
    </div>
  </aside>
</template>
