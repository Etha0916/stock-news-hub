# Fin-Tech News Hub

A personal financial news aggregator that pulls 30+ RSS feeds, classifies
each article into themes you care about — **Mag7**, **ELN underlyings**,
**Semiconductors**, **Taiwan Tech**, **AI**, and **Fed Rates** — both English
and Traditional Chinese.

## Quick start

```bash
cd news_hub
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:8000> in your browser.

The app fetches feeds on startup, then re-polls every 5 minutes in the
background. Click **Refresh** for an on-demand pull.

## Files

| File | Purpose |
|---|---|
| `app.py`           | FastAPI server + APScheduler + serves the frontend |
| `config.py`        | Theme keywords + RSS source URLs (your tuning surface) |
| `classify.py`      | Multi-label keyword classifier |
| `ingest.py`        | RSS fetch + HTML cleaning + persistence |
| `db.py`            | SQLite schema and queries |
| `static/index.html` | Single-page frontend (vanilla JS) |
| `news.db`          | Created on first run — your local article store |

## How it works

```
APScheduler (every 5 min)
       │
       ▼
  ingest.py  ──►  feedparser fetches each RSS in config.py
       │              │
       │              ▼
       │         classify.py  ──►  scores each article against every theme,
       │                          emits zero or more labels
       │
       ▼
  db.py UPSERT  ──►  news.db  (SQLite, single table)
                          │
                          ▼
                    GET /api/articles
                          │
                          ▼
                   static/index.html
                   (renders cards, theme filter,
                    EN / 繁中 language toggle)
```

### Classifier

For each theme `c` we keep a set of keywords with weights:

```
score(article, theme) = Σ_{k ∈ keywords_high(c)} 3·[k ∈ article]
                      + Σ_{k ∈ keywords_med(c)}  1·[k ∈ article]

label article with theme c  if  score >= 1.5
```

So one strong keyword (`TSMC`, `FOMC`) or two weak ones (`chip`, `foundry`)
tags the article. Multi-label: an Nvidia AI chip article gets `nvda`, `semi`,
and `ai` simultaneously.

Themes and keyword sets live entirely in `config.py` — adding a theme or
tuning a keyword is a one-line edit. No retraining, no labeled data.

### RSS sources

30+ feeds across Reuters, Bloomberg, CNBC, MarketWatch, Investing.com,
經濟日報, 工商時報, Anue 鉅亨, plus Google News per-theme queries. Full list
in `config.py` under `RSS_SOURCES`.

### Frontend

Vanilla JS, no build step. `index.html` calls `/api/articles`, renders cards,
provides:

- Theme filter (click a chip to filter)
- Language toggle (English ↔ 繁體中文 — switches article display language
  + theme chip labels)
- Refresh button (forces a re-poll)

## Configuration

Edit `config.py`:

- `THEMES` — dict of `{ key: { label_en, label_zh, keywords_high, keywords_med } }`
- `RSS_SOURCES` — list of `{ name, url }` dicts

Defaults work out of the box. Tune for your watchlist.

## Notes

- SQLite means single-writer; APScheduler runs one job at a time, no issue.
- HTML cleaning strips tags and decodes entities so the summary field is
  plain text suitable for the card preview.
- Duplicate detection is by URL hash — same article from two feeds collapses
  to one row.
- The app is intentionally a single-file FastAPI for clarity. Production
  deployments are out of scope for this version.

## Algorithms

For the math behind the multi-label classifier, SimHash + MinHash/LSH
deduplication, and time-decay relevance ranking, see **[ALGORITHMS.md](./ALGORITHMS.md)**.

## License

Personal project, no license declared. Fork freely for personal use.
