/**
 * Custom categories — user-defined groupings of tickers.
 *
 * Conceptually parallel to the preset Mag7 / ELN groups in config.py, but
 * created and managed entirely client-side. Stored in localStorage.
 *
 * Constraints:
 *   - Symbol must be uppercase
 *   - Saving a category that includes a symbol not yet in watchlist
 *     auto-adds it to watchlist (so news flow includes it)
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import type { CustomCategory } from "@/types";

function newId(): string {
  // crypto.randomUUID is supported in all evergreen browsers
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  // Fallback for old runtimes
  return "cat_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export const useCategoriesStore = defineStore(
  "categories",
  () => {
    const list = ref<CustomCategory[]>([]);

    function create(name: string, symbols: string[]): CustomCategory {
      const cat: CustomCategory = {
        id: newId(),
        name: name.trim(),
        symbols: [...new Set(symbols.map((s) => s.toUpperCase()))],
        createdAt: Date.now(),
      };
      list.value = [...list.value, cat];
      return cat;
    }

    function update(
      id: string,
      patch: Partial<Omit<CustomCategory, "id" | "createdAt">>
    ): void {
      list.value = list.value.map((c) => {
        if (c.id !== id) return c;
        const next = { ...c };
        if (patch.name !== undefined) next.name = patch.name.trim();
        if (patch.symbols !== undefined) {
          next.symbols = [...new Set(patch.symbols.map((s) => s.toUpperCase()))];
        }
        return next;
      });
    }

    function remove(id: string): void {
      list.value = list.value.filter((c) => c.id !== id);
    }

    function getById(id: string): CustomCategory | undefined {
      return list.value.find((c) => c.id === id);
    }

    /** Remove a symbol from every category — used when user un-watches it. */
    function pruneSymbol(symbol: string): void {
      const sym = symbol.toUpperCase();
      list.value = list.value.map((c) => ({
        ...c,
        symbols: c.symbols.filter((s) => s !== sym),
      }));
    }

    return { list, create, update, remove, getById, pruneSymbol };
  },
  {
    persist: {
      storage: localStorage,
      // Default JSON serializer is fine — array of plain objects
    },
  }
);
