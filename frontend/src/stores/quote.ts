/**
 * Quote store — per-ticker price + candles cache.
 *
 * Both quote and candles come from Finnhub via /api/quote/* and /api/candles/*
 * (proxied server-side so the API key stays secret + edge-cached for cost).
 *
 * Cache shape: keyed by uppercase ticker symbol. Once fetched, kept in memory
 * for the session — refetch by calling fetchQuote/fetchCandles again.
 */
import { defineStore } from "pinia";
import { ref } from "vue";
import type { Quote, Candle } from "@/types";
import { apiGet } from "@/composables/useApi";

interface CandleResponse {
  ticker: string;
  resolution: string;
  candles: Candle[];
}

export const useQuoteStore = defineStore("quote", () => {
  const quotes = ref<Record<string, Quote>>({});
  const candles = ref<Record<string, Candle[]>>({});
  const loading = ref<Record<string, boolean>>({});
  const errors = ref<Record<string, string | null>>({});

  async function fetchQuote(symbol: string) {
    const sym = symbol.toUpperCase();
    if (loading.value[`q:${sym}`]) return;
    loading.value = { ...loading.value, [`q:${sym}`]: true };
    errors.value = { ...errors.value, [`q:${sym}`]: null };
    try {
      const data = await apiGet<Quote>(`/api/quote/${sym}`);
      quotes.value = { ...quotes.value, [sym]: data };
    } catch (e) {
      errors.value = {
        ...errors.value,
        [`q:${sym}`]: e instanceof Error ? e.message : "Unknown error",
      };
    } finally {
      loading.value = { ...loading.value, [`q:${sym}`]: false };
    }
  }

  async function fetchCandles(symbol: string, days = 90) {
    const sym = symbol.toUpperCase();
    const key = `c:${sym}:${days}`;
    if (loading.value[key]) return;
    loading.value = { ...loading.value, [key]: true };
    errors.value = { ...errors.value, [key]: null };
    try {
      const data = await apiGet<CandleResponse>(
        `/api/candles/${sym}?days=${days}&resolution=D`
      );
      candles.value = { ...candles.value, [sym]: data.candles };
    } catch (e) {
      errors.value = {
        ...errors.value,
        [key]: e instanceof Error ? e.message : "Unknown error",
      };
    } finally {
      loading.value = { ...loading.value, [key]: false };
    }
  }

  function isLoadingQuote(sym: string) {
    return !!loading.value[`q:${sym.toUpperCase()}`];
  }
  function isLoadingCandles(sym: string) {
    return Object.keys(loading.value).some(
      (k) => k.startsWith(`c:${sym.toUpperCase()}:`) && loading.value[k]
    );
  }

  function quoteError(sym: string) {
    return errors.value[`q:${sym.toUpperCase()}`] ?? null;
  }
  function candleError(sym: string) {
    return Object.entries(errors.value).find(
      ([k, v]) => k.startsWith(`c:${sym.toUpperCase()}:`) && v
    )?.[1] ?? null;
  }

  return {
    quotes,
    candles,
    fetchQuote,
    fetchCandles,
    isLoadingQuote,
    isLoadingCandles,
    quoteError,
    candleError,
  };
});
