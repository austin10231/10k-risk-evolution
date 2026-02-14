from typing import Dict, List, Tuple
import difflib

def _normalize(text: str) -> str:
    return " ".join(text.lower().split())

def _best_match(block, candidates) -> Tuple[float, Dict]:
    """
    Very simple similarity:
    use difflib ratio on normalized text
    """
    best = (0.0, None)
    t = _normalize(block["risk_text"])
    for c in candidates:
        ratio = difflib.SequenceMatcher(None, t, _normalize(c["risk_text"])).ratio()
        if ratio > best[0]:
            best = (ratio, c)
    return best[0], best[1]

def compare_reports(latest: Dict, prior: Dict, company: str, year_latest: int, year_prior: int) -> Dict:
    latest_blocks = latest.get("risk_blocks", [])
    prior_blocks = prior.get("risk_blocks", [])

    changes = []
    used_prior = set()

    # NEW / MODIFIED detection
    for lb in latest_blocks:
        score, pb = _best_match(lb, prior_blocks)
        if pb is None or score < 0.55:
            changes.append({
                "risk_theme": lb.get("risk_theme", "other"),
                "change_type": "NEW",
                "change_score": int((1 - score) * 100) if pb else 90,
                "short_explanation": "This risk block does not appear in the prior filing (or is substantially different).",
                "old_text": None,
                "new_text": lb.get("risk_text"),
                "latest_block_id": lb.get("block_id"),
                "prior_block_id": None,
            })
        else:
            used_prior.add(pb.get("block_id"))
            if score < 0.85:
                changes.append({
                    "risk_theme": lb.get("risk_theme", "other"),
                    "change_type": "MODIFIED",
                    "change_score": int((1 - score) * 100),
                    "short_explanation": "This risk block exists in both filings but the wording changed materially.",
                    "old_text": pb.get("risk_text"),
                    "new_text": lb.get("risk_text"),
                    "latest_block_id": lb.get("block_id"),
                    "prior_block_id": pb.get("block_id"),
                })

    # REMOVED detection
    latest_ids = set(b.get("block_id") for b in latest_blocks)
    for pb in prior_blocks:
        if pb.get("block_id") in used_prior:
            continue
        # If no strong match in latest, treat as removed
        score, lb = _best_match(pb, latest_blocks)
        if lb is None or score < 0.55:
            changes.append({
                "risk_theme": pb.get("risk_theme", "other"),
                "change_type": "REMOVED",
                "change_score": int((1 - score) * 100) if lb else 90,
                "short_explanation": "This risk block appears in the prior filing but not in the latest filing.",
                "old_text": pb.get("risk_text"),
                "new_text": None,
                "latest_block_id": None,
                "prior_block_id": pb.get("block_id"),
            })

    # sort by score desc, then NEW first
    priority = {"NEW": 0, "REMOVED": 1, "MODIFIED": 2}
    changes.sort(key=lambda x: (priority.get(x["change_type"], 9), -x.get("change_score", 0)))

    return {
        "company": company,
        "compare_pair": {"latest_year": year_latest, "prior_year": year_prior},
        "risk_changes": changes[:15],  # Top N
    }
