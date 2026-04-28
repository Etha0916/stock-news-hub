"""
build.py — Static-site builder.

Each run is stateless: fetches all RSS sources right now, classifies, writes
fresh JSON snapshots into docs/data/. The static frontend reads those JSON
files directly, so there is no backend at runtime.

Used by GitHub Actions on a 15-minute cron AND for local development:
    python build.py
    python -m http.server -d docs 8000
    # then open http://localhost:8000
"""
from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from time import mktime
from pathlib import Path

import feedparser

from config import THEMES, THEME_GROUPS, RSS_SOURCES
from classify import classify

DATA_DIR = Path(__file__).parent / "docs" / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
THEMES_PATH = DATA_DIR / "themes.json"

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
    """Return ISO 8601 string with UTC zone."""
    for attr in ("published_parsed", "updated_parsed"):
        v = getattr(entry, attr, None)
        if v:
            try:
                return datetime.fromtimestamp(mktime(v), tz=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


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
            "id": _hash_url(link),
            "url": link,
            "title": title,
            "summary": summary[:600],
            "published": _parse_date(entry),
            "source": source["name"],
            "labels": result["labels"],
            # scores left out of the public payload to keep file small;
            # uncomment to expose for debugging:
            # "scores": result["scores"],
        })
    return out


def fetch_all() -> list[dict]:
    seen: set[str] = set()
    articles: list[dict] = []
    ok = fail = 0
    for src in RSS_SOURCES:
        try:
            for art in fetch_one(src):
                if art["id"] not in seen:
                    seen.add(art["id"])
                    articles.append(art)
            ok += 1
        except Exception as e:
            fail += 1
            print(f"[build] {src['name']} FAILED: {e}")
    print(f"[build] sources: {ok} ok, {fail} failed; {len(articles)} unique articles")
    return articles


def themes_payload() -> dict:
    return {
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


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    articles = fetch_all()
    articles.sort(key=lambda a: a["published"], reverse=True)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(articles),
        "articles": articles,
    }
    ARTICLES_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    THEMES_PATH.write_text(
        json.dumps(themes_payload(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[build] wrote {len(articles)} articles to {ARTICLES_PATH}")


if __name__ == "__main__":
    main()
