"""
dedupe.py — Two-layer near-duplicate detection.

Layer 1: SimHash + Hamming distance
    Cheap (single 64-bit fingerprint, single XOR popcount). Catches near-
    identical reprints — same article with verb swaps or punctuation drift.
    Threshold: Hamming ≤ 6.

Layer 2: MinHash + LSH + Jaccard
    Pricier (128 hashes per article + LSH band lookup). Catches paraphrased
    reprints — same event covered by different outlets in different words
    (Reuters wire → Bloomberg rewrite → 經濟日報 translation).
    Threshold: Jaccard ≥ 0.7.

Both run independently; either match → drop the new article.

This module deliberately uses zero external deps (no numpy, no datasketch)
to keep Vercel cold-start light. Algorithms are textbook implementations:
  - SimHash:   Charikar 2002, Manku-Jain-Sarma 2007
  - MinHash:   Broder 1997
  - LSH bands: Gionis-Indyk-Motwani 1999
"""
from __future__ import annotations

import re
import struct
import hashlib
from typing import Iterable, List


_BITS = 64
_MASK_64 = (1 << _BITS) - 1


# ===========================================================================
# Tokenization (shared by SimHash + MinHash)
# ===========================================================================
_EN_RE = re.compile(r"[a-z0-9]{2,}")
_CJK_RE = re.compile(r"[一-鿿]")
_WS_RE = re.compile(r"\s+")


def _tokenize(text: str) -> List[str]:
    """Tokens for SimHash: English unigrams + bigrams, CJK 2-grams."""
    text = text.lower()
    tokens: List[str] = []
    en = _EN_RE.findall(text)
    tokens.extend(en)
    for i in range(len(en) - 1):
        tokens.append(en[i] + " " + en[i + 1])
    cjk = _CJK_RE.findall(text)
    for i in range(len(cjk) - 1):
        tokens.append(cjk[i] + cjk[i + 1])
    return tokens


def _shingles(text: str, k: int = 5) -> set:
    """Character k-shingles for MinHash, with whitespace removed so formatting
    doesn't change the shingle set."""
    s = _WS_RE.sub("", text.lower())
    if len(s) < k:
        return {s} if s else set()
    return {s[i : i + k] for i in range(len(s) - k + 1)}


