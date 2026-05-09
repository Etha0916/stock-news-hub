/**
 * Watchlist store — user's personal list of ticker symbols.
 *
 * Persistence: localStorage now; Phase 6 migrates to server-side per-user.
 *
 * Two kinds of tickers can live here:
 *   1. PRESET tickers (already in config.py THEMES, e.g. NVDA, AAPL).
 *      These work immediately — articles for them are already classified.
 *   2. CUSTOM tickers (any US symbol, e.g. BABA). The user calls add(),
 *      which POSTs to /api/watchlist/register; the backend validates via
 *      Finnhub, registers globally, and inline-fetches the first batch of
 *      news so the user sees something within seconds.
 */
import { defineStore } from "pinia";
import { ref, computed } from "vue";

interface RegisterResponse {
  ok: boolean;
  symbol?: string;
  newly_registered?: boolean;
  fresh_articles?: number;
  current_price?: number;
  error?: string;
  detail?: string;
}

const TICKER_RE = /^[A-Za-z]{1,6}$/;

export const useWatchlistStore = defineStore(
  "watchlist",
  () => {
    // Always uppercase
    const symbols = ref<string[]>([]);

    const symbolsSet = computed(() => new Set(symbols.value));

    function isWatched(sym: string): boolean {
      return symbolsSet.value.has(sym.toUpperCase());
    }

    /** Add a ticker locally without backend round-trip. Used for preset
     *  tickers (already classified) and "+ all from group" bulk adds. */
    function addLocal(sym: string): void {
      const s = sym.toUpperCase();
      if (!symbolsSet.value.has(s)) {
        symbols.value = [...symbols.value, s];
      }
    }

    function addLocalMany(syms: string[]): void {
      const next = new Set(symbolsSet.value);
      for (const s of syms) {
        if (TICKER_RE.test(s)) next.add(s.toUpperCase());
      }
      symbols.value = [...next];
    }

    /** Add a (potentially custom) ticker. Validates with backend, registers
     *  globally, returns success/error. */
    async function add(sym: string): Promise<RegisterResponse> {
      const s = sym.toUpperCase().trim();
      if (!TICKER_RE.test(s)) {
        return { ok: false, error: "invalid_symbol" };
      }
      if (symbolsSet.value.has(s)) {
        return { ok: false, error: "already_added" };
      }
      try {
        const res = await fetch("/api/watchlist/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol: s }),
        });
        const data: RegisterResponse = await res.json();
        if (!res.ok) {
          return { ok: false, error: data.error ?? `http_${res.status}` };
        }
        // Persist locally
        addLocal(s);
        return { ok: true, ...data };
      } catch (e) {
        return {
          ok: false,
          error: "network_error",
          detail: e instanceof Error ? e.message : String(e),
        };
      }
    }

    function remove(sym: string): void {
      const s = sym.toUpperCase();
      symbols.value = symbols.value.filter((x) => x !== s);
    }

    function clear(): void {
      symbols.value = [];
    }

    return {
      symbols,
      symbolsSet,
      isWatched,
      add,
      addLocal,
      addLocalMany,
      remove,
      clear,
    };
  },
  {
    persist: {
      storage: localStorage,
      serializer: {
        serialize: (state: Record<string, unknown>) =>
          JSON.stringify({ symbols: state.symbols }),
        deserialize: (s: string) => {
          try {
            const obj = JSON.parse(s);
            const arr = Array.isArray(obj.symbols) ? obj.symbols : [];
            return { symbols: arr.filter((x: unknown) => typeof x === "string") };
          } catch {
            return { symbols: [] };
          }
        },
      },
    },
  }
);
