"""Risk-evolution comparator.

Public entrypoint is `compare_risks(prior_result, latest_result, mode=..., ...)`.
It produces four buckets (retained / modified / added / removed) plus a
9-category coverage matrix. The legacy `new_risks` / `removed_risks`
keys are still populated so downstream agent code keeps working.

Pipeline
--------
1.  Flatten each result's risks into a list of sub-risk dicts (carrying
    `title`, `labels`, and the bucket key the matcher will use).
2.  Group both sides by bucket key (the dashboard_category when
    available, else "General & Other"). In `cross` mode for cases where
    the dashboard category is missing on either side, fall back to a
    single "ALL" bucket so we don't lose matches.
3.  For each bucket build a similarity matrix using the hybrid scorer
    (token Jaccard + char-trigram cosine + label overlap, plus an
    embedding cosine when an embedder is supplied).
4.  Run a rectangular Hungarian assignment to pick the optimum pairing.
5.  Split pairs into `retained` (>= T_high), `modified`
    (T_low ≤ score < T_high); unpaired latest items become `added`,
    unpaired prior items become `removed`.

Threshold defaults
------------------
- YoY    : T_low=0.62, T_high=0.85  (average-confidence preset)
- Cross  : T_low=0.55, T_high=0.80  (looser because cross-company
                                     vocabulary diverges further)

Callers can override by passing `threshold_low` / `threshold_high`.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from core.compare_assignment import solve_assignment
from core.compare_text import (
    canonicalize,
    char_trigrams,
    concept_overlap,
    cosine,
    jaccard,
    label_overlap,
    token_diff,
    token_set,
    trigram_cosine,
)


# Public default thresholds. Tweakable from `_compare_payload`.
# Calibrated against the lexical-only pipeline on a hand-built sample;
# when the Bedrock embedding service is available, real-world scores
# climb ~0.10 on equivalent pairs, so the same thresholds remain safe.
DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "yoy":   {"low": 0.58, "high": 0.82},
    "cross": {"low": 0.52, "high": 0.78},
}

# Floor used when emitting `pairs.candidates` — pairs below this score
# are never returned even if Hungarian picks them. Set well below the
# lowest threshold so the UI slider can still drop into "loose" mode
# without needing another round-trip.
CANDIDATE_FLOOR = 0.45

# Score weights for the hybrid lexical formula (no embedding).
# `concept` captures shared SEC-domain concepts (cyber/supplier/...)
# canonicalised through the synonym table; it is by far the strongest
# lexical signal on its own.
WEIGHTS_LEXICAL = {
    "concept": 0.35,
    "jaccard": 0.25,
    "trigram": 0.20,
    "label":   0.20,
}

# Score weights when an embedding is available. Embedding subsumes
# most of the trigram signal, so we drop it and rebalance.
WEIGHTS_HYBRID = {
    "embed":   0.55,
    "concept": 0.20,
    "jaccard": 0.15,
    "label":   0.10,
}


# ---------- flattening ----------

def _coerce_labels(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    out: List[str] = []
    for v in value:
        s = str(v or "").strip()
        if s:
            out.append(s)
    return out


def _flatten(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return [{title, labels, dashboard_category, original_category}, ...]
    in the order they appear in the source filing. Position is preserved
    so downstream callers can do emphasis-shift analysis if desired.
    """
    items: List[Dict[str, Any]] = []
    if not isinstance(result, dict):
        return items
    for block in result.get("risks", []) or []:
        if not isinstance(block, dict):
            continue
        orig_cat = str(block.get("category", "") or "Unknown").strip() or "Unknown"
        for sr in block.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = _coerce_labels(sr.get("labels"))
                dash = str(sr.get("dashboard_category", "") or "").strip()
                pre_orig = str(sr.get("original_category", "") or "").strip()
            elif isinstance(sr, str):
                title = sr.strip()
                labels = []
                dash = ""
                pre_orig = ""
            else:
                title = str(sr or "").strip()
                labels = []
                dash = ""
                pre_orig = ""
            if not title:
                continue
            items.append({
                "title": title,
                "labels": labels,
                "dashboard_category": dash,
                "original_category": pre_orig or orig_cat,
                "category": dash or orig_cat,  # legacy alias
                "position": len(items),
            })
    return items


