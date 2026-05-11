"""
rate_limit.py — Per-IP fixed-window rate limiter backed by Upstash Redis.

Why Upstash:
  - Plain HTTP REST API (works inside Vercel serverless without socket pools)
  - Free tier 10K commands/day — far more than we'll burn even under abuse
  - Latency: ~5-15ms from US-East Vercel functions to US-East Upstash

Behavior on outage:
  - If Upstash env vars are missing OR Redis call throws → fail OPEN (allow).
    We're protecting against malicious abuse, not enforcing a paid quota.
    Failing closed would create a foot-gun: a flaky Redis would block all
    legit users.
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import HTTPException, Request

try:
    from upstash_redis import Redis  # type: ignore
    _redis: Optional[Redis] = None
    _url = os.environ.get("UPSTASH_REDIS_REST_URL", "")
    _token = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if _url and _token:
        _redis = Redis(url=_url, token=_token)
except Exception:
    _redis = None


def _client_ip(request: Request) -> str:
    """Extract real client IP, honoring Vercel's proxy headers."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    real = request.headers.get("x-real-ip", "")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


def _check(bucket: str, limit: int, window_s: int) -> bool:
    if _redis is None:
        return True
    try:
        count = _redis.incr(bucket)
        if count == 1:
            _redis.expire(bucket, window_s)
        return count <= limit
    except Exception as e:
        print(f"[rate_limit] Redis call failed: {e}", flush=True)
        return True


def rate_limit(prefix: str, limit: int, window_s: int):
    """FastAPI dependency factory."""
    def _dep(request: Request) -> None:
        ip = _client_ip(request)
        bucket = f"rl:{prefix}:{ip}"
        if not _check(bucket, limit, window_s):
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "limit": limit,
                    "window_seconds": window_s,
                },
                headers={"Retry-After": str(window_s)},
            )
    return _dep
