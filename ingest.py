"""
ingest.py — Cron worker. Fetch RSS, classify, dedupe, write to Supabase.

Pipeline:
    1. Verify DB connection (fail fast if unreachable)
    2. Pre-load last-24h SimHashes into an in-memory pool
    3. Parallel-fetch all RSS sources
    4. Per article:  classify → drop if no labels → compute simhash →
       drop if Hamming-near to anything in pool → insert
       (and add the new simhash to pool for cross-feed dedup within the same run)

Local invocation:
    DATABASE_URL=postgresql://... python -u ingest.py
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
from db import get_conn, upsert_article, load_recent_simhashes
from dedupe import simhash, hamming, to_signed_bigint, find_near_duplicate


# Hamming threshold: empirically 6 is the safe choice for headline+summary.
# At threshold 6 we reliably catch identical reprints and tiny rewrites,
# without false-positively merging "Nvidia Q3 earnings" vs "AMD Q3 earnings"
# (which sit at Hamming ~13 in our test set). Tune by editing this constant.
SIMHASH_THRESHOLD = 6

_TAG_RE = re.compile(r"<[^>]+>")
_ENTITIES = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
             "&quot;": '"', "&#39;": "'"}


def log(msg: str) -> None:
    print(msg, flush=True)


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
        log(f"[ingest] {source['name']} FAILED: {e}")
        return []


def main() -> None:
    started = datetime.now(timezone.utc)
    log(f"[ingest] starting at {started.isoformat()}; "
        f"{len(RSS_SOURCES)} sources")

    # ----- Phase 1: verify DB connection -----
    log("[ingest] testing DB connection...")
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        log("[ingest] DB connection OK")
    except Exception as e:
        log(f"[ingest] DB connection FAILED: {type(e).__name__}: {e}")
        sys.exit(1)

    # ----- Phase 2: load existing simhashes for dedup -----
    log("[ingest] loading recent simhashes for dedup pool...")
    try:
        with get_conn() as conn:
            sh_pool = load_recent_simhashes(conn, hours=24)
        log(f"[ingest] dedup pool: {len(sh_pool)} simhashes from last 24h")
    except Exception as e:
        log(f"[ingest] failed to load simhashes (column may be missing — "
            f"did you run migration_002?): {e}")
        sh_pool = []

    # ----- Phase 3: parallel RSS fetch -----
    log("[ingest] fetching RSS sources in parallel...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        all_articles: list[dict] = []
        for arts in ex.map(safe_fetch, RSS_SOURCES):
            all_articles.extend(arts)
    log(f"[ingest] fetched {len(all_articles)} candidate articles")

    # ----- Phase 4: classify already done, dedupe, single-conn upsert -----
    inserted = url_dup = sem_dup = errors = 0
    with get_conn() as conn:
        for art in all_articles:
            text = art["title"] + " " + art.get("summary", "")
            sh_unsigned = simhash(text)

            # Semantic dedup: linear scan of last-24h pool
            if find_near_duplicate(sh_unsigned, sh_pool, SIMHASH_THRESHOLD) is not None:
                sem_dup += 1
                continue

            art["simhash"] = to_signed_bigint(sh_unsigned)
            try:
                status = upsert_article(conn, art)
                if status == "inserted":
                    inserted += 1
                    sh_pool.append(art["simhash"])  # widen pool for in-run dedup
                else:
                    url_dup += 1
            except Exception as e:
                errors += 1
                log(f"[ingest] upsert failed for {art.get('url', '?')[:80]}: {e}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log(f"[ingest] done in {elapsed:.1f}s — "
        f"{inserted} new, {url_dup} url_dups, {sem_dup} sem_dups, {errors} errors")


if __name__ == "__main__":
    main()