# ---------- bucketing ----------

def _bucket_key(item: Dict[str, Any]) -> str:
    return str(item.get("dashboard_category") or "").strip() or "General & Other"


def _bucketise(
    items: Sequence[Dict[str, Any]],
    *,
    use_buckets: bool,
) -> Dict[str, List[int]]:
    """Map bucket-key -> list of indices into `items`."""
    if not use_buckets:
        return {"ALL": list(range(len(items)))}
    buckets: Dict[str, List[int]] = {}
    for idx, it in enumerate(items):
        key = _bucket_key(it)
        buckets.setdefault(key, []).append(idx)
    return buckets


# ---------- scoring ----------

def _hybrid_score(
    a: Dict[str, Any],
    b: Dict[str, Any],
    *,
    embed_lookup: Optional[Callable[[str], Optional[Sequence[float]]]] = None,
) -> Tuple[float, Dict[str, float]]:
    """Return (combined_score, components) for one candidate pair."""
    ta = a["title"]
    tb = b["title"]

    tok_a = token_set(ta)
    tok_b = token_set(tb)
    tri_a = char_trigrams(ta)
    tri_b = char_trigrams(tb)

    j = jaccard(tok_a, tok_b)
    tri = trigram_cosine(tri_a, tri_b)
    lab = label_overlap(a.get("labels"), b.get("labels"))
    concept = concept_overlap(ta, tb)

    emb_score = 0.0
    have_embed = False
    if embed_lookup is not None:
        va = embed_lookup(ta)
        vb = embed_lookup(tb)
        if va is not None and vb is not None:
            emb_score = cosine(va, vb)
            have_embed = True

    if have_embed:
        w = WEIGHTS_HYBRID
        # When labels are missing on either side the `label` term is 0
        # by design — redistribute that weight onto the embedding and
        # concept signals so we don't penalise pairs for lacking tags.
        label_w = w["label"] if lab > 0 else 0.0
        spillover = w["label"] - label_w
        combined = (
            (w["embed"] + 0.6 * spillover) * emb_score
            + (w["concept"] + 0.3 * spillover) * concept
            + (w["jaccard"] + 0.1 * spillover) * j
            + label_w * lab
        )
    else:
        w = WEIGHTS_LEXICAL
        label_w = w["label"] if lab > 0 else 0.0
        spillover = w["label"] - label_w
        combined = (
            (w["concept"] + 0.5 * spillover) * concept
            + (w["jaccard"] + 0.25 * spillover) * j
            + (w["trigram"] + 0.25 * spillover) * tri
            + label_w * lab
        )

    # Literal carry-over: identical canonical strings should never drop
    # below 0.99 even if some component (e.g. embedding) wobbles.
    if canonicalize(ta) and canonicalize(ta) == canonicalize(tb):
        combined = max(combined, 0.99)

    components = {
        "concept": round(concept, 4),
        "jaccard": round(j, 4),
        "trigram": round(tri, 4),
        "label":   round(lab, 4),
        "embed":   round(emb_score, 4) if have_embed else None,
    }
    return float(min(1.0, max(0.0, combined))), components


# ---------- per-bucket matching ----------

def _match_bucket(
    prior_items: Sequence[Dict[str, Any]],
    latest_items: Sequence[Dict[str, Any]],
    *,
    prior_indices: Sequence[int],
    latest_indices: Sequence[int],
    embed_lookup: Optional[Callable[[str], Optional[Sequence[float]]]],
) -> List[Dict[str, Any]]:
    """Return list of candidate pair dicts (above CANDIDATE_FLOOR)."""
    if not prior_indices or not latest_indices:
        return []

    rows = len(prior_indices)
    cols = len(latest_indices)
    score_matrix: List[List[float]] = [[0.0] * cols for _ in range(rows)]
    component_matrix: List[List[Dict[str, float]]] = [
        [{} for _ in range(cols)] for _ in range(rows)
    ]

    for r, pi in enumerate(prior_indices):
        for c, li in enumerate(latest_indices):
            score, comps = _hybrid_score(
                prior_items[pi],
                latest_items[li],
                embed_lookup=embed_lookup,
            )
            score_matrix[r][c] = score
            component_matrix[r][c] = comps

    assignment = solve_assignment(score_matrix, floor=CANDIDATE_FLOOR)
    pairs: List[Dict[str, Any]] = []
    for r, c, score in assignment:
        pi = prior_indices[r]
        li = latest_indices[c]
        pairs.append({
            "prior_index": pi,
            "latest_index": li,
            "score": round(score, 4),
            "components": component_matrix[r][c],
        })
    return pairs


