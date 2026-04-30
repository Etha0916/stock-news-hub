"""
ingest.py — Cron worker. Fetch RSS, classify, write to Supabase.

Run by GitHub Actions every ~10 minutes (see .github/workflows/ingest.yml).
Idempotent: re-running on the same articles is a no-op (URL hash dedupe).

Local invocation:
    DATABASE_URL=postgresql://... python ingest.py
"""
from __future__ import annotations

import os
import re
import sys
import hashlib
from datetime import datetime, timezone
from time import mktime
from concurrent.futures import ThreadPoolExecutor

import feedparser

from config import RSS_SOURCES
from classify import classify
from db import upsert_article


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


def _parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed"):
        v = getattr(entry, attr, None)
        if v:
            try:
                return datetime.fromtimestamp(mktime(v), tz=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def fetch_one(source: dict) -> list[dict]:
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
            "url_hash":  _hash_url(link),
            "url":       link,
            "title":     title,
            "summary":   summary[:600],
            "published": _parse_date(entry),
            "source":    source["name"],
            "labels":    result["labels"],
            "scores":    result["scores"],
        })
    return out


def safe_fetch(source: dict) -> list[dict]:
    try:
        return fetch_one(source)
    except Exception as e:
        print(f"[ingest] {source['name']} FAILED: {e}", file=sys.stderr)
        return []


def main() -> None:
    started = datetime.now(timezone.utc)
    inserted = duplicate = errors = 0

    print(f"[ingest] starting at {started.isoformat()}; "
          f"{len(RSS_SOURCES)} sources")

    with ThreadPoolExecutor(max_workers=12) as ex:
        all_articles: list[dict] = []
        for arts in ex.map(safe_fetch, RSS_SOURCES):
            all_articles.extend(arts)

    print(f"[ingest] fetched {len(all_articles)} candidate articles")

    for art in all_articles:
        try:
            status = upsert_article(art)
            if status == "inserted":
                inserted += 1
            else:
                duplicate += 1
        except Exception as e:
            errors += 1
            print(f"[ingest] upsert failed for {art.get('url', '?')}: {e}",
                  file=sys.stderr)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    print(f"[ingest] done in {elapsed:.1f}s — "
          f"{inserted} new, {duplicate} dups, {errors} errors")


if __name__ == "__main__":
    main()
