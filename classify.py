"""
classify.py — Multi-label keyword classifier.

Score formula per theme c:
    s_c(a) =   3.0 * |high-keyword hits|        # strong positive
             + 1.0 * |med-keyword hits|         # weak positive
             - sum(w_n for n in negatives hit)  # veto / disambiguation
             + sum(w_C for C in co-occur sets   # contextual boost
                   if all members of C in a)
    s_c(a) := max(s_c(a), 0)                    # clamp at 0
    label  := s_c(a) >= THRESHOLD               # default 1.5

ASCII keywords use word-boundary matching (case-insensitive); CJK keywords
use plain substring matching.
"""
from __future__ import annotations

import re
import json
from typing import Dict, List, Tuple

from config import THEMES

W_HIGH = 3.0
W_MED = 1.0
THRESHOLD = 1.5


# ---------------------------------------------------------------------------
# Pattern compilation
# ---------------------------------------------------------------------------
def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _compile_one(kw: str) -> re.Pattern:
    if _is_ascii(kw):
        return re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
    return re.compile(re.escape(kw))


def _compile_list(keywords: List[str]) -> List[Tuple[str, re.Pattern]]:
    return [(kw, _compile_one(kw)) for kw in keywords]


def _compile_neg(items: List[Tuple[str, float]]) -> List[Tuple[str, re.Pattern, float]]:
    return [(kw, _compile_one(kw), w) for (kw, w) in items]


def _compile_co(items: List[Tuple[List[str], float]]) -> List[Tuple[List[Tuple[str, re.Pattern]], float]]:
    out = []
    for keys, weight in items:
        compiled_keys = [(k, _compile_one(k)) for k in keys]
        out.append((compiled_keys, weight))
    return out


_COMPILED: Dict[str, dict] = {}
for theme, conf in THEMES.items():
    _COMPILED[theme] = {
        "high": _compile_list(conf.get("keywords_high", [])),
        "med":  _compile_list(conf.get("keywords_med", [])),
        "neg":  _compile_neg(conf.get("keywords_neg", [])),
        "co":   _compile_co(conf.get("keywords_co", [])),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def classify(text: str) -> Dict:
    """
    Returns:
        {
          "scores":  {theme: float},
          "labels":  [theme, ...],          # those whose final score >= THRESHOLD
          "matches": {theme: [tagged tokens]} # for debugging / explainability
        }
    Match tags use sigils:
        +word  → positive hit
        -word  → negative (veto) hit
        &(a,b) → co-occurrence rule fired
    """
    scores: Dict[str, float] = {}
    matches: Dict[str, List[str]] = {}

    for theme, c in _COMPILED.items():
        s = 0.0
        m: List[str] = []

        # Positive evidence
        for kw, p in c["high"]:
            if p.search(text):
                s += W_HIGH
                m.append(f"+{kw}")
        for kw, p in c["med"]:
            if p.search(text):
                s += W_MED
                m.append(f"+{kw}")

        # Negative evidence (vetoes)
        for kw, p, w in c["neg"]:
            if p.search(text):
                s -= w
                m.append(f"-{kw}")

        # Co-occurrence boosts (all keys must match)
        for compiled_keys, w in c["co"]:
            if all(p.search(text) for _, p in compiled_keys):
                s += w
                m.append("&(" + ",".join(k for k, _ in compiled_keys) + ")")

        scores[theme] = max(s, 0.0)
        matches[theme] = m

    labels = [t for t, s in scores.items() if s >= THRESHOLD]
    return {"scores": scores, "labels": labels, "matches": matches}


def scores_to_json(scores: Dict[str, float]) -> str:
    return json.dumps(scores, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI smoke test:  python classify.py "some headline"
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or \
        "Nvidia and TSMC announce 2nm AI chip; Fed signals possible rate cut."
    r = classify(text)
    print("Text:    ", text)
    print("Labels:  ", r["labels"])
    print("Scores:  ", {k: round(v, 2) for k, v in r["scores"].items() if v > 0})
    print("Matches: ", {k: v for k, v in r["matches"].items() if v})
