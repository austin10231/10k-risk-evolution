"""
Compare two analysis results by risk title matching.

Only produces NEW and REMOVED — no MODIFIED scoring (MVP).
"""

import re


def _normalize(title: str) -> str:
    """Lowercase, strip punctuation and extra whitespace."""
    t = title.lower()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compare_risks(prior_result: dict, latest_result: dict) -> dict:
    """
    Returns {
        new_risks:     [{title, content}, ...],
        removed_risks: [{title, content}, ...],
    }
    """
    prior_risks = prior_result.get("risks", [])
    latest_risks = latest_result.get("risks", [])

    prior_titles = {_normalize(r["title"]): r for r in prior_risks}
    latest_titles = {_normalize(r["title"]): r for r in latest_risks}

    prior_set = set(prior_titles.keys())
    latest_set = set(latest_titles.keys())

    new_risks = [
        latest_titles[t] for t in sorted(latest_set - prior_set)
    ]
    removed_risks = [
        prior_titles[t] for t in sorted(prior_set - latest_set)
    ]

    return {
        "new_risks": new_risks,
        "removed_risks": removed_risks,
    }
