"""
Compare two structured risk-block results (prior vs latest)
using difflib sequence similarity.
"""

import difflib


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def compare_filings(
    prior_result: dict,
    latest_result: dict,
    sim_threshold: float = 0.30,
    identical_threshold: float = 0.95,
    top_n: int = 15,
) -> list[dict]:
    """
    Return a sorted list of top-N risk changes.

    Change types:
      NEW      — block exists in latest only
      REMOVED  — block exists in prior only
      MODIFIED — matched pair with sim < identical_threshold
    """
    prior_blocks = prior_result.get("risk_blocks", [])
    latest_blocks = latest_result.get("risk_blocks", [])

    # Build candidate similarity pairs
    candidates: list[tuple[float, int, int]] = []
    for li, lb in enumerate(latest_blocks):
        for pi, pb in enumerate(prior_blocks):
            sim = _similarity(lb["risk_text"], pb["risk_text"])
            if sim > sim_threshold:
                candidates.append((sim, li, pi))

    candidates.sort(reverse=True)

    matched_latest: set[int] = set()
    matched_prior: set[int] = set()
    matches: list[tuple[int, int, float]] = []

    for sim, li, pi in candidates:
        if li not in matched_latest and pi not in matched_prior:
            matched_latest.add(li)
            matched_prior.add(pi)
            matches.append((li, pi, sim))

    changes: list[dict] = []

    # NEW
    for i, lb in enumerate(latest_blocks):
        if i not in matched_latest:
            changes.append(
                {
                    "risk_theme": lb["risk_theme"],
                    "change_type": "NEW",
                    "change_score": 90,
                    "short_explanation": f"New risk disclosed: {lb['title'][:60]}",
                    "latest_block": lb,
                    "prior_block": None,
                }
            )

    # REMOVED
    for j, pb in enumerate(prior_blocks):
        if j not in matched_prior:
            changes.append(
                {
                    "risk_theme": pb["risk_theme"],
                    "change_type": "REMOVED",
                    "change_score": 85,
                    "short_explanation": f"Risk no longer disclosed: {pb['title'][:60]}",
                    "latest_block": None,
                    "prior_block": pb,
                }
            )

    # MODIFIED
    for li, pi, sim in matches:
        if sim < identical_threshold:
            score = int((1 - sim) * 100)
            changes.append(
                {
                    "risk_theme": latest_blocks[li]["risk_theme"],
                    "change_type": "MODIFIED",
                    "change_score": max(score, 5),
                    "short_explanation": (
                        f"Language changed ({sim:.0%} similar): "
                        f"{latest_blocks[li]['title'][:50]}"
                    ),
                    "latest_block": latest_blocks[li],
                    "prior_block": prior_blocks[pi],
                }
            )

    # Sort: NEW → REMOVED → MODIFIED, then by score desc
    order = {"NEW": 0, "REMOVED": 1, "MODIFIED": 2}
    changes.sort(key=lambda c: (order[c["change_type"]], -c["change_score"]))

    return changes[:top_n]
