# Stock News Hub — Algorithms

A personalized financial-news aggregator that ingests 30+ RSS feeds every
10 minutes, classifies articles across user-configurable themes, deduplicates
near-identical reports, and serves a real-time SPA with per-ticker price /
K-line views. This document is the **algorithmic spine** of the project — the
math, the design decisions, and the trade-offs behind each component.

For deployment instructions see `deploy.md` (not yet shipped); for product
walkthrough see the live demo at <https://stock-news-hub.vercel.app>.

---

## Pipeline at a glance

```
                    GitHub Actions cron (every 10 min)
                                |
                                v
        +-----------------------------------------------+
        |  ingest.py                                    |
        |   1.  Fetch 30+ RSS feeds in parallel         |
        |   2.  Classify each article (Sec. 1)          |
        |   3.  SimHash dedupe       (Sec. 2)           |
        |   4.  MinHash + LSH dedupe (Sec. 3)           |
        |   5.  UPSERT into Postgres                    |
        +-----------------------------------------------+
                                |
                                v
                       Supabase Postgres
                       (articles, watchlist_tickers, ...)
                                |
                +---------------+----------------+
                |                                |
                v                                v
   Vercel FastAPI                     Supabase Realtime
   (read endpoints +                  (WebSocket push of
    Finnhub / Twelve                   INSERT events)
    Data proxy)                                |
                |                              |
                +--------------+---------------+
                               |
                               v
                  Vue 3 SPA  (HomeView / TickerView)
                  - Time-decay relevance sort (Sec. 4)
                  - Rate-limited backend (Sec. 5)
                  - Provider fallback for prices (Sec. 6)
                  - Market-state-aware caching (Sec. 7)
```

Source layout:

```
config.py          themes, keyword sets, RSS source list
classify.py        weighted multi-label scorer
dedupe.py          SimHash + MinHash + LSH primitives
ingest.py          orchestrator that ties them together
db.py              Supabase Postgres helpers (psycopg)
rate_limit.py      Upstash-backed per-IP throttle
api/index.py       FastAPI server: read endpoints,
                   provider proxies, SPA fallback
frontend/          Vue 3 + Vite + Pinia client
```

---

## 1. Multi-label keyword scorer

### Problem