# ---------- public API ----------

def _public_item(item: Dict[str, Any]) -> Dict[str, Any]:
    """Shape an item for the JSON response (preserve legacy keys)."""
    dash = item.get("dashboard_category") or ""
    orig = item.get("original_category") or ""
    return {
        "title":              item["title"],
        "labels":             list(item.get("labels") or []),
        "dashboard_category": dash,
        "original_category":  orig,
        "category":           dash or orig or "",
    }


def compare_risks(
    prior_result: Dict[str, Any],
    latest_result: Dict[str, Any],
    *,
    mode: str = "yoy",
    threshold_low: Optional[float] = None,
    threshold_high: Optional[float] = None,
    embed_lookup: Optional[Callable[[str], Optional[Sequence[float]]]] = None,
) -> Dict[str, Any]:
    mode_key = "cross" if str(mode or "").lower().startswith("cross") else "yoy"
    defaults = DEFAULT_THRESHOLDS[mode_key]
    t_low = float(threshold_low) if threshold_low is not None else defaults["low"]
    t_high = float(threshold_high) if threshold_high is not None else defaults["high"]
    if t_high < t_low:
        t_high = t_low

    prior_items = _flatten(prior_result)
    latest_items = _flatten(latest_result)

    # Decide whether to bucket. If either side has zero items carrying
    # a dashboard_category, fall back to a single "ALL" bucket so we
    # don't silently lose all matches just because the upstream
    # classifier didn't run.
    prior_with_cat = sum(1 for x in prior_items if x.get("dashboard_category"))
    latest_with_cat = sum(1 for x in latest_items if x.get("dashboard_category"))
    use_buckets = prior_with_cat > 0 and latest_with_cat > 0

    prior_buckets = _bucketise(prior_items, use_buckets=use_buckets)
    latest_buckets = _bucketise(latest_items, use_buckets=use_buckets)

    all_pairs: List[Dict[str, Any]] = []
    matched_prior: set[int] = set()
    matched_latest: set[int] = set()

    bucket_keys = set(prior_buckets) | set(latest_buckets)
    for key in bucket_keys:
        pi_idx = prior_buckets.get(key, [])
        li_idx = latest_buckets.get(key, [])
        pairs = _match_bucket(
            prior_items,
            latest_items,
            prior_indices=pi_idx,
            latest_indices=li_idx,
            embed_lookup=embed_lookup,
        )
        for pair in pairs:
            pair["bucket"] = key
            matched_prior.add(pair["prior_index"])
            matched_latest.add(pair["latest_index"])
        all_pairs.extend(pairs)

    # Sort pairs descending by score so the UI gets a stable order and
    # the highest-confidence matches dominate downstream summaries.
    all_pairs.sort(key=lambda p: (-p["score"], p["bucket"]))

    retained: List[Dict[str, Any]] = []
    modified: List[Dict[str, Any]] = []
    for pair in all_pairs:
        pi = pair["prior_index"]
        li = pair["latest_index"]
        prior_item = prior_items[pi]
        latest_item = latest_items[li]
        record = {
            "prior":  _public_item(prior_item),
            "latest": _public_item(latest_item),
            "score":  pair["score"],
            "components": pair["components"],
            "bucket": pair["bucket"],
            "title_changed": canonicalize(prior_item["title"]) != canonicalize(latest_item["title"]),
            "diff": token_diff(prior_item["title"], latest_item["title"]),
        }
        if pair["score"] >= t_high:
            retained.append(record)
        elif pair["score"] >= t_low:
            modified.append(record)
        else:
            # Below T_low: treat as unmatched on both sides so the
            # added/removed lists reflect the user's chosen threshold.
            matched_prior.discard(pi)
            matched_latest.discard(li)

    added = [
        _public_item(latest_items[i])
        for i in range(len(latest_items))
        if i not in matched_latest
    ]
    removed = [
        _public_item(prior_items[i])
        for i in range(len(prior_items))
        if i not in matched_prior
    ]

    # ---- category coverage matrix ----
    category_matrix = _build_category_matrix(
        prior_items, latest_items, retained, modified, added, removed
    )

    # ---- legacy keys (downstream agent code still reads these) ----
    legacy_new = added
    legacy_removed = removed

    return {
        "mode": mode_key,
        "scoring": {
            "threshold_low":  round(t_low, 4),
            "threshold_high": round(t_high, 4),
            "candidate_floor": CANDIDATE_FLOOR,
            "method": "embed+lex" if embed_lookup else "lexical",
            "weights": dict(WEIGHTS_HYBRID if embed_lookup else WEIGHTS_LEXICAL),
        },
        "pairs": {
            "retained": retained,
            "modified": modified,
            "added":    added,
            "removed":  removed,
            # Every Hungarian pair that scored >= CANDIDATE_FLOOR — lets
            # the front-end slider re-bucket locally without another
            # round-trip to the backend.
            "candidates": [
                {
                    "prior":  _public_item(prior_items[p["prior_index"]]),
                    "latest": _public_item(latest_items[p["latest_index"]]),
                    "score":  p["score"],
                    "components": p["components"],
                    "bucket": p["bucket"],
                    "title_changed": canonicalize(prior_items[p["prior_index"]]["title"])
                                       != canonicalize(latest_items[p["latest_index"]]["title"]),
                    "diff": token_diff(
                        prior_items[p["prior_index"]]["title"],
                        latest_items[p["latest_index"]]["title"],
                    ),
                }
                for p in all_pairs
            ],
        },
        "category_matrix": category_matrix,
        "summary": {
            "retained": len(retained),
            "modified": len(modified),
            "added":    len(added),
            "removed":  len(removed),
            "prior_total":  len(prior_items),
            "latest_total": len(latest_items),
            "churn_rate":   _churn_rate(retained, modified, added, removed),
            "avg_match_score": _avg_score(retained + modified),
            # Legacy aliases for backward compatibility.
            "new_count":     len(legacy_new),
            "removed_count": len(legacy_removed),
        },
        "new_risks":     legacy_new,
        "removed_risks": legacy_removed,
    }


