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

from config import RSS_SOURCES
from classify import classify
from db import (
    get_conn,
    upsert_article,
    load_recent_simhashes,
    load_recent_minhashes,
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

    # ----- Phase 3: parallel RSS fetch -----
    log("[ingest] fetching RSS sources in parallel...")
    with ThreadPoolExecutor(max_workers=12) as ex:
        all_articles: list[dict] = []
        for arts in ex.map(safe_fetch, RSS_SOURCES):
            all_articles.extend(arts)
    log(f"[ingest] fetched {len(all_articles)} candidate articles")

    # ----- Phase 4: dedupe + insert -----
    inserted = url_dup = sh_dup = mh_dup = errors = 0
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

            # 4c. Insert
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


if __name__ == "__main__":
    main()