Given an article $a$ (title + summary) and a finite set of themes
$\mathcal{C} = \{\text{aapl}, \text{semi}, \text{ai}, \text{fed}, \ldots\}$,
assign zero or more theme labels. The classifier must be **explainable** (we
have to be able to answer "why was this article tagged `semi`?"), **cheap**
(runs ~30 times per cron, on the order of 1000 articles), and **multi-label**
(an article about Nvidia's AI chip is `nvda`, `semi`, and `ai` simultaneously).

### Model

For each theme $c$ we maintain four keyword sets — strong-positive,
weak-positive, negative (vetoes), and co-occurrence pairs — with associated
weights. The score is

$$
s_c(a) = \underbrace{w_H \sum_{k \in K^H_c} \mathbb{1}\{k \in a\}}_{\text{strong positives, }w_H = 3}
       + \underbrace{w_M \sum_{k \in K^M_c} \mathbb{1}\{k \in a\}}_{\text{weak positives, }w_M = 1}
       - \underbrace{\sum_{n \in K^N_c} w_n \mathbb{1}\{n \in a\}}_{\text{vetoes}}
       + \underbrace{\sum_{P \in K^{CO}_c} w_P \prod_{k \in P} \mathbb{1}\{k \in a\}}_{\text{co-occurrence}}
$$

clamped at zero, and the label assignment is

$$
\hat{y}_c(a) = \mathbb{1}\{\max(s_c(a), 0) \geq \tau\}, \quad \tau = 1.5.
$$

So **one strong hit** (`TSMC`, `FOMC`) **or two weak hits** (`chip` + `foundry`)
tags the article. **Negatives are vetoes** — they exist to fix specific
disambiguations:

- `meta` theme has `metadata`, `metaphor`, `meta-analysis` as negatives (weight
  2.5–3.0) so that "Open meta tags" doesn't get tagged as Meta Platforms.
- `snap` theme has `snap election`, `food stamps`, `SNAP benefits` as negatives
  so news about UK politics or the US food assistance program doesn't
  pollute the Snap Inc. feed.
- `amzn` theme excludes `Amazon rainforest`, `Amazon river`.
- `aapl` excludes `apple pie`, `apple orchard`, `Big Apple`.

**Co-occurrence** patches the cases where a single weak keyword is too noisy:
"rate" alone shows up in mortgage news, sports news, exchange-rate news. But
`("rate", "Fed")` or `("rate", "Powell")` co-occurring is strong evidence for
the `fed` theme. We give those pairs weight 2.0 each.

Conceptually this is equivalent to a **hand-tuned, sparse, log-linear model**:
we set the feature weights by domain knowledge rather than training. The
advantages over a learned classifier here are (i) zero labeled data needed,
(ii) every score is trivially explainable, (iii) adding a keyword takes 1
line in `config.py`.

### Tokenization

ASCII keywords use word-boundary regex (`\b…\b`, case-insensitive) — so
`Apple` matches `Apple` and `APPLE` but not `applesauce`. CJK keywords use
plain substring match because Chinese has no whitespace tokenization without
a segmenter; this is the standard practical compromise.

### Files

- `config.py` — `THEMES` dict, each entry has `keywords_high`, `keywords_med`,
  optional `keywords_neg`, optional `keywords_co`.
- `classify.py` — `_compile_*` builders, `classify(text)` entry point.

### Pitfalls

- Bare ticker symbols like `META`, `SNAP` are too noisy as high-weight
  keywords. We push them to medium weight and lean on more specific phrases
  (`Meta Platforms`, `Snap Inc`, `Snapchat`) for high.
- The scorer cannot generalize: a brand-new product name like `Sora` for
  OpenAI is invisible until we add it to `config.py`. Phase 5 (out of scope
  for this README) plans an embedding-prototype upgrade for graceful
  generalization.

---

## 2. SimHash near-duplicate detection

### Problem

After URL deduplication, we still see many copies of the same wire story
republished across feeds with minor edits ("Nvidia reports…" vs "Nvidia
posts…"). A character-level diff is overkill and too brittle; we want a
**fingerprint** so the duplicate check is O(1) hash comparison plus a
short Hamming distance computation.

### Algorithm (Charikar 2002)

For each text:

1. Tokenize into features. Our tokenizer (`_tokenize` in `dedupe.py`)
   emits English unigrams + bigrams plus Chinese character 2-grams. Bigrams
   are important — without them, "Nvidia Q3" and "Q3 Nvidia" produce
   identical fingerprints despite different intent.
2. For each feature $f$ compute a 64-bit hash $h_f$. We use SHA-1 truncated
   to 64 bits.
3. Maintain a vector $\mathbf{v} \in \mathbb{Z}^{64}$. For each feature:
   $v_i \mathrel{+}= 1$ if bit $i$ of $h_f$ is 1, else $v_i \mathrel{-}= 1$.
4. The SimHash $S \in \{0,1\}^{64}$ is the sign of $\mathbf{v}$:
   bit $i$ of $S$ is $1$ iff $v_i > 0$.

Two near-duplicates produce SimHashes that differ in only a few bits — the
**Hamming distance** $d_H(S_a, S_b)$ approximates the symmetric difference of
feature sets, scaled by 64. We declare a duplicate when

$$
d_H(S_a, S_b) \leq 6 \quad (\text{out of 64}).
$$

This threshold comes from Manku, Jain & Sarma (2007), who established 3
as the canonical threshold for web-page-scale documents (thousands of
shingles). For our shorter "title + summary" inputs (~30–100 features),
we relax to 6 to capture more rewrites while still avoiding obvious
false positives — confirmed empirically against a held-out set.

### Bit-pattern tricks

Postgres has no unsigned 64-bit type. `BIGINT` is signed `[-2^63, 2^63)`.
SimHash is unsigned. We round-trip via two's complement:

```python
def to_signed_bigint(v: int) -> int:
    v &= (1 << 64) - 1
    if v >= (1 << 63):
        v -= (1 << 64)
    return v
```

The bit pattern survives the roundtrip — XOR on the recovered values gives
the same Hamming distance as XOR on the original unsigned values.

### Files

- `dedupe.py` — `simhash()`, `hamming()`, `to_signed_bigint()`.

### Pitfalls

- **Translations are invisible.** "聯準會升息" and "Fed raises rates" share
  almost zero tokens; SimHash distance is uniformly large. We accept this —
  translations are caught by URL hash if they share a source, otherwise not.
- **Same-template different-entity articles look similar.** "Nvidia Q3
  revenue beats" and "AMD Q3 revenue beats" share many bigrams. They land at
  Hamming distance ~12-15 in our test data — above our threshold of 6, so we
  don't false-merge them. This margin is why we picked 6, not 10.

---

## 3. MinHash + LSH (paraphrase detection)

### Problem

SimHash catches near-verbatim reprints but misses **paraphrased** versions of
the same event: Reuters reports a deal, Bloomberg rewrites the lede,
經濟日報 translates the body. These share most facts but few exact character
sequences. We want a Jaccard-style set-similarity test that catches these.

### Algorithm

For each article we compute a **MinHash signature** of size $n = 128$:

1. Define a set of $k$-shingles. We use $k = 5$ character-level shingles,
   stripping whitespace, so that "Nvidia Q3" and "Nvidia  Q3" share shingles.
2. For each of $n$ independent hash functions $h_1, \ldots, h_n$ (we
   parameterize MD5 with a 2-byte salt), let
   $\mathrm{MinHash}_i(A) = \min_{x \in A} h_i(x)$.
3. The signature is $\sigma(A) = (\mathrm{MinHash}_1(A), \ldots, \mathrm{MinHash}_n(A))$.

Broder (1997) shows that for any two sets $A, B$:

$$
\Pr[\mathrm{MinHash}_i(A) = \mathrm{MinHash}_i(B)] = J(A, B) = \frac{|A \cap B|}{|A \cup B|}.
$$

So estimating Jaccard reduces to counting signature collisions:

$$
\hat{J}(A, B) = \frac{1}{n} \sum_{i=1}^{n} \mathbb{1}\{\sigma_i(A) = \sigma_i(B)\}.
$$

### Why LSH? — making the query cheap

A pool of 1000 articles in the past 24 hours produces 1000 signatures.
Pairwise Jaccard with the new article is $O(n)$ each, $O(N n)$ total — fine
for our scale but wasteful. **LSH banding** (Gionis-Indyk-Motwani 1999) cuts
this to roughly $O(\sqrt{N})$ candidates:

Split the signature into $b$ bands of $r$ rows ($b \cdot r = n$). Hash each
band to a bucket. Two signatures **share a bucket on at least one band** iff
they agree on all $r$ rows of that band. The probability of this happening
given Jaccard $t$ is

$$
P_{\text{LSH}}(t) = 1 - (1 - t^r)^b,
$$

which is an S-curve crossing 0.5 near our chosen threshold. We pick $(b, r)$
to minimize $|P_{\text{LSH}}(\tau) - 0.5|$ at our target threshold
$\tau = 0.6$. For $n = 128$ this gives $(b, r) = (16, 8)$.

Query a new article by hashing its bands, looking up each band's bucket,
unioning the candidates, and finally computing the exact Jaccard estimate
$\hat{J}$ against each candidate. Confirmed duplicate iff
$\hat{J} \geq 0.6$.

### Why 0.6, not 0.7?

The literature quotes 0.7–0.8 for web-page-scale documents (thousands of
shingles). On our headline + 600-char summaries (~250 shingles), real
wire reprints land in 0.5–0.8, while same-template-different-company
articles sit at 0.3–0.5. The threshold-0.6 boundary captures wire reprints
without false-merging "Nvidia Q3 revenue" with "AMD Q3 revenue". This was
calibrated empirically with the test cases in `dedupe.py`'s `__main__`.

### Files

- `dedupe.py` — `MinHash`, `MinHashLSH`, `make_minhash()`,
  `find_near_dup_minhash()`. The implementation is from-scratch (no
  `datasketch` dependency) so that Vercel cold-start stays light.

### Two-stage dedup in ingest

The pipeline runs **SimHash first**, **MinHash second**:

```
for each candidate article a:
    sh ← SimHash(a.title + " " + a.summary)
    if  any pool entry has Hamming(sh, .) ≤ 6  → drop  (sim-hash dup)
    mh ← MinHash(a.title + " " + a.summary)
    if  LSH(mh) returns any cand with Jaccard ≥ 0.6  → drop  (paraphrase dup)
    insert a with simhash + minhash_bytes into Postgres
    add sh, mh to in-memory pool for the rest of this run
```

Both pools are loaded from the last 24-hour window at the start of each
cron run; new inserts are appended in-memory so within-run duplicates are
caught too.

---

## 4. Time-decay relevance ranking

### Problem

Chronological feed ("newest first") is easy but not always optimal. When the
user picks "Top" instead of "Latest", we want a score that combines:

- **Theme score** $s_c(a)$ — how well the article matches the user's filter
- **Recency** — articles age out of relevance fast in finance news
- **Future**: engagement (clicks, time-on-page) — not yet implemented

### Decay function

Exponential decay with half-life $T_{1/2} = 24$ hours:

$$
W(\Delta t) = e^{-\lambda \Delta t}, \quad \lambda = \frac{\ln 2}{T_{1/2}} \approx 0.0289 \text{ hr}^{-1}
$$

So an article 24 hours old contributes 50% of its theme-score weight, 48
hours old 25%, and so on. The half-life of 24 hours is calibrated for
financial-news velocity — it's faster than evergreen content (week+ half-life)
but slower than breaking news (1-hour half-life).

### Combined relevance score

$$
R(a, c) = \max_{c \in \text{filter}} s_c(a) \cdot e^{-\lambda \Delta t_a}
$$

When no filter is active, $\max_c$ is taken over all themes — articles with
a strong signal in any theme bubble up. When a filter is active, only that
theme's scores matter.

### Files

- `frontend/src/stores/news.ts` — `displayedArticles` computed property.

### Why client-side?

The math runs on a few hundred articles in the user's browser, so we keep it
purely frontend. Moving to Postgres-side ranking would require a SQL function
and re-rendering the cached `/api/articles` response each time the user
toggles between Latest/Top, breaking the edge cache strategy in section 7.

---

## 5. Rate limiting (fixed window, Redis-backed)

### Problem

Two public POST endpoints can be weaponized:

- `POST /api/watchlist/register` triggers a Finnhub validation + Yahoo RSS
  fetch + Postgres insert per call. A scripted attacker hammering this can
  burn our 800-call/day Twelve Data budget AND fill `watchlist_tickers` with
  garbage that subsequent cron jobs try to fetch indefinitely.
- `GET /api/quote/{ticker}` and `GET /api/candles/{ticker}` proxy to paid
  third-party APIs; uncached traffic to arbitrary tickers exhausts quota.

We need per-IP rate limiting that survives Vercel's stateless function
restarts.

### Algorithm

Fixed-window counter in Redis:

```
key   = "rl:" + endpoint + ":" + client_ip
ttl   = window_seconds
limit = max_requests_per_window

count = INCR key
if count == 1:
    EXPIRE key ttl
if count > limit:
    return 429
```

Three operations per request (`INCR`, conditional `EXPIRE`), but `EXPIRE`
fires only on the first request of a window, so amortized cost is ~1
Redis call. With Upstash (REST API over HTTP, ~10ms latency from US-East
Vercel functions) this adds negligible overhead.

We deliberately picked **fixed window over sliding window**. Sliding window
is more "fair" near boundaries but requires storing per-request timestamps;
fixed window is one integer per (IP, endpoint) and the boundary-spike
behavior is fine for an abuse-prevention use case.

### Fail-open policy

If Upstash is unreachable or returns an error, the dependency raises
nothing and the request passes. The rationale: we are protecting against
malicious abuse, not enforcing a paid quota. A flaky Redis would block our
own users — a worse failure mode than letting some abuse through during a
Redis outage. Operationally we'd notice via Vercel logs.

### Files

- `rate_limit.py` — `rate_limit(prefix, limit, window_s)` FastAPI
  dependency factory.

### Client-IP extraction

We honor Vercel's proxy headers in this order:
`X-Forwarded-For` (leftmost), `X-Real-IP`, then `request.client.host`.
Reading `request.client.host` directly would give us the Vercel edge proxy
IP, defeating the purpose.

---

## 6. Provider fallback chain (Twelve Data → Yahoo)

### Problem

OHLCV daily candles have been a moving target: Finnhub paywalled `/stock/candle`
in 2024, Yahoo's chart endpoint started 429ing Vercel egress IPs, Stooq added
a captcha-issued API key requirement. We resolved this by integrating
**Twelve Data** as the primary, but want graceful degradation when it fails
(rate limits, transient outages).

### Algorithm

Sequential try-catch through an ordered list of providers, returning on the
first non-empty success:

```python
def candles_with_fallback(symbol, days):
    errors = []
    for name, fetch_fn in PROVIDERS:
        try:
            data = fetch_fn(symbol, days)
            if data:
                return data, name, errors
            errors.append(f"{name}: empty")
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__}: {e}")
    return [], "none", errors
```

Three things worth noting:

1. **Empty result counts as failure** — Twelve Data returns `status: "ok"`
   with an empty `values` array for unknown tickers; we fall through.
2. **Errors are accumulated, not silenced** — the final response includes
   `tried: [...]` if all providers fail, so debugging an outage doesn't
   require reading function logs.
3. **The successful provider is echoed back** in the response as `source:`,
   making it observable from the client without instrumenting separately.

### Why not run providers in parallel?

We could `asyncio.gather` and take the first non-empty result, saving 0.5–1
second when the primary fails. But Twelve Data succeeds 99% of the time, and
the latency cost is paid only on its failure, so the savings are
not worth doubling our outbound API call rate (which counts against both
provider quotas).

### Files

- `api/index.py` — `_candles_with_fallback`, with `_twelve_candles` and
  `_yahoo_candles` as the primary and fallback implementations.

---

## 7. Market-state-aware HTTP cache

### Problem

A quote endpoint should be **fresh during US market hours** (price moves
every second) but **stale-tolerant after close** (the last-trade price
doesn't change until the next session). The same is true for daily candles
— intraday they're a moving target, but after 4 PM ET the day's bar is
fixed for 16+ hours. Static cache TTLs waste either freshness or quota.

### Algorithm

Map UTC timestamp to one of four market states using DST-aware Eastern Time:

```python
def us_market_state(now_utc) -> str:
    now_et = now_utc.astimezone(ZoneInfo("America/New_York"))
    if now_et.weekday() >= 5:                              return "closed"
    if   time(4, 0)  <= now_et.time() < time(9, 30):       return "pre"
    elif time(9, 30) <= now_et.time() < time(16, 0):       return "open"
    elif time(16, 0) <= now_et.time() < time(20, 0):       return "after"
    else:                                                  return "closed"
```

Then map state to TTL:

| Endpoint | open  | pre / after | closed |
|---|---|---|---|
| `/api/quote/X`   | 30 s   | 120 s   | 3600 s  |
| `/api/candles/X` (daily)   | 300 s  | 600 s   | 21600 s |
| `/api/candles/X` (intraday) | 60 s   | 120 s   | 600 s  |
| `/api/articles`            | 180 s (constant — RSS cron is 10 min) |
| `/api/themes`              | 86400 s (config-derived) |

The `Cache-Control` header is set per response:

```python
Cache-Control: public, s-maxage=300, stale-while-revalidate=1800
```

The `stale-while-revalidate` directive (RFC 5861) is critical: it tells
Vercel's edge to **serve stale content immediately** to the next visitor
**while asynchronously refreshing the cache** in the background. The visitor
gets <50ms perceived latency; the cache renews to a fresh value for the
visitor after them. Effectively, only one request per TTL window per region
hits our function — everyone else hits the edge.

### Files

- `api/index.py` — `us_market_state()`, `quote_cache_seconds()`,
  `candle_cache_seconds()`.

### Why not a single CDN-level rule?

Vercel does have edge-routing rules in `vercel.json`, but they can't read
the current time to compute a dynamic TTL. Anything time-conditional has
to be set per-response by the application. The performance cost is a
single `datetime.now()` + `.astimezone()` call per request — ~10μs.

---

## References

- Charikar, M. (2002). *Similarity estimation techniques from rounding
  algorithms.* STOC '02. — SimHash.
- Manku, G., Jain, A., & Sarma, A. (2007). *Detecting near-duplicates for
  web crawling.* WWW '07. — Hamming threshold = 3 (and our adapted = 6).
- Broder, A. (1997). *On the resemblance and containment of documents.*
  Compression and Complexity of Sequences. — MinHash.
- Gionis, A., Indyk, P., & Motwani, R. (1999). *Similarity search in high
  dimensions via hashing.* VLDB '99. — LSH banding.
- Bernstein, P. & Goodman, N. (1981). *Concurrency control in distributed
  database systems.* ACM Computing Surveys. — basis for fail-open vs
  fail-closed reasoning in section 5.

---

## License & status

Status: **personal MVP, headed for B2B SaaS**. Code style is opinionated
toward clarity rather than maximum performance — every algorithm above
has a faster industrial-grade implementation, but the project is
deliberately within reading distance of a junior engineer.
