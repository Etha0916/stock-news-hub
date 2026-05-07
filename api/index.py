"""
api/index.py — Vercel serverless backend (FastAPI).

Reads articles from Supabase (no RSS fetch in the request path), so responses
are 50–200 ms even on cache miss. RSS ingestion is decoupled into ingest.py
which runs on GitHub Actions cron.

Routes:
    GET /                — serves docs/index.html (the SPA)
    GET /api/themes      — taxonomy (groups + themes from config.py)
    GET /api/articles    — articles from DB, optionally filtered + paginated
    GET /api/health      — DB stats
"""
from __future__ import annotations

import os
import sys
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone, time as dtime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Make repo-root modules importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import THEMES, THEME_GROUPS  # noqa: E402
from db import query_articles, stats  # noqa: E402


app = FastAPI(title="Fin-Tech News Hub API",
              docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# Cache strategy — different freshness needs per endpoint.
# Quote / intraday candles are aggressive during market hours, relaxed at night.
# Themes (config-derived) cache for a day. Articles cache for a minute with
# generous stale-while-revalidate so most visitors hit the edge.
# ---------------------------------------------------------------------------
_ET = ZoneInfo("America/New_York")  # auto handles DST


def us_market_state(now_utc: datetime | None = None) -> str:
    """Return one of: 'open', 'pre', 'after', 'closed'. ET-based, DST-aware."""
    now = (now_utc or datetime.now(tz=timezone.utc)).astimezone(_ET)
    if now.weekday() >= 5:
        return "closed"
    t = now.time()
    if dtime(4, 0) <= t < dtime(9, 30):  return "pre"
    if dtime(9, 30) <= t < dtime(16, 0): return "open"
    if dtime(16, 0) <= t < dtime(20, 0): return "after"
    return "closed"


def quote_cache_seconds() -> int:
    state = us_market_state()
    if state == "open":   return 30
    if state in ("pre", "after"):  return 120
    return 3600  # closed: an hour is plenty


def candle_cache_seconds(resolution: str) -> int:
    state = us_market_state()
    intraday = resolution in ("1", "5", "15", "30", "60")
    if intraday:
        return 60 if state == "open" else 600
    # daily / weekly / monthly
    return 300 if state == "open" else 21600  # 6h after close

DOCS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs"
))
INDEX_HTML = os.path.join(DOCS_DIR, "index.html")


# ---------------------------------------------------------------------------
# Frontend (Vue SPA built by Vite into docs/)
# Vite emits docs/index.html + docs/assets/<hashed>.js + .css
# ---------------------------------------------------------------------------
ASSETS_DIR = os.path.join(DOCS_DIR, "assets")

# Mount /assets/* directly to docs/assets so Vite's hashed bundles are served
# with proper cache headers and 200 responses (not via the catch-all).
if os.path.isdir(ASSETS_DIR):
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", response_class=HTMLResponse)
def root():
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")
    return HTMLResponse(
        "<h1>News Hub</h1><p>Frontend bundle missing — run `npm run build`.</p>",
        status_code=200,
    )