def _churn_rate(retained, modified, added, removed) -> float:
    total = len(retained) + len(modified) + len(added) + len(removed)
    if total == 0:
        return 0.0
    return round((len(modified) + len(added) + len(removed)) / total, 4)


def _avg_score(pairs: Sequence[Dict[str, Any]]) -> float:
    if not pairs:
        return 0.0
    return round(sum(p["score"] for p in pairs) / len(pairs), 4)


def _build_category_matrix(
    prior_items: Sequence[Dict[str, Any]],
    latest_items: Sequence[Dict[str, Any]],
    retained: Sequence[Dict[str, Any]],
    modified: Sequence[Dict[str, Any]],
    added: Sequence[Dict[str, Any]],
    removed: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """For each dashboard_category that appears on either side, report
    counts for the four buckets plus totals. Categories are returned in
    descending order of prior+latest total so the most populous ones
    surface first in the UI.
    """
    cats: Dict[str, Dict[str, int]] = {}

    def _empty():
        return {
            "retained": 0, "modified": 0, "added": 0, "removed": 0,
            "prior_total": 0, "latest_total": 0,
        }

    def _cat_of(item: Dict[str, Any]) -> str:
        return str(item.get("dashboard_category") or item.get("category") or "General & Other").strip() or "General & Other"

    for it in prior_items:
        cats.setdefault(_cat_of(it), _empty())["prior_total"] += 1
    for it in latest_items:
        cats.setdefault(_cat_of(it), _empty())["latest_total"] += 1
    for r in retained:
        cats.setdefault(_cat_of(r["latest"]), _empty())["retained"] += 1
    for m in modified:
        cats.setdefault(_cat_of(m["latest"]), _empty())["modified"] += 1
    for a in added:
        cats.setdefault(_cat_of(a), _empty())["added"] += 1
    for rem in removed:
        cats.setdefault(_cat_of(rem), _empty())["removed"] += 1

    rows = [
        {"category": cat, **counts}
        for cat, counts in cats.items()
    ]
    rows.sort(key=lambda r: (-(r["prior_total"] + r["latest_total"]), r["category"]))
    return rows
