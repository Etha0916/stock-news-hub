"""
api/index.py — Vercel serverless backend (FastAPI).

Exposes:
    GET /api/themes    — taxonomy (groups + themes)
    GET /api/articles  — on-demand RSS fetch + classify

Both responses set HTTP cache headers so Vercel's edge CDN caches them and the
function only actually runs on cache miss.
"""
from __future__ import annotations

import os
import sys
import re
import hashlib
from datetime import datetime, timezone
from time import mktime
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from fastapi.responses import JSONResponse

# Make repo-root modules (config.py, classify.py) importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import feedparser  # noqa: E402

from config import RSS_SOURCES, THEMES, THEME_GROUPS  # noqa: E402
from classify import classify  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers (copied/adapted from build.py)
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
             "&quot;": '"', "&#39;": "'"}


def _strip_html(s: str) -> str:
    if not s:
        return ""
    s = _TAG_RE.sub("", s)
    for k, v in _ENTITIES.items():
        s = s.replace(k, v)
    return s.strip()


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _parse_date(entry) -> str:
    for attr in ("published_parsed", "updated_parsed"):
        v = getattr(entry, attr, None)
        if v:
            try:
                return datetime.fromtimestamp(mktime(v), tz=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def _fetch_one(source: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    out = []
    for entry in feed.entries:
        link = entry.get("link", "")
        title = _strip_html(entry.get("title", ""))
        summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
        if not link or not title:
            continue
        text = f"{title}. {summary}"
        result = classify(text)
        if not result["labels"]:
            continue
        out.append({
            "id": _hash_url(link),
            "url": link,
            "title": title,
            "summary": summary[:600],
            "published": _parse_date(entry),
            "source": source["name"],
            "labels": result["labels"],
        })
    return out


def _safe_fetch(source: dict) -> list[dict]:
    try:
        return _fetch_one(source)
    except Exception as e:
        print(f"[articles] {source['name']} FAILED: {e}")
        return []


def fetch_all() -> list[dict]:
    seen: set[str] = set()
    articles: list[dict] = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        for arts in ex.map(_safe_fetch, RSS_SOURCES):
            for a in arts:
                if a["id"] not in seen:
                    seen.add(a["id"])
                    articles.append(a)
    articles.sort(key=lambda a: a["published"], reverse=True)
    return articles


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="Fin-Tech News Hub API")


@app.get("/api/themes")
def get_themes():
    payload = {
        "groups": THEME_GROUPS,
        "themes": {
            k: {
                "label_en": v["label_en"],
                "label_zh": v["label_zh"],
                "groups": v.get("groups", []),
            }
            for k, v in THEMES.items()
        },
    }
    return JSONResponse(
        content=payload,
        headers={
            # Themes barely change — cache aggressively
            "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/articles")
def get_articles():
    articles = fetch_all()
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": articles,
    }
    return JSONResponse(
        content=payload,
        headers={
            # Edge-cache 5 min; serve stale up to 60 s while revalidating
            "Cache-Control": "public, s-maxage=300, stale-while-revalidate=60",
            "Access-Control-Allow-Origin": "*",
        },
    )


@app.get("/api/health")
def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}