# ---------------------------------------------------------------------------
# /api/themes — config-derived, basically static
# ---------------------------------------------------------------------------
@app.get("/api/themes")
def get_themes():
    payload = {
        "groups": THEME_GROUPS,
        "themes": {
            k: {
                "label_en": v["label_en"],
                "label_zh": v["label_zh"],
                "groups":   v.get("groups", []),
            }
            for k, v in THEMES.items()
        },
    }
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# /api/articles — DB read
# ---------------------------------------------------------------------------
@app.get("/api/articles")
def get_articles(
    themes: str | None = Query(default=None,
                                description="Comma-separated theme keys"),
    days: int = Query(default=14, ge=1, le=90),
    limit: int = Query(default=500, ge=1, le=2000),
):
    theme_list = (
        [t.strip() for t in themes.split(",") if t.strip()]
        if themes else None
    )
    rows = query_articles(theme_list, days=days, limit=limit)

    articles = [{
        "id":        r["id"],
        "url":       r["url"],
        "title":     r["title"],
        "summary":   r["summary"],
        "published": r["published_at"].isoformat() if r["published_at"] else None,
        "source":    r["source"],
        "labels":    r["labels"],
        "scores":    r.get("scores") or {},   # per-theme classifier scores
    } for r in rows]

    return JSONResponse(
        content={
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count":      len(articles),
            "articles":   articles,
        },
        headers={
            # 60s edge cache, 5min stale-while-revalidate. Ingest cron is ~10min,
            # so most visitors hit the edge while a few trigger background revalidation.
            "Cache-Control": "public, s-maxage=60, stale-while-revalidate=300",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# Finnhub proxy — quote + candles
# We proxy Finnhub server-side so:
#   (a) the API key never reaches the browser
#   (b) edge cache amortizes Finnhub rate-limit (60 calls/min on free tier)
# ---------------------------------------------------------------------------
FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")
FINNHUB_BASE = "https://finnhub.io/api/v1"


def _finnhub_get(path: str, params: dict) -> dict:
    if not FINNHUB_KEY:
        raise RuntimeError("FINNHUB_API_KEY env var is not set")
    params["token"] = FINNHUB_KEY
    qs = urllib.parse.urlencode(params)
    url = f"{FINNHUB_BASE}{path}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "stock-news-hub/0.1"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read())


@app.get("/api/quote/{ticker}")
def get_quote(ticker: str):
    """Real-time quote for a US-listed stock."""
    sym = ticker.upper()
    try:
        data = _finnhub_get("/quote", {"symbol": sym})
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"finnhub_failed: {e}", "ticker": sym},
        )

    # Finnhub /quote keys: c=current, d=change, dp=change%, h=high, l=low,
    # o=open, pc=prev close, t=timestamp
    ts_unix = data.get("t") or 0
    payload = {
        "ticker": sym,
        "price": data.get("c"),
        "change": data.get("d"),
        "change_pct": data.get("dp"),
        "high": data.get("h"),
        "low": data.get("l"),
        "open": data.get("o"),
        "prev_close": data.get("pc"),
        "ts": (
            datetime.fromtimestamp(ts_unix, tz=timezone.utc).isoformat()
            if ts_unix else None
        ),
    }
    s_max = quote_cache_seconds()
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": f"public, s-maxage={s_max}, stale-while-revalidate={s_max * 4}",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# Twelve Data candle source.
#   - 800 calls/day free tier, 8 calls/minute
#   - With our 5-min edge cache, 11 tickers × 1 day worst-case ~110 calls/day
#   - Returns JSON, newest-first; we flip oldest-first for lightweight-charts
# Why not the others:
#   Finnhub /stock/candle  → paywalled (2024)
#   Yahoo  /v8/finance/chart → 429 from Vercel IPs
#   Stooq  daily CSV       → now requires captcha-issued apikey
# ---------------------------------------------------------------------------
TWELVE_DATA_KEY = os.environ.get("TWELVE_DATA_API_KEY", "")
_TWELVE_BASE = "https://api.twelvedata.com"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _twelve_candles(symbol: str, days: int) -> list:
    if not TWELVE_DATA_KEY:
        raise RuntimeError("TWELVE_DATA_API_KEY env var is not set")

    # outputsize = number of bars; cap at 5000 (API max)
    outputsize = min(max(days, 5), 5000)
    params = {
        "symbol":     symbol,
        "interval":   "1day",
        "outputsize": str(outputsize),
        "apikey":     TWELVE_DATA_KEY,
        "format":     "JSON",
    }
    url = f"{_TWELVE_BASE}/time_series?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())

    if data.get("status") != "ok":
        raise RuntimeError(
            f"twelvedata: {data.get('code', '?')} {data.get('message', 'unknown')}"
        )

    values = data.get("values") or []
    out = []
    for v in values:
        try:
            dt = datetime.strptime(v["datetime"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
            out.append({
                "time":   int(dt.timestamp()),
                "open":   float(v["open"]),
                "high":   float(v["high"]),
                "low":    float(v["low"]),
                "close":  float(v["close"]),
                "volume": int(float(v.get("volume") or 0)),
            })
        except (KeyError, ValueError):
            continue

    # API returns newest-first; lightweight-charts wants oldest-first
    out.sort(key=lambda c: c["time"])
    return out


# ---------------------------------------------------------------------------
# Yahoo Finance fallback. Same chart endpoint we tried before — when
# Twelve Data fails, we still try Yahoo. Often works on a retry from a
# different Vercel region even if the previous call 429'd.
# ---------------------------------------------------------------------------
_YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart"


def _days_to_yahoo_range(days: int) -> str:
    if days <= 5:   return "5d"
    if days <= 30:  return "1mo"
    if days <= 90:  return "3mo"
    if days <= 180: return "6mo"
    if days <= 365: return "1y"
    return "2y"


def _yahoo_candles(symbol: str, days: int) -> list:
    range_str = _days_to_yahoo_range(days)
    url = f"{_YAHOO_CHART}/{symbol}?interval=1d&range={range_str}"
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = json.loads(resp.read())

    rs = body.get("chart", {}).get("result") or []
    if not rs:
        return []
    r = rs[0]
    ts_arr = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    out = []
    for i, ts in enumerate(ts_arr):
        if i >= len(o) or o[i] is None:
            continue
        out.append({"time": ts, "open": o[i], "high": h[i],
                    "low": l[i], "close": c[i], "volume": v[i] or 0})
    return out


# ---------------------------------------------------------------------------
# Fallback chain. Order matters: paid quota first, free fallbacks after.
# Returns (candles, source_name). Raises if every provider fails.
# ---------------------------------------------------------------------------
def _candles_with_fallback(symbol: str, days: int) -> tuple[list, str, list[str]]:
    errors: list[str] = []
    for name, fn in [("twelvedata", _twelve_candles), ("yahoo", _yahoo_candles)]:
        try:
            data = fn(symbol, days)
            if data:
                return data, name, errors
            errors.append(f"{name}: empty")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {e}")
    return [], "none", errors


@app.get("/api/candles/{ticker}")
def get_candles(
    ticker: str,
    resolution: str = Query(default="D", pattern="^(1|5|15|30|60|D|W|M)$"),
    days: int = Query(default=90, ge=1, le=365 * 2),
):
    """OHLCV daily candles. Falls back through provider chain on failure."""
    sym = ticker.upper()
    candles, source, errors = _candles_with_fallback(sym, days)

    if not candles:
        return JSONResponse(
            status_code=502,
            content={"error": "all_providers_failed", "ticker": sym, "tried": errors},
        )

    if not candles:
        return JSONResponse(
            status_code=404,
            content={"error": "no_data", "ticker": sym},
        )

    s_max = candle_cache_seconds(resolution)
    return JSONResponse(
        content={
            "ticker": sym,
            "resolution": resolution,
            "candles": candles,
            "source": source,  # observability — which provider answered
        },
        headers={
            "Cache-Control": f"public, s-maxage={s_max}, stale-while-revalidate={s_max * 6}",
            "Access-Control-Allow-Origin": "*",
        },
    )


# ---------------------------------------------------------------------------
# /api/health — operational sanity check
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    try:
        return {
            "ok": True,
            "ts": datetime.now(timezone.utc).isoformat(),
            "db": stats(),
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"ok": False, "error": str(e)},
        )


# ---------------------------------------------------------------------------
# SPA fallback (must be the LAST route — catches everything not matched above)
#
# Vue Router uses createWebHistory(), so direct hits to /ticker/NVDA or
# /bookmarks need to return index.html (the client-side router takes over).
# We also serve top-level static files like favicon.ico, robots.txt,
# manifest.json from docs/ if they exist.
# ---------------------------------------------------------------------------
@app.get("/{full_path:path}")
def spa_fallback(full_path: str):
    # Specific files at docs/ root (favicon, robots, manifest, etc.)
    if full_path:
        candidate = os.path.normpath(os.path.join(DOCS_DIR, full_path))
        # Defense: prevent path-traversal escaping DOCS_DIR
        if candidate.startswith(DOCS_DIR) and os.path.isfile(candidate):
            return FileResponse(candidate)
    # Otherwise it's a client-side route → serve the SPA shell
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")
    return HTMLResponse("Frontend not built yet", status_code=404)
