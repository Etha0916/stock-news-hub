# Fin-Tech News Hub

Personal financial news aggregator covering **Mag7**, **ELN underlyings**,
**Semiconductors**, **Taiwan Tech**, **AI**, and **Fed Rate** — bilingual UI
(Traditional Chinese / English).

Two deployment targets supported out of the box:

- **Vercel** (recommended) — true on-demand fetch, edge-cached for 5 min
- **GitHub Pages** — pre-baked static, refreshed every 5 min by Actions cron

## Architecture

### Vercel path (preferred)
```
Browser ─► /api/articles  ─►  Vercel function (Python)
                                 ├─ fetches all RSS in parallel
                                 ├─ classifies via classify.py
                                 └─ returns JSON
                                 (edge-cached 5 min)
```
Data is **at most cache-old** (300 s); first uncached visitor pays ~5 s, all
subsequent visitors served from edge in <50 ms. Stale-while-revalidate means
even cache-miss visitors get instant stale data while the worker fetches fresh.

### GitHub Pages path (fallback)
```
GitHub Actions cron (every 5 min)
  └─ runs build.py → writes docs/data/articles.json + themes.json
GitHub Pages serves docs/ via CDN; frontend reads ./data/*.json
```

## Files

| File | Role |
|---|---|
| `config.py` | Theme keywords, group structure, RSS source list |
| `classify.py` | Multi-label keyword classifier |
| `build.py` | Static-site builder (used by GitHub Actions + local dev) |
| `api/articles.py` | Vercel serverless function — on-demand RSS fetch |
| `api/themes.py` | Vercel serverless function — theme taxonomy |
| `docs/index.html` | Frontend (vanilla JS) — tries `/api/*` first, falls back to `./data/*.json` |
| `vercel.json` | Vercel routing + function config |
| `.github/workflows/build.yml` | GitHub Actions cron (only matters for GitHub Pages path) |
| `requirements.txt` | Python deps (just `feedparser`) |

## Deployment to Vercel

1. **Sign up:** <https://vercel.com/signup> — choose "Continue with GitHub"

2. **Import project:**
   - Dashboard → **Add New…** → **Project**
   - Find your repo (`stock-news-hub`) → **Import**
   - Vercel auto-detects the structure. Don't change anything; just press **Deploy**.

3. **Wait ~30 seconds** — Vercel builds and deploys.

4. **Get your URL.** It will look like:
   ```
   https://stock-news-hub.vercel.app
   ```
   Or if you set a custom subdomain, whatever you chose.

That's it. **Every `git push origin main` auto-deploys** within 30 s.

### Free tier limits (Vercel Hobby)

- 100 GB bandwidth / month — far more than this project will use
- 100 K function invocations / month — with 5-min edge cache, that's ~10 K real fetches max
- 10 s function execution per invocation (we hit ~5 s for all 30 RSS feeds in parallel)
- 12 invocations / minute — irrelevant given edge caching

If you want hard 24/7 reliability + multiple users, the Pro plan ($20/mo) lifts these. For personal use Hobby is fine.

## Deployment to GitHub Pages (alternative)

1. Repo → **Settings → Pages** → Source: **GitHub Actions**
2. Repo → **Settings → Actions → General** → Workflow permissions: **Read and write**
3. Repo → **Actions** tab → **Build & Deploy** → **Run workflow**
4. Site live at `https://YOUR_USERNAME.github.io/REPO_NAME/`

Note: this path uses `docs/data/*.json` baked at build time, refreshed by the
5-min cron. The frontend will automatically fall back to it if `/api/*` is
unavailable (which it always will be on GitHub Pages).

## Local development

```bash
pip install -r requirements.txt

# Generate static data
python build.py

# Serve frontend
python -m http.server -d docs 8000
# open http://localhost:8000
```

For local testing of the Vercel functions, install the Vercel CLI:

```bash
npm i -g vercel
vercel dev
```

## Customizing

- **Add a ticker / theme:** edit `THEMES` in `config.py`, push, done.
- **Tune classifier sensitivity:** edit `W_HIGH`, `W_MED`, `THRESHOLD` in `classify.py`.
- **Change cache duration:** edit `s-maxage=300` in `api/articles.py` to taste
  (lower = fresher but more function invocations; higher = staler but cheaper).
- **Add an RSS source:** append to `RSS_SOURCES` in `config.py`.

## Classifier in one line

```
score(article, theme) = 3·(strong-keyword hits) + 1·(soft-keyword hits)
label = (score ≥ 1.5) → multi-label across themes
```

So **one strong hit** (e.g. `TSMC`, `FOMC`) **or two soft hits** (e.g. `chip` + `foundry`) tags the article. Articles with no theme match are dropped.

## Pitfalls

- **Google News rate limits.** The function fetches 30+ feeds per cache-miss; Google can throttle if a single IP fires too many concurrent requests. The 5-min edge cache keeps us well under any limit.
- **Function cold start:** first request after idle adds ~1 s (Python function bootstrap). Edge cache hides this from most users.
- **`SNAP` ticker is deliberately excluded** as a bare keyword — too many false positives ("snap election", "snap decision"). Snap Inc. is matched via "Snap Inc" / "Snapchat" instead.
- **`Foundry` is a Palantir product** but also a semiconductor term. Excluded from PLTR's keywords to avoid bleed.
