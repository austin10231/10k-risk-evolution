"""Text canonicalisation + lexical similarity primitives for Compare.

Design notes:
- Pure stdlib; no nltk/scikit. Calling cost matters because we score
  every pair in a (small) bucket.
- The pipeline is deterministic and idempotent so we can also pre-cache
  canonical forms next to embeddings if we want to later.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import Iterable, List, Sequence

from core.compare_synonyms import (
    BOILERPLATE_PREFIXES,
    STOP_WORDS,
    SYNONYM_GROUPS,
    synonym_lookup,
)


_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_MONEY_RE = re.compile(
    r"\$\s?\d[\d,]*(?:\.\d+)?\s?(?:billion|million|thousand|bn|mm|k)?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\b\d+(?:\.\d+)?\s?%")
_NUMERIC_RE = re.compile(r"\b\d[\d,]*(?:\.\d+)?\b")

# Lazily built; cheap but called per title.
_SYNONYM_MAP = synonym_lookup()
_SYNONYM_MULTI = sorted(
    (k for k in _SYNONYM_MAP if " " in k),
    key=lambda s: (-len(s), s),
)
_SYNONYM_SINGLE = sorted(
    (k for k in _SYNONYM_MAP if " " not in k),
    key=lambda s: (-len(s), s),
)
_BOILERPLATE = sorted(BOILERPLATE_PREFIXES, key=lambda s: (-len(s), s))


def _strip_boilerplate(text: str) -> str:
    """Drop the longest boilerplate preamble that the title starts with."""
    for p in _BOILERPLATE:
        if text.startswith(p + " ") or text == p:
            return text[len(p):].lstrip()
    return text


def _replace_synonyms(text: str) -> str:
    """Two-pass replacement: multi-word phrases first (so 'cyber attack'
    becomes 'infosec' before the single-word 'cyber' rule could fire),
    then single-word forms."""
    out = text
    for surface in _SYNONYM_MULTI:
        if surface in out:
            out = out.replace(surface, _SYNONYM_MAP[surface])
    if not out:
        return out
    # Single-word: rebuild by token to avoid partial-word matches.
    tokens = out.split()
    for i, tok in enumerate(tokens):
        repl = _SYNONYM_MAP.get(tok)
        if repl:
            tokens[i] = repl
    return " ".join(tokens)


def _light_stem(token: str) -> str:
    """Lightweight Porter-style suffix stripping for English plurals and
    common verb forms. Stops short of full Porter to keep round-trip
    behaviour predictable for SEC vocabulary.
    """
    if len(token) <= 3:
        return token
    for suffix in ("ization", "izations", "ation", "ations", "ments",
                   "ment", "ings", "ing", "ies", "ied", "ied",
                   "ied", "ies", "ed", "es", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            stem = token[: -len(suffix)]
            # un-double trailing consonants e.g. 'shipping' -> 'ship'
            if (
                len(stem) >= 2
                and stem[-1] == stem[-2]
                and stem[-1] not in "aeiou"
            ):
                stem = stem[:-1]
            return stem
    return token


@lru_cache(maxsize=4096)
def canonicalize(title: str) -> str:
    """Return a canonical string for fuzzy matching. Idempotent."""
    if not title:
        return ""
    t = str(title).lower()
    t = _MONEY_RE.sub(" <money> ", t)
    t = _PERCENT_RE.sub(" <pct> ", t)
    t = _YEAR_RE.sub(" <year> ", t)
    t = _NUMERIC_RE.sub(" <num> ", t)
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t).strip()
    t = _strip_boilerplate(t)
    t = _replace_synonyms(t)
    # Stem and drop stopwords. Keep the synthetic <year>/<money>/<num>
    # placeholders so different magnitudes still align.
    tokens = []
    for tok in t.split():
        if tok in STOP_WORDS:
            continue
        if len(tok) <= 1:
            continue
        if tok.startswith("<") and tok.endswith(">"):
            tokens.append(tok)
            continue
        tokens.append(_light_stem(tok))
    return " ".join(tokens)


@lru_cache(maxsize=4096)
def token_set(title: str) -> frozenset[str]:
    canon = canonicalize(title)
    return frozenset(t for t in canon.split() if t)


@lru_cache(maxsize=4096)
def char_trigrams(title: str) -> tuple[str, ...]:
    canon = canonicalize(title)
    if not canon:
        return tuple()
    padded = f"  {canon}  "
    return tuple(padded[i:i + 3] for i in range(len(padded) - 2))


# ---------- similarity primitives ----------

def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0


def overlap_coefficient(a: Iterable[str], b: Iterable[str]) -> float:
    """|A ∩ B| / min(|A|, |B|) — useful when one side is much shorter."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def trigram_cosine(a: Sequence[str], b: Sequence[str]) -> float:
    if not a or not b:
        return 0.0
    ca, cb = Counter(a), Counter(b)
    dot = sum(ca[t] * cb[t] for t in ca.keys() & cb.keys())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# Concept canonicals after the same stemming the pipeline applies to
# every token. This lets `concept_overlap` recognise domain-specific
# matches like {infosec}, {supplier}, {litigation} even after stemming
# rewrites the canonical form (e.g. 'litigation' -> 'litig').
_CONCEPT_CANONICALS = frozenset(
    _light_stem(c) for c, _ in SYNONYM_GROUPS
)


def concept_tokens(title: str) -> frozenset[str]:
    """Subset of canonicalised tokens that map to one of our curated
    domain concepts (cyber, supplier, currency, ...). These tokens are
    high-information: any overlap on them is strong evidence of a real
    same-risk pair.
    """
    return frozenset(t for t in token_set(title) if t in _CONCEPT_CANONICALS)


def concept_overlap(title_a: str, title_b: str) -> float:
    """Overlap coefficient over domain concepts.

    Uses |A ∩ B| / min(|A|, |B|) rather than Jaccard because real risk
    factors usually invoke 1–2 concepts each. Jaccard would punish a
    title that mentions more concepts than its counterpart even when
    they are clearly the same risk.
    """
    ca = concept_tokens(title_a)
    cb = concept_tokens(title_b)
    if not ca or not cb:
        return 0.0
    inter = len(ca & cb)
    return inter / min(len(ca), len(cb))


def label_overlap(labels_a: Iterable[str], labels_b: Iterable[str]) -> float:
    """Labels are short keyword tags. We canonicalize each label and use
    Jaccard. If either side has no labels we return 0 so this signal
    only ever helps; the caller already weights it lightly.
    """
    norm_a = {canonicalize(x) for x in (labels_a or []) if str(x).strip()}
    norm_b = {canonicalize(x) for x in (labels_b or []) if str(x).strip()}
    norm_a.discard("")
    norm_b.discard("")
    if not norm_a or not norm_b:
        return 0.0
    inter = len(norm_a & norm_b)
    union = len(norm_a | norm_b)
    return inter / union if union else 0.0


def cosine(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(vec_a, vec_b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


# ---------- diff helpers for UI ----------

def token_diff(prior_title: str, latest_title: str) -> dict:
    """Return {added: [...], removed: [...]} of canonicalised tokens
    between two titles. Used by the UI to highlight wording shifts on
    modified pairs.
    """
    a = token_set(prior_title)
    b = token_set(latest_title)
    added = sorted(b - a)
    removed = sorted(a - b)
    return {"added": added, "removed": removed}
