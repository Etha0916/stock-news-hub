"""
classify.py — Multi-label keyword classifier.

Score formula (per theme c):
    s_c(a) = 3.0 * (#high-weight matches) + 1.0 * (#med-weight matches)
Label:
    y_c(a) = 1   iff   s_c(a) >= THRESHOLD (default 1.5)

ASCII keywords use word-boundary matching; CJK keywords use plain substring.
"""
import re
import json
from typing import Dict, List, Tuple
from config import THEMES

W_HIGH = 3.0
W_MED = 1.0
THRESHOLD = 1.5


def _is_ascii(s: str) -> bool:
    return all(ord(c) < 128 for c in s)


def _compile(keywords: List[str]) -> List[Tuple[str, re.Pattern]]:
    out = []
    for kw in keywords:
        if _is_ascii(kw):
            pat = re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)
        else:
            pat = re.compile(re.escape(kw))
        out.append((kw, pat))
    return out


# Pre-compile once at import time
_COMPILED: Dict[str, Dict[str, List[Tuple[str, re.Pattern]]]] = {}
for theme, conf in THEMES.items():
    _COMPILED[theme] = {
        "high": _compile(conf["keywords_high"]),
        "med":  _compile(conf["keywords_med"]),
    }


def classify(text: str) -> Dict:
    """
    Returns:
        {
          "scores":  {theme: float},
          "labels":  [theme, ...],          # those that passed THRESHOLD
          "matches": {theme: [keyword,...]} # for debugging / explainability
        }
    """
    scores: Dict[str, float] = {}
    matches: Dict[str, List[str]] = {}
    for theme, patterns in _COMPILED.items():
        s = 0.0
        m: List[str] = []
        for kw, p in patterns["high"]:
            if p.search(text):
                s += W_HIGH
                m.append(kw)
        for kw, p in patterns["med"]:
            if p.search(text):
                s += W_MED
                m.append(kw)
        scores[theme] = s
        matches[theme] = m
    labels = [t for t, s in scores.items() if s >= THRESHOLD]
    return {"scores": scores, "labels": labels, "matches": matches}


def scores_to_json(scores: Dict[str, float]) -> str:
    return json.dumps(scores, ensure_ascii=False)


# ---------------------------------------------------------------------------
# CLI smoke test:  python classify.py "some headline text"
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    text = " ".join(sys.argv[1:]) or \
        "Nvidia and TSMC announce new AI chip; Fed signals possible rate cut."
    r = classify(text)
    print("Text:    ", text)
    print("Scores:  ", r["scores"])
    print("Labels:  ", r["labels"])
    print("Matches: ", r["matches"])
