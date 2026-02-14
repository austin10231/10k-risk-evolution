"""
Compare two analysis results by sub-risk title matching.
Uses fuzzy matching (SequenceMatcher) to handle minor wording changes.
Works with hierarchical risks: [ { category, sub_risks: [str, ...] }, ... ]
"""

import re
import difflib


def _normalize(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _flatten_sub_risks(result: dict) -> list[dict]:
    """Flatten hierarchical risks into [{category, title, norm}]."""
    items = []
    for cat_block in result.get("risks", []):
        cat = cat_block.get("category", "Unknown")
        for sr in cat_block.get("sub_risks", []):
            items.append({
                "category": cat,
                "title": sr,
                "norm": _normalize(sr),
            })
    return items


def _find_best_match(norm: str, candidates: list[dict], threshold: float = 0.80) -> dict | None:
    """Find the best fuzzy match for norm among candidates."""
    best = None
    best_ratio = 0.0
    for c in candidates:
        ratio = difflib.SequenceMatcher(None, norm, c["norm"]).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best = c
    if best_ratio >= threshold:
        return best
    return None


def compare_risks(prior_result: dict, latest_result: dict) -> dict:
    """
    Returns {
        new_risks:     [{ category, title }],
        removed_risks: [{ category, title }],
    }
    """
    prior = _flatten_sub_risks(prior_result)
    latest = _flatten_sub_risks(latest_result)

    # Track which items have been matched
    matched_prior: set[int] = set()
    matched_latest: set[int] = set()

    # For each latest risk, try to find a match in prior
    for li, lr in enumerate(latest):
        unmatched_prior = [
            (pi, pr) for pi, pr in enumerate(prior) if pi not in matched_prior
        ]
        if not unmatched_prior:
            break
        best = None
        best_ratio = 0.0
        best_pi = -1
        for pi, pr in unmatched_prior:
            ratio = difflib.SequenceMatcher(None, lr["norm"], pr["norm"]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_pi = pi
        if best_ratio >= 0.75:
            matched_latest.add(li)
            matched_prior.add(best_pi)

    # Unmatched latest = NEW, unmatched prior = REMOVED
    new_risks = [
        {"category": latest[i]["category"], "title": latest[i]["title"]}
        for i in range(len(latest)) if i not in matched_latest
    ]
    removed_risks = [
        {"category": prior[i]["category"], "title": prior[i]["title"]}
        for i in range(len(prior)) if i not in matched_prior
    ]

    return {"new_risks": new_risks, "removed_risks": removed_risks}
