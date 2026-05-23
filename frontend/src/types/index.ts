/**
 * Shared TypeScript types — single source of truth for the app's domain model.
 * These mirror the JSON shapes returned by /api/themes and /api/articles
 * (see api/index.py).
 */

export interface Theme {
  label_en: string;
  label_zh: string;
  groups: string[];
}

export interface ThemeGroup {
  label_en: string;
  label_zh: string;
}

export interface ThemesPayload {
  groups: Record<string, ThemeGroup>;
  themes: Record<string, Theme>;
}

export interface Article {
  id: number;
  url: string;
  title: string;
  summary: string | null;
  published: string | null; // ISO 8601
  source: string;
  labels: string[];
  scores?: Record<string, number>; // per-theme classifier scores
  // Sentiment (added in migration 006; null for older articles)
  sentiment_score?: number | null;       // -1.0 .. +1.0
  sentiment_confidence?: number | null;  // 0.0 .. 1.0
  sentiment_rationale?: string | null;
}

export type SortMode = "time" | "relevance";

/** A user-created group of tickers (like a private Mag7). Stored in
 *  localStorage now; will move to server-side per-user in Phase 6. */
export interface CustomCategory {
  id: string;        // crypto.randomUUID()
  name: string;      // user-chosen, e.g. "我的 AI 板塊"
  symbols: string[]; // uppercase tickers, e.g. ["NVDA", "AAPL", "PLTR"]
  createdAt: number; // ms epoch
}

export interface ArticlesPayload {
  updated_at: string;
  count: number;
  articles: Article[];
}

export type Lang = "zh" | "en";

/** Per-ticker quote returned by /api/quote/:ticker (Phase 4 stage 4). */
export interface Quote {
  ticker: string;
  price: number;
  change: number;
  change_pct: number;
  high: number;
  low: number;
  open: number;
  prev_close: number;
  ts: string;
}

/** Single OHLCV bar for K-line. */
export interface Candle {
  time: number; // unix seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
