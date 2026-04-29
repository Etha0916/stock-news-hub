"""
api/articles.py — Vercel serverless function: /api/articles

Fetches every RSS source on demand, classifies, returns JSON.
Edge-cached for 5 minutes via Cache-Control headers, so the function
itself only actually runs at most once every ~5 minutes per region.
"""
from __future__ import annotations

import json
import os
import sys
import re
import hashlib
from datetime import datetime, timezone
from time import mktime
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

# Make repo-root modules (config.py, classify.py) importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import feedparser  # noqa: E402

from config import RSS_SOURCES  # noqa: E402
from classify import classify  # noqa: E402


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
    """Fetch every source in parallel, dedupe, sort newest-first."""
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


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            articles = fetch_all()
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "count": len(articles),
                "articles": articles,
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            # Edge-cache for 5 min; serve stale up to 60s while revalidating
            self.send_header("Cache-Control",
                             "public, s-maxage=300, stale-while-revalidate=60")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err)