# ===========================================================================
# SimHash (existing)
# ===========================================================================
def _feature_hash(token: str) -> int:
    digest = hashlib.sha1(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def simhash(text: str) -> int:
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
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin((a & _MASK_64) ^ (b & _MASK_64)).count("1")


def to_signed_bigint(v: int) -> int:
    v &= _MASK_64
    if v >= (1 << 63):
        v -= 1 << 64
    return v


def from_signed_bigint(v: int) -> int:
    return v & _MASK_64


def find_near_duplicate(
    new_simhash: int,
    pool: Iterable[int],
    threshold: int = 6,
) -> int | None:
    new_unsigned = new_simhash & _MASK_64
    for existing in pool:
        if bin(new_unsigned ^ (existing & _MASK_64)).count("1") <= threshold:
            return existing
    return None


# ===========================================================================
# MinHash
# ===========================================================================
NUM_PERM = 128
# Empirical: 0.7 is web-page-scale (thousands of shingles); for headlines+summary
# of ~250 shingles, real wire reprints land in 0.5-0.8 range while
# template-similar-different-company stories sit at 0.3-0.5. We pick 0.6 as the
# "wire reprint" threshold — catches most verbatim republications without
# false-merging Nvidia-Q3 with AMD-Q3.
JACCARD_THRESHOLD = 0.6
_HASH_MOD = (1 << 32) - 1   # 32-bit hash space; max value is sentinel "infinity"


class MinHash:
    """Minimal MinHash. Stores num_perm 32-bit hash values."""

    __slots__ = ("num_perm", "hashvalues")

    def __init__(self, num_perm: int = NUM_PERM):
        self.num_perm = num_perm
        self.hashvalues: list[int] = [_HASH_MOD] * num_perm

    def update(self, token: bytes) -> None:
        # Generate num_perm independent hashes by varying the salt
        for i in range(self.num_perm):
            h = hashlib.md5(i.to_bytes(2, "big") + token).digest()
            v = int.from_bytes(h[:4], "big")
            if v < self.hashvalues[i]:
                self.hashvalues[i] = v

    def jaccard(self, other: "MinHash") -> float:
        if self.num_perm != other.num_perm:
            raise ValueError("num_perm mismatch")
        same = sum(
            1 for a, b in zip(self.hashvalues, other.hashvalues) if a == b
        )
        return same / self.num_perm


def make_minhash(text: str, num_perm: int = NUM_PERM) -> MinHash:
    mh = MinHash(num_perm)
    for sh in _shingles(text):
        mh.update(sh.encode("utf-8"))
    return mh


def serialize_minhash(mh: MinHash) -> bytes:
    """Pack as `num_perm` × uint32 — fixed 512 bytes for default 128 perm."""
    return struct.pack(f"{mh.num_perm}I", *mh.hashvalues)


def deserialize_minhash(blob: bytes, num_perm: int = NUM_PERM) -> MinHash:
    mh = MinHash(num_perm)
    mh.hashvalues = list(struct.unpack(f"{num_perm}I", blob))
    return mh


# ===========================================================================
# LSH banding — locality-sensitive hashing for fast near-duplicate query
# ===========================================================================
def _optimal_bands(threshold: float, num_perm: int) -> tuple[int, int]:
    """Pick b (bands) and r (rows/band) such that b*r = num_perm and the LSH
    S-curve P(match|J=t) = 1 - (1 - t^r)^b crosses 0.5 near `threshold`.
    Standard heuristic — choose params minimizing |P(threshold) - 0.5|."""
    best = (num_perm, 1)
    min_err = float("inf")
    for b in range(1, num_perm + 1):
        if num_perm % b != 0:
            continue
        r = num_perm // b
        prob = 1 - (1 - threshold ** r) ** b
        err = abs(prob - 0.5)
        if err < min_err:
            min_err = err
            best = (b, r)
    return best


class MinHashLSH:
    """Banded LSH index over MinHash signatures."""

    def __init__(self, threshold: float = JACCARD_THRESHOLD, num_perm: int = NUM_PERM):
        self.num_perm = num_perm
        self.threshold = threshold
        self.b, self.r = _optimal_bands(threshold, num_perm)
        # b independent hash tables: band_hash → set of keys
        self.tables: list[dict] = [dict() for _ in range(self.b)]

    def _band_hashes(self, mh: MinHash) -> list[int]:
        return [
            hash(tuple(mh.hashvalues[band * self.r : (band + 1) * self.r]))
            for band in range(self.b)
        ]

    def insert(self, key: str, mh: MinHash) -> None:
        for band, bh in enumerate(self._band_hashes(mh)):
            self.tables[band].setdefault(bh, set()).add(key)

    def query(self, mh: MinHash) -> set:
        """Return candidate keys whose signature shares ≥1 band hash."""
        out: set = set()
        for band, bh in enumerate(self._band_hashes(mh)):
            out.update(self.tables[band].get(bh, ()))
        return out


def find_near_dup_minhash(
    new_mh: MinHash,
    lsh: MinHashLSH,
    mh_pool: dict,
    threshold: float = JACCARD_THRESHOLD,
) -> str | None:
    """Two-stage check: LSH gives candidates, exact Jaccard confirms."""
    for cand_id in lsh.query(new_mh):
        cand = mh_pool.get(cand_id)
        if cand is not None and new_mh.jaccard(cand) >= threshold:
            return cand_id
    return None


# ===========================================================================
# Smoke test
# ===========================================================================
if __name__ == "__main__":
    pairs = [
        # Near-dup expected
        (
            "Nvidia Q3 earnings beat estimates on AI chip demand. Revenue $35.1B up 94%.",
            "Nvidia posts Q3 earnings beat on AI chip demand. The company's revenue hit $35.1 billion.",
        ),
        # Different
        (
            "Nvidia Q3 earnings beat estimates",
            "Apple unveils new iPhone with on-device generative AI",
        ),
        # Same template, different ticker — should NOT dedup
        (
            "Nvidia Q3 revenue $35B beats estimates",
            "AMD Q3 revenue $7B beats estimates",
        ),
    ]
    for a, b in pairs:
        sh_a, sh_b = simhash(a), simhash(b)
        sh_d = hamming(sh_a, sh_b)
        mh_a, mh_b = make_minhash(a), make_minhash(b)
        j = mh_a.jaccard(mh_b)
        verdict_sh = "DUP" if sh_d <= 6 else "ok"
        verdict_mh = "DUP" if j >= 0.7 else "ok"
        print(f"SH={sh_d:3d} ({verdict_sh})  J={j:.2f} ({verdict_mh})  "
              f"{a[:50]!r} <> {b[:50]!r}")
