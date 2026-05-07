/**
 * Centralized API access. All fetch calls go through here so that:
 *   - Phase 5 auth: adding `Authorization: Bearer ${token}` is one-line
 *   - B2B: org-scoped endpoints add their headers here, not per-component
 *   - Errors are normalized
 */

const API_BASE = ""; // dev: Vite proxies /api → Vercel; prod: same origin

class ApiError extends Error {
  constructor(public status: number, public path: string, message: string) {
    super(`API ${path} ${status}: ${message}`);
    this.name = "ApiError";
  }
}

function buildHeaders(): HeadersInit {
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  // Future: const token = useAuthStore().token; if (token) headers.Authorization = `Bearer ${token}`;
  return headers;
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: buildHeaders(),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new ApiError(res.status, path, text.slice(0, 200));
  }
  return (await res.json()) as T;
}

export { ApiError };
