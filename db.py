"""
db.py — Supabase / Postgres connection + queries.

Uses psycopg v3 directly (no ORM) because our schema is small and the queries
are simple. Reads DATABASE_URL from environment.

For Vercel serverless: use the **Supabase Connection Pooler** URL (port 6543,
"transaction mode") — direct connections (port 5432) will exhaust the limit
under any real load. The pooler URL looks like:
    postgresql://postgres.XXX:PWD@aws-0-REGION.pooler.supabase.com:6543/postgres
"""
from __future__ import annotations

import os
import json
from contextlib import contextmanager
from typing import Iterable

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


def _db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to Vercel project env vars "
            "(for the API) and to GitHub Actions secrets (for ingest.py)."
        )
    return url


@contextmanager
def get_conn():
    url = _db_url()
    # Sanity check the URL — fail fast with a useful error if it's the wrong shape.
    # GitHub Actions has no IPv6, so the Direct connection (port 5432) hangs forever.
    # Always use the Transaction Pooler (port 6543).
    if ":5432/" in url and "pooler.supabase.com" not in url:
        raise RuntimeError(
            "DATABASE_URL points to Supabase Direct (port 5432). "
            "GitHub Actions runners are IPv4-only — Direct connections will hang. "
            "Use the Transaction Pooler URL (port 6543, host pooler.supabase.com)."
        )
    conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Write path — used by ingest.py
# Caller is responsible for connection lifecycle (one conn for the whole
# ingest run), so we don't pay 30 × connect-timeout if the DB is unreachable.
# ---------------------------------------------------------------------------
def upsert_article(conn, article: dict) -> str:
    """
    Insert if URL is new; skip if URL already exists. Returns:
        'inserted' — newly written
        'duplicate' — url_hash already in DB, no action

    `article` may carry an optional 'simhash' (signed 64-bit BIGINT-safe int).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO articles
              (url_hash, url, title, summary, published_at,
               source, labels, scores, simhash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (url_hash) DO NOTHING
            RETURNING id
            """,
            (
                article["url_hash"],
                article["url"],
                article["title"],
                article["summary"],
                article["published"],
                article["source"],
                article["labels"],
                Jsonb(article["scores"]),
                article.get("simhash"),
            ),
        )
        return "inserted" if cur.fetchone() else "duplicate"


def load_recent_simhashes(conn, hours: int = 24) -> list[int]:
    """
    Pull simhashes from the last `hours` for the in-memory dedup pool.
    Returned values are signed BIGINTs as stored in Postgres.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT simhash FROM articles
            WHERE published_at > NOW() - %s::interval
              AND simhash IS NOT NULL
            """,
            (f"{int(hours)} hours",),
        )
        return [row["simhash"] for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Read path — used by api/index.py
# ---------------------------------------------------------------------------
def query_articles(
    themes: Iterable[str] | None = None,
    days: int = 14,
    limit: int = 500,
) -> list[dict]:
    """
    Return articles within the last `days`, optionally filtered to those
    tagged with any of the given themes (OR semantics via array overlap).
    Newest first.
    """
    interval = f"{int(days)} days"
    with get_conn() as conn, conn.cursor() as cur:
        if themes:
            theme_list = list(themes)
            cur.execute(
                """
                SELECT id, url, title, summary, published_at,
                       source, labels, scores
                FROM articles
                WHERE published_at > NOW() - %s::interval
                  AND labels && %s
                ORDER BY published_at DESC
                LIMIT %s
                """,
                (interval, theme_list, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, url, title, summary, published_at,
                       source, labels, scores
                FROM articles
                WHERE published_at > NOW() - %s::interval
                ORDER BY published_at DESC
                LIMIT %s
                """,
                (interval, limit),
            )
        return cur.fetchall()


def stats() -> dict:
    """Quick health stats — used by /api/health."""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              COUNT(*)                         AS total,
              MAX(published_at)                AS newest,
              MIN(published_at)                AS oldest,
              COUNT(*) FILTER (
                WHERE published_at > NOW() - INTERVAL '24 hours'
              )                                AS last_24h
            FROM articles
            """
        )
        row = cur.fetchone()
        return {
            "total":   row["total"],
            "newest":  row["newest"].isoformat() if row["newest"] else None,
            "oldest":  row["oldest"].isoformat() if row["oldest"] else None,
            "last_24h": row["last_24h"],
        }
