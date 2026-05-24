"""
sentiment.py — Per-article sentiment scoring via Claude Haiku 4.5.

Sits next to classify.py / dedupe.py in the root namespace. Designed to be
called from ingest.py after classification + dedupe, so we only pay the LLM
cost for articles that pass theme filtering and aren't duplicates.

Score semantics
---------------
    score  ∈ [-1.0, +1.0]
        −1.0  strongly bearish (immediate negative price impact expected)
         0.0  neutral / no actionable signal
        +1.0  strongly bullish (immediate positive price impact expected)
    confidence ∈ [0.0, 1.0]
        how sure the model is — low confidence = ambiguous news, treat as 0

Bilingual: the same prompt handles both English and Traditional Chinese
news headlines, so we don't need to detect language upstream.

Cost: ~$0.00015 per article (input ~50 tok @ $1/MTok, output ~30 tok @ $5/MTok).
At 500 articles/day → ~$2.25/month.

Failure mode: if the model output is unparseable, we return None instead
of raising — sentiment is enrichment, not a hard requirement.
"""
from __future__ import annotations

import os
import json
import re
import time
import threading
from typing import Optional, TypedDict
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 200
TIMEOUT_S = 15.0
PROMPT_VERSION = "v1"

# Anthropic Tier 1 rate limit for Haiku is 50 RPM. We cap at 45 RPM for a
# safety margin so concurrent workers never trigger 429 errors.
# Upgrading to Tier 2 ($40 total credit purchases) raises this to 1,000 RPM
# and makes this throttle effectively a no-op.
_RATE_LIMIT_RPM = 45
_MIN_CALL_INTERVAL_S = 60.0 / _RATE_LIMIT_RPM  # ~1.33 seconds

# Shared throttle state across threads. The lock is held very briefly (just
# to read/update _last_api_call_at), so contention is negligible even with
# many workers.
_rate_limit_lock = threading.Lock()
_last_api_call_at: float = 0.0


def _wait_for_rate_limit() -> None:
    """Block (sleep) until safe to send the next API request.

    Thread-safe: enforces a global lower bound on inter-call interval no
    matter how many workers are calling score_article() concurrently. With
    4 workers and ~1.5s API latency, this pipelines at the rate-limit
    ceiling without ever exceeding it.
    """
    global _last_api_call_at
    with _rate_limit_lock:
        now = time.monotonic()
        elapsed = now - _last_api_call_at
        if elapsed < _MIN_CALL_INTERVAL_S:
            time.sleep(_MIN_CALL_INTERVAL_S - elapsed)
        _last_api_call_at = time.monotonic()


class SentimentResult(TypedDict):
    """Returned by score_article. All fields populated on success."""
    score: float                # -1.0 .. +1.0
    confidence: float           # 0.0 .. 1.0
    rationale: str              # one-sentence reason
    model: str                  # which model produced it
    scored_at: str              # ISO 8601 timestamp


# ---------------------------------------------------------------------------
# Lazy client — avoids importing anthropic at module load (Vercel cold-start
# matters), and gives a clear error if the env var is missing.
# ---------------------------------------------------------------------------
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY env var not set. "
            "Set it in Vercel (Settings → Environment Variables) and locally "
            "(.env or shell). Sentiment scoring is skipped until configured."
        )
    # Import inside the function so the rest of the app can be imported
    # even if anthropic isn't installed (it's only needed at scoring time).
    from anthropic import Anthropic  # noqa: PLC0415
    # max_retries=1: with our own _wait_for_rate_limit() pacing, the SDK
    # shouldn't see 429s in steady state. Cap retries so transient network
    # blips get one chance but we don't amplify rate-limit hits.
    _client = Anthropic(api_key=api_key, timeout=TIMEOUT_S, max_retries=1)
    return _client


# ---------------------------------------------------------------------------
# Prompt — kept short to minimize cost, but JSON-strict so parsing is robust.
# ---------------------------------------------------------------------------
_PROMPT_TEMPLATE = """You are a financial sentiment analyst. Score the immediate \
market impact of this news on a scale from -1.0 (strongly bearish) to +1.0 \
(strongly bullish), where 0 means neutral or no actionable signal.

Consider: earnings surprises, guidance changes, regulatory actions, \
macro shifts, and how the market typically reacts. Be calibrated: most \
news should score between -0.5 and +0.5; extreme scores (|score| > 0.7) \
should be rare and reserved for clearly significant events.

Output strictly valid JSON, no markdown fences, no explanation outside the JSON:
{{
  "score": <float in [-1.0, 1.0]>,
  "confidence": <float in [0.0, 1.0]>,
  "rationale": "<one short sentence, max 120 chars, language matching the input>"
}}

Title: {title}
Summary: {summary}"""


def _build_prompt(title: str, summary: str) -> str:
    # Truncate to keep input token count predictable / cheap.
    title = (title or "").strip()[:300]
    summary = (summary or "").strip()[:600]
    return _PROMPT_TEMPLATE.format(title=title, summary=summary)


# ---------------------------------------------------------------------------
# Robust JSON extraction — model usually outputs clean JSON, but we handle
# the case where it wraps in ```json ... ``` or adds trailing prose.
# ---------------------------------------------------------------------------
_JSON_BLOCK_RE = re.compile(r"\{[^{}]*\"score\"[^{}]*\}", re.DOTALL)


def _parse_response(text: str) -> Optional[dict]:
    text = text.strip()
    # Strip markdown fence if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: extract first JSON-looking object
    m = _JSON_BLOCK_RE.search(text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def score_article(
    title: str,
    summary: str = "",
) -> Optional[SentimentResult]:
    """
    Score a single article. Returns None on any failure (parse, API, timeout).
    Callers should treat None as "no sentiment available, leave column NULL".
    """
    if not title or not title.strip():
        return None

    try:
        client = _get_client()
        prompt = _build_prompt(title, summary)
        # Wait if needed to stay under the global RPM ceiling. Cheap when
        # workers aren't saturated; blocks briefly when they are.
        _wait_for_rate_limit()
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
        parsed = _parse_response(raw)
        if parsed is None:
            return None
        score = _clamp(parsed.get("score", 0.0), -1.0, 1.0)
        confidence = _clamp(parsed.get("confidence", 0.0), 0.0, 1.0)
        rationale = str(parsed.get("rationale", ""))[:200]
        return SentimentResult(
            score=score,
            confidence=confidence,
            rationale=rationale,
            model=MODEL,
            scored_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        # Never let sentiment failure block ingest pipeline.
        print(f"[sentiment] score failed for title={title[:60]!r}: {e}", flush=True)
        return None


def is_enabled() -> bool:
    """Cheap check used by ingest.py to skip the LLM call entirely when
    ANTHROPIC_API_KEY isn't set (e.g. local dev without an API key)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
