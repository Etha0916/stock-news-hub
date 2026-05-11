/**
 * safeUrl — guard against javascript: / data: / vbscript: URL XSS.
 *
 * Article URLs come from RSS feeds and could in theory be attacker-shaped
 * (compromised feed, social-engineered redirect, etc.). Vue auto-escapes
 * HTML in template bindings BUT does NOT block dangerous protocols when
 * binding to `href`. This helper is the canonical "is it safe to navigate"
 * check used everywhere we render external links.
 */
const SAFE_PROTOCOLS = new Set(["http:", "https:"]);

export function safeUrl(url: string | null | undefined): string {
  if (!url) return "#";
  // Reject obvious garbage early
  const trimmed = url.trim();
  if (!trimmed) return "#";
  try {
    const parsed = new URL(trimmed);
    if (!SAFE_PROTOCOLS.has(parsed.protocol)) return "#";
    return parsed.toString();
  } catch {
    return "#"; // unparseable → drop
  }
}
