"""
ingest.py — Cron worker. Fetch RSS, classify, dedupe, write to Supabase.

Pipeline:
    1. Verify DB connection (fail fast if unreachable)
    2. Pre-load last-24h SimHashes AND MinHashes into in-memory pools
    3. Build LSH index over MinHashes
    4. Parallel-fetch all RSS sources
    5. Per article:
       a. Classify (drop if no theme matches)
       b. Compute SimHash → reject if Hamming ≤ 6 to anything in pool
       c. Compute MinHash → reject if LSH+Jaccard ≥ 0.6 to anything in pool
       d. Insert; add new signatures to both pools so within-run dups also catch
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

from config import RSS_SOURCES, yahoo_finance_ticker_rss
from classify import classify
from db import (
    get_conn,
    upsert_article,
    load_recent_simhashes,
    load_recent_minhashes,
    load_watchlist_symbols,
)
from dedupe import (
    simhash,
    to_signed_bigint,
    find_near_duplicate,
    make_minhash,
    serialize_minhash,
    deserialize_minhash,
    MinHashLSH,
    find_near_dup_minhash,
    JACCARD_THRESHOLD,
)
import sentiment as _sentiment


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


def _ticker_from_source_name(source_name: str) -> str | None:
    """Parse 'Yahoo:NVDA' → 'nvda'. Returns None if not a per-ticker source."""
    if source_name.startswith("Yahoo:"):
        sym = source_name.split(":", 1)[1].strip().lower()
        if sym.isalpha() and 1 <= len(sym) <= 6:
            return sym
    return None


def fetch_one(source: dict) -> list[dict]:
    feed = feedparser.parse(source["url"])
    auto_label = _ticker_from_source_name(source["name"])
    out = []
    for entry in feed.entries:
        link = entry.get("link", "")
        title = _strip_html(entry.get("title", ""))
        summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))
        if not link or not title:
            continue
        text = f"{title}. {summary}"
        result = classify(text)
        labels = list(result["labels"])
        scores = dict(result["scores"])

        # Auto-tag from per-ticker sources (Yahoo:NVDA → 'nvda').
        # Lets dynamic watchlist tickers like BABA tag without keyword config.
        if auto_label and auto_label not in labels:
            labels.append(auto_label)
            scores.setdefault(auto_label, 3.0)  # match high-confidence weight

        if not labels:
            continue
        out.append({
            "url_hash":  _hash_url(link),
            "url":       link,
            "title":     title,
            "summary":   summary[:600],
            "published": _parse_date(entry),
            "source":    source["name"],
            "labels":    labels,
            "scores":    scores,
        })
    return out


def build_dynamic_sources(conn) -> list[dict]:
    """Pull watchlist tickers from DB and emit Yahoo Finance RSS source entries."""
    syms = load_watchlist_symbols(conn)
    return [
        {"name": f"Yahoo:{sym}", "url": yahoo_finance_ticker_rss(sym)}
        for sym in syms
    ]


def merge_sources(static_sources: list[dict], dynamic_sources: list[dict]) -> list[dict]:
    """Combine, dedupe by URL (some watchlist tickers may overlap with static)."""
    seen = set()
    out = []
    for s in static_sources + dynamic_sources:
        if s["url"] in seen:
            continue
        seen.add(s["url"])
        out.append(s)
    return out


def safe_fetch(source: dict) -> list[dict]:
    try:
        return fetch_one(source)
    except Exception as e:
        log(f"[ingest] {source['name']} FAILED: {e}")
        return []


def main() -> None:
    started = datetime.now(timezone.utc)
    log(f"[ingest] starting at {started.isoformat()}")

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

    # ----- Phase 2: load existing dedup state -----
    log("[ingest] loading recent SimHashes + MinHashes...")
    try:
        with get_conn() as conn:
            sh_pool = load_recent_simhashes(conn, hours=24)
            mh_rows = load_recent_minhashes(conn, hours=24)
    except Exception as e:
        log(f"[ingest] failed to load dedup state "
            f"(did you run migration_003 yet?): {e}")
        sh_pool, mh_rows = [], []

    # Deserialize MinHashes and build LSH index
    mh_pool: dict[str, object] = {}
    lsh = MinHashLSH(threshold=JACCARD_THRESHOLD)
    for aid, blob in mh_rows:
        try:
            mh = deserialize_minhash(blob)
            mh_pool[str(aid)] = mh
            lsh.insert(str(aid), mh)
        except Exception as e:
            log(f"[ingest] bad minhash for id={aid}: {e}")
    log(f"[ingest] dedup pool — SimHash:{len(sh_pool)} MinHash:{len(mh_pool)} "
        f"(LSH bands={lsh.b}, rows/band={lsh.r})")

    # ----- Phase 2.5: merge static + dynamic (watchlist) RSS sources -----
    try:
        with get_conn() as conn:
            dyn = build_dynamic_sources(conn)
        sources = merge_sources(RSS_SOURCES, dyn)
        log(f"[ingest] sources — static:{len(RSS_SOURCES)} "
            f"dynamic:{len(dyn)} merged:{len(sources)}")
    except Exception as e:
        log(f"[ingest] failed to load watchlist tickers (using static only): {e}")
        sources = RSS_SOURCES

    # ----- Phase 3: parallel RSS fetch -----
    log("[ingest] fetching RSS sources in parallel...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        all_articles: list[dict] = []
        for arts in ex.map(safe_fetch, sources):
            all_articles.extend(arts)
    log(f"[ingest] fetched {len(all_articles)} candidate articles")

    # ----- Phase 4: dedupe + sentiment + insert -----
    inserted = url_dup = sh_dup = mh_dup = errors = 0
    sentiment_scored = sentiment_failed = 0
    sentiment_on = _sentiment.is_enabled()
    if not sentiment_on:
        log("[ingest] ANTHROPIC_API_KEY not set — skipping sentiment scoring")

    with get_conn() as conn:
        for art in all_articles:
            text = art["title"] + " " + art.get("summary", "")

            # 4a. SimHash check (cheap, catches verbatim reprints)
            sh_unsigned = simhash(text)
            if find_near_duplicate(sh_unsigned, sh_pool, SIMHASH_THRESHOLD) is not None:
                sh_dup += 1
                continue

            # 4b. MinHash + LSH check (pricier, catches paraphrased reprints)
            new_mh = make_minhash(text)
            if find_near_dup_minhash(new_mh, lsh, mh_pool, JACCARD_THRESHOLD):
                mh_dup += 1
                continue

            # 4c. Sentiment (best-effort, never blocks insert)
            #     Only pay the LLM cost for articles that survived dedupe.
            if sentiment_on:
                result = _sentiment.score_article(
                    art["title"], art.get("summary", "")
                )
                if result is not None:
                    art["sentiment_score"] = result["score"]
                    art["sentiment_confidence"] = result["confidence"]
                    art["sentiment_rationale"] = result["rationale"]
                    art["sentiment_model"] = result["model"]
                    art["sentiment_scored_at"] = result["scored_at"]
                    sentiment_scored += 1
                else:
                    sentiment_failed += 1

            # 4d. Insert
            art["simhash"] = to_signed_bigint(sh_unsigned)
            art["minhash_bytes"] = serialize_minhash(new_mh)
            try:
                new_id = upsert_article(conn, art)
                if new_id is not None:
                    inserted += 1
                    sh_pool.append(art["simhash"])
                    mh_pool[str(new_id)] = new_mh
                    lsh.insert(str(new_id), new_mh)
                else:
                    url_dup += 1
            except Exception as e:
                errors += 1
                log(f"[ingest] upsert failed for {art.get('url', '?')[:80]}: {e}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log(f"[ingest] done in {elapsed:.1f}s — "
        f"{inserted} new, {url_dup} url_dups, "
        f"{sh_dup} simhash_dups, {mh_dup} minhash_dups, {errors} errors")
    if sentiment_on:
        log(f"[ingest] sentiment — {sentiment_scored} scored, "
            f"{sentiment_failed} failed")


if __name__ == "__main__":
    main()
