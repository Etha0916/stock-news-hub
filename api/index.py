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
from datetime import datetime, timezone

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

# Make repo-root modules importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import THEMES, THEME_GROUPS  # noqa: E402
from db import query_articles, stats  # noqa: E402


app = FastAPI(title="Fin-Tech News Hub API",
              docs_url=None, redoc_url=None)

DOCS_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "docs"
))
INDEX_HTML = os.path.join(DOCS_DIR, "index.html")


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def root():
    if os.path.isfile(INDEX_HTML):
        return FileResponse(INDEX_HTML, media_type="text/html; charset=utf-8")
    return HTMLResponse(
        "<h1>News Hub</h1><p>Frontend bundle missing — try /api/articles.</p>",
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
    } for r in rows]

    return JSONResponse(
        content={
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "count":      len(articles),
            "articles":   articles,
        },
        headers={
            # 2 min edge cache + 1 min stale-while-revalidate.
            # Ingest runs every ~10 min, so users see at most ~3 min stale data.
            "Cache-Control": "public, s-maxage=120, stale-while-revalidate=60",
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
    return JSONResponse(
        content=payload,
        headers={
            "Cache-Control": "public, s-maxage=60, stale-while-revalidate=30",
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


@app.get("/api/candles/{ticker}")
def get_candles(
    ticker: str,
    resolution: str = Query(default="D", pattern="^(1|5|15|30|60|D|W|M)$"),
    days: int = Query(default=90, ge=1, le=365 * 2),
):
    """OHLCV daily candles for K-line chart. Sourced from Twelve Data."""
    sym = ticker.upper()

    try:
        candles = _twelve_candles(sym, days)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"twelvedata_failed: {e}", "ticker": sym},
        )

    if not candles:
        return JSONResponse(
            status_code=404,
            content={"error": "no_data", "ticker": sym},
        )

    if not candles:
        return JSONResponse(
            status_code=404,
            content={"error": "no_data", "ticker": sym},
        )

    cache_max = 300 if resolution in ("D", "W", "M") else 60
    return JSONResponse(
        content={"ticker": sym, "resolution": resolution, "candles": candles},
        headers={
            "Cache-Control": f"public, s-maxage={cache_max}, stale-while-revalidate=60",
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
