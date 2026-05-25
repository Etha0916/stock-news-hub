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
import concurrent.futures
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

# Sentiment scoring concurrency. Claude Haiku 4.5 typical latency is 1-2s;
# at 4 workers we get ~50-100 articles/min. Tier 1 rate limit is 50 RPM so
# 4 is the safe ceiling. Don't bump without confirming a higher tier.
MAX_SENTIMENT_WORKERS = 4
# Hard cap on sentiment phase. Beyond this, remaining candidates are inserted
# with NULL sentiment. The GitHub Action's timeout-minutes:15 gives a 5-min
# buffer for dedupe + insert phases after sentiment finishes.
SENTIMENT_BUDGET_S = 600


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
    # 12h window (down from 24h) + LIMIT 5000 in db.py keep this query under
    # 5s even when article volume spikes. Older 24h entries that we miss are
    # still backstopped by the url_hash UNIQUE constraint at INSERT time.
    log("[ingest] loading recent SimHashes + MinHashes...")
    try:
        with get_conn() as conn:
            sh_pool = load_recent_simhashes(conn, hours=12)
            mh_rows = load_recent_minhashes(conn, hours=12)
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

    # ----- Phase 4: URL pre-check + dedupe + sentiment + insert -----
    # Split into phases so sentiment scoring (the slow I/O-bound part) can
    # run in parallel without serializing on dedupe or DB writes.
    sentiment_on = _sentiment.is_enabled()
    if not sentiment_on:
        log("[ingest] ANTHROPIC_API_KEY not set — skipping sentiment scoring")

    # ----- Phase 4-pre: URL pre-check (cheapest dedupe — skip DB-known URLs) -----
    # Without this, we pay sentiment API for articles whose url_hash is
    # already in DB. Recent dedup pool only spans 24h; older articles with
    # the same URL slip through SimHash/MinHash and only get caught at
    # INSERT time (after we already paid for sentiment scoring).
    url_skip = 0
    existing_url_hashes: set[str] = set()
    if all_articles:
        try:
            url_hashes = [a["url_hash"] for a in all_articles]
            with get_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    "SELECT url_hash FROM articles WHERE url_hash = ANY(%s)",
                    (url_hashes,),
                )
                existing_url_hashes = {row["url_hash"] for row in cur.fetchall()}
        except Exception as e:
            log(f"[ingest] URL pre-check failed (continuing without): {e}")

        before = len(all_articles)
        all_articles = [a for a in all_articles if a["url_hash"] not in existing_url_hashes]
        url_skip = before - len(all_articles)
        log(f"[ingest] URL pre-check — {url_skip} DB-known URLs filtered, "
            f"{len(all_articles)} truly new to dedupe")

    # ----- Phase 4a: dedupe (sequential, in-memory, fast) -----
    sh_dup = mh_dup = 0
    candidates: list[dict] = []  # articles that survived dedupe, ready for sentiment + insert
    for art in all_articles:
        text = art["title"] + " " + art.get("summary", "")
        sh_unsigned = simhash(text)
        if find_near_duplicate(sh_unsigned, sh_pool, SIMHASH_THRESHOLD) is not None:
            sh_dup += 1
            continue
        new_mh = make_minhash(text)
        if find_near_dup_minhash(new_mh, lsh, mh_pool, JACCARD_THRESHOLD):
            mh_dup += 1
            continue
        # Attach hash artifacts now so insert phase doesn't recompute
        art["simhash"] = to_signed_bigint(sh_unsigned)
        art["minhash_bytes"] = serialize_minhash(new_mh)
        art["_minhash_obj"] = new_mh  # for post-insert pool update; not persisted
        candidates.append(art)
        # In-run SimHash pool update so intra-run verbatim dups still get caught
        # (MinHash pool update needs an article id, so we defer that to insert phase)
        sh_pool.append(art["simhash"])

    log(f"[ingest] dedupe — sh_dup:{sh_dup} mh_dup:{mh_dup} "
        f"candidates:{len(candidates)} (out of {len(all_articles)} fetched)")

    # ----- Phase 4b: parallel sentiment scoring -----
    sentiment_scored = sentiment_failed = sentiment_skipped = 0
    if sentiment_on and candidates:
        log(f"[ingest] sentiment — scoring {len(candidates)} candidates "
            f"(workers={MAX_SENTIMENT_WORKERS}, budget={SENTIMENT_BUDGET_S}s)")
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_SENTIMENT_WORKERS
        ) as ex:
            futures = {
                ex.submit(_sentiment.score_article, a["title"], a.get("summary", "")): a
                for a in candidates
            }
            try:
                for future in concurrent.futures.as_completed(
                    futures, timeout=SENTIMENT_BUDGET_S
                ):
                    art = futures[future]
                    try:
                        result = future.result()
                    except Exception as e:
                        log(f"[sentiment] worker exception: {e}")
                        sentiment_failed += 1
                        continue
                    if result is not None:
                        art["sentiment_score"]      = result["score"]
                        art["sentiment_confidence"] = result["confidence"]
                        art["sentiment_rationale"]  = result["rationale"]
                        art["sentiment_model"]      = result["model"]
                        art["sentiment_scored_at"]  = result["scored_at"]
                        sentiment_scored += 1
                    else:
                        sentiment_failed += 1
            except concurrent.futures.TimeoutError:
                sentiment_skipped = sum(1 for f in futures if not f.done())
                log(f"[ingest] sentiment budget exceeded — "
                    f"{sentiment_skipped} candidates will be inserted with NULL sentiment")
                for f in futures:
                    if not f.done():
                        f.cancel()

    # ----- Phase 4c: sequential insert -----
    inserted = url_dup = errors = 0
    with get_conn() as conn:
        for art in candidates:
            try:
                new_id = upsert_article(conn, art)
                if new_id is not None:
                    inserted += 1
                    mh_obj = art.get("_minhash_obj")
                    if mh_obj is not None:
                        mh_pool[str(new_id)] = mh_obj
                        lsh.insert(str(new_id), mh_obj)
                else:
                    url_dup += 1
            except Exception as e:
                errors += 1
                log(f"[ingest] upsert failed for {art.get('url', '?')[:80]}: {e}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    log(f"[ingest] done in {elapsed:.1f}s — "
        f"{inserted} new, {url_skip} url_pre_skip, {url_dup} url_dup_at_insert, "
        f"{sh_dup} simhash_dups, {mh_dup} minhash_dups, {errors} errors")
    if sentiment_on:
        log(f"[ingest] sentiment — {sentiment_scored} scored, "
            f"{sentiment_failed} failed, {sentiment_skipped} skipped (budget)")


if __name__ == "__main__":
    main()
