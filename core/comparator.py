"""
Compare two analysis results by sub-risk title matching.
Works with the hierarchical risks format:
  risks: [ { category, sub_risks: [str, ...] }, ... ]
"""

import re


def _normalize(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _flatten_sub_risks(result: dict) -> list[dict]:
    """Flatten hierarchical risks into [{category, title_normalized, title_original}]."""
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


def compare_risks(prior_result: dict, latest_result: dict) -> dict:
    """
    Returns {
        new_risks:     [{ category, title }],
        removed_risks: [{ category, title }],
    }
    """
    prior = _flatten_sub_risks(prior_result)
    latest = _flatten_sub_risks(latest_result)

    prior_norms = {r["norm"]: r for r in prior}
    latest_norms = {r["norm"]: r for r in latest}

    prior_set = set(prior_norms.keys())
    latest_set = set(latest_norms.keys())

    new_risks = [
        {"category": latest_norms[n]["category"], "title": latest_norms[n]["title"]}
        for n in sorted(latest_set - prior_set)
    ]
    removed_risks = [
        {"category": prior_norms[n]["category"], "title": prior_norms[n]["title"]}
        for n in sorted(prior_set - latest_set)
    ]

    return {"new_risks": new_risks, "removed_risks": removed_risks}
