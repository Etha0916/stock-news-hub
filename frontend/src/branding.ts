/**
 * Centralized brand strings.
 * Phase 5 will add a server-side `org_branding` lookup so multi-tenant B2B
 * customers can override these per organization. Until then, all UI strings
 * live here so renaming the product is a one-file change.
 */
export const BRAND = {
  appName_zh: "Stock News Hub",
  appName_en: "Stock News Hub",
  tagline_zh: "美股 + 半導體 + 台廠 + AI + 聯準會,一頁看完",
  tagline_en: "Mag7 · Semis · Taiwan Tech · AI · Fed — one feed",
  emoji: "📈",
  copyright: "© 2026",
  // Future: org-level overrides via API
} as const;
