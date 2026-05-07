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
# Stooq candle source.
#   - No API key, no auth, no rate limits (at our scale)
#   - Returns CSV: Date,Open,High,Low,Close,Volume (one daily bar per line)
#   - URL pattern: https://stooq.com/q/d/l/?s={symbol}.us&i=d
#   - Stable for 10+ years; common in quant open-source projects
# Yahoo's chart endpoint is too aggressively rate-limited from Vercel IPs;
# Finnhub paywalled candles in 2024. Stooq is the reliable middle ground.
# ---------------------------------------------------------------------------
_STOOQ_BASE = "https://stooq.com/q/d/l"
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _stooq_candles(symbol: str, days: int) -> list:
    """Fetch daily OHLCV from Stooq, return last `days` bars (oldest-first)."""
    # US tickers on Stooq use a `.us` suffix
    s = f"{symbol.lower()}.us"
    url = f"{_STOOQ_BASE}/?s={s}&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": _BROWSER_UA})
    with urllib.request.urlopen(req, timeout=8) as resp:
        text = resp.read().decode("utf-8", errors="replace")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return []

    # First line is the header: "Date,Open,High,Low,Close,Volume"
    cutoff_ts = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    out = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 6:
            continue
        try:
            dt = datetime.strptime(parts[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            ts = int(dt.timestamp())
            if ts < cutoff_ts:
                continue
            out.append({
                "time":   ts,
                "open":   float(parts[1]),
                "high":   float(parts[2]),
                "low":    float(parts[3]),
                "close":  float(parts[4]),
                "volume": int(parts[5]) if parts[5] and parts[5].isdigit() else 0,
            })
        except (ValueError, IndexError):
            continue

    # lightweight-charts wants oldest-first
    out.sort(key=lambda c: c["time"])
    return out


@app.get("/api/candles/{ticker}")
def get_candles(
    ticker: str,
    resolution: str = Query(default="D", pattern="^(1|5|15|30|60|D|W|M)$"),
    days: int = Query(default=90, ge=1, le=365 * 2),
):
    """OHLCV daily candles for K-line chart. Sourced from Stooq."""
    sym = ticker.upper()

    try:
        candles = _stooq_candles(sym, days)
    except Exception as e:
        return JSONResponse(
            status_code=502,
            content={"error": f"stooq_failed: {e}", "ticker": sym},
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
