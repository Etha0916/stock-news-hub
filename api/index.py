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
# Yahoo Finance candle source.
# Finnhub's /stock/candle was paywalled in 2024 (free tier returns 403 for US
# stocks). Yahoo's public chart endpoint has no key requirement and no
# meaningful rate limit at our scale. It's the same source that the `yfinance`
# Python package wraps.
# ---------------------------------------------------------------------------
_YAHOO_CHART_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
# Browser-like UA — Yahoo soft-blocks obvious bot strings
_YAHOO_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _days_to_yahoo_range(days: int) -> str:
    if days <= 5:   return "5d"
    if days <= 30:  return "1mo"
    if days <= 90:  return "3mo"
    if days <= 180: return "6mo"
    if days <= 365: return "1y"
    return "2y"


def _yahoo_candles(symbol: str, days: int) -> list:
    range_str = _days_to_yahoo_range(days)
    url = f"{_YAHOO_CHART_BASE}/{symbol}?interval=1d&range={range_str}"
    req = urllib.request.Request(url, headers={"User-Agent": _YAHOO_UA})
    with urllib.request.urlopen(req, timeout=8) as resp:
        body = json.loads(resp.read())

    result_list = body.get("chart", {}).get("result") or []
    if not result_list:
        return []
    r = result_list[0]
    timestamps = r.get("timestamp") or []
    quote = (r.get("indicators", {}).get("quote") or [{}])[0]
    opens   = quote.get("open")   or []
    highs   = quote.get("high")   or []
    lows    = quote.get("low")    or []
    closes  = quote.get("close")  or []
    volumes = quote.get("volume") or []

    out = []
    for i, ts in enumerate(timestamps):
        # Holidays / half-trading days produce None entries — skip
        if i >= len(opens) or opens[i] is None:
            continue
        out.append({
            "time":   ts,
            "open":   opens[i],
            "high":   highs[i],
            "low":    lows[i],
            "close":  closes[i],
            "volume": volumes[i] or 0,
        })
    return out


@app.get("/api/candles/{ticker}")
def get_candles(
    ticker: str,
    resolution: str = Query(default="D", pattern="^(1|5|15|30|60|D|W|M)$"),
    days: int = Query(default=90, ge=1, le=365 * 2),
):
    """OHLCV daily candles for K-line chart. Sourced from Yahoo Finance."""
    sym = ticker.upper()

    try:
        candles = _yahoo_candles(sym, days)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"yahoo_failed: {e}", "ticker": sym},
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
