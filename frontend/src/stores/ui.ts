/**
 * UI store — purely user-side state: language, filters, collapsed groups,
 * sort mode. Persisted to localStorage so reload preserves selections.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import type { Lang, SortMode } from "@/types";

export const useUiStore = defineStore(
  "ui",
  () => {
    const lang = ref<Lang>("zh");
    const selectedThemes = ref<Set<string>>(new Set());
    const collapsedGroups = ref<Set<string>>(new Set());
    const sortMode = ref<SortMode>("time");

    function toggleTheme(key: string) {
      const next = new Set(selectedThemes.value);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      selectedThemes.value = next;
    }

    function toggleGroup(childKeys: string[]) {
      if (childKeys.length === 0) return;
      const next = new Set(selectedThemes.value);
      const allSelected = childKeys.every((k) => next.has(k));
      if (allSelected) childKeys.forEach((k) => next.delete(k));
      else childKeys.forEach((k) => next.add(k));
      selectedThemes.value = next;
    }

    function toggleGroupCollapse(gkey: string) {
      const next = new Set(collapsedGroups.value);
      if (next.has(gkey)) next.delete(gkey);
      else next.add(gkey);
      collapsedGroups.value = next;
    }

    function clearFilters() {
      selectedThemes.value = new Set();
    }

    function setLang(l: Lang) {
      lang.value = l;
    }

    function setSortMode(m: SortMode) {
      sortMode.value = m;
    }

    return {
      lang,
      selectedThemes,
      collapsedGroups,
      sortMode,
      toggleTheme,
      toggleGroup,
      toggleGroupCollapse,
      clearFilters,
      setLang,
      setSortMode,
    };
  },
  {
    persist: {
      storage: localStorage,
      serializer: {
        serialize: (state: Record<string, unknown>) =>
          JSON.stringify({
            lang: state.lang,
            sortMode: state.sortMode,
            selectedThemes: [...(state.selectedThemes as Set<string>)],
            collapsedGroups: [...(state.collapsedGroups as Set<string>)],
          }),
        deserialize: (s: string) => {
          try {
            const obj = JSON.parse(s);
            return {
              lang: (obj.lang as Lang) ?? "zh",
              sortMode: (obj.sortMode as SortMode) ?? "time",
              selectedThemes: new Set<string>(obj.selectedThemes ?? []),
              collapsedGroups: new Set<string>(obj.collapsedGroups ?? []),
            };
          } catch {
            return {
              lang: "zh" as Lang,
              sortMode: "time" as SortMode,
              selectedThemes: new Set<string>(),
              collapsedGroups: new Set<string>(),
            };
          }
        },
      },
    },
  }
);
