"""
dedupe.py — SimHash-based near-duplicate detection.

Background — why SimHash:
    Reuters, Bloomberg and the Taiwanese wires (經濟日報、工商時報、鉅亨網)
    routinely reprint the same wire story. URL hash dedupe doesn't catch these
    because every outlet has a different URL. We need *near*-duplicate matching.

Algorithm (Charikar 2002):
    1. Extract features from text: tokenize into n-grams.
    2. Hash each feature to a 64-bit fingerprint h.
    3. Maintain a 64-element vector V of signed weights.
       For each feature, for each bit i in h:
         if bit i of h is 1: V[i] += weight
         else:               V[i] -= weight
    4. Collapse: SimHash(text) is the 64-bit value where bit i = (V[i] > 0).

Properties:
    - Two documents with overlapping vocabulary produce simhashes whose Hamming
      distance is small (the bit positions disagreeing correspond to features
      that *differ* between the two).
    - Near-dup threshold: Hamming distance ≤ 3 (out of 64) = strong candidate.
      This is the canonical threshold from Manku-Jain-Sarma 2007 "Detecting
      near-duplicates for web crawling."

Storage:
    SimHash is 64-bit unsigned; Postgres BIGINT is signed (max 2^63 - 1).
    We map the high bit by subtracting 2^64 when value >= 2^63, so the bit
    pattern survives roundtrip. Hamming distance is computed in Python after
    masking back to 64-bit unsigned.
"""
from __future__ import annotations

import re
import hashlib
from typing import Iterable, List


_BITS = 64
_MASK_64 = (1 << _BITS) - 1


# ---------------------------------------------------------------------------
# Tokenization for mixed CJK / English text
# ---------------------------------------------------------------------------
_EN_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RE = re.compile(r"[一-鿿]")


def _tokenize(text: str) -> List[str]:
    """
    Tokenize for SimHash. Mixed-language strategy:
      - English/digit unigrams (≥2 chars, lowercased)
      - English word bigrams: pairs of adjacent words. These capture phrasing
        uniqueness which is critical for short-text discrimination — without
        them, two headlines sharing 60% of words but different word order are
        indistinguishable to SimHash.
      - Chinese character 2-grams (overlapping)
    """
    text = text.lower()
    tokens: List[str] = []

    # English unigrams + bigrams
    en_words = _EN_RE.findall(text)
    tokens.extend(en_words)
    for i in range(len(en_words) - 1):
        tokens.append(en_words[i] + " " + en_words[i + 1])

    # CJK character 2-grams
    cjk = _CJK_RE.findall(text)
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])

    return tokens


def _feature_hash(token: str) -> int:
    """Stable 64-bit hash of a feature string (use SHA-1, take low 8 bytes)."""
    digest = hashlib.sha1(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


# ---------------------------------------------------------------------------
# Core SimHash
# ---------------------------------------------------------------------------
def simhash(text: str) -> int:
    """Compute 64-bit SimHash. Returns unsigned int in [0, 2^64)."""
    if not text:
        return 0
    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights = [0] * _BITS
    for tok in tokens:
        h = _feature_hash(tok)
        for i in range(_BITS):
            if (h >> i) & 1:
                weights[i] += 1
            else:
                weights[i] -= 1

    out = 0
    for i in range(_BITS):
        if weights[i] > 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    """Hamming distance between two simhashes (signed or unsigned)."""
    return bin((a & _MASK_64) ^ (b & _MASK_64)).count("1")


# ---------------------------------------------------------------------------
# Postgres BIGINT round-trip
# ---------------------------------------------------------------------------
def to_signed_bigint(v: int) -> int:
    """Map unsigned 64-bit simhash to signed BIGINT (-2^63..2^63-1)."""
    v &= _MASK_64
    if v >= (1 << 63):
        v -= (1 << 64)
    return v


def from_signed_bigint(v: int) -> int:
    """Recover unsigned 64-bit simhash from signed BIGINT read out of DB."""
    return v & _MASK_64


# ---------------------------------------------------------------------------
# Near-dup query
# ---------------------------------------------------------------------------
def find_near_duplicate(
    new_simhash: int,
    pool: Iterable[int],
    threshold: int = 3,
) -> int | None:
    """
    Linear scan: return the first pool simhash within `threshold` Hamming
    distance, else None. Pool size of a few thousand is fine; for >100k,
    upgrade to LSH banding.
    """
    new_unsigned = new_simhash & _MASK_64
    for existing in pool:
        if bin(new_unsigned ^ (existing & _MASK_64)).count("1") <= threshold:
            return existing
    return None


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pairs = [
        ("Nvidia reports record Q3 earnings on AI chip demand",
         "Nvidia posts record Q3 earnings driven by AI chip sales"),  # near dup
        ("TSMC Arizona fab progresses",
         "Apple unveils new iPhone 17 with on-device AI"),             # different
        ("聯準會宣布升息一碼",
         "FOMC raises rates by 25 basis points"),                      # different lang, same idea (probably won't dedup)
    ]
    for a, b in pairs:
        sa, sb = simhash(a), simhash(b)
        d = hamming(sa, sb)
        verdict = "DUP" if d <= 3 else "ok"
        print(f"[{d:2d}] {verdict}: {a[:60]!r} <> {b[:60]!r}")
