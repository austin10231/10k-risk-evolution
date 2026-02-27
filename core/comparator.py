"""Compare by sub-risk title fuzzy matching."""

import re
import difflib


def _normalize(title):
    if not isinstance(title, str):
        title = str(title)
    t = re.sub(r"[^\w\s]", "", title.lower())
    return re.sub(r"\s+", " ", t).strip()


def _flatten_sub_risks(result):
    items = []
    for cb in result.get("risks", []):
        cat = cb.get("category", "Unknown")
        for sr in cb.get("sub_risks", []):
            if isinstance(sr, dict):
                title = sr.get("title", str(sr))
            elif isinstance(sr, str):
                title = sr
            else:
                title = str(sr)
            items.append({"category": cat, "title": title, "norm": _normalize(title)})
    return items


def compare_risks(prior_result, latest_result):
    prior = _flatten_sub_risks(prior_result)
    latest = _flatten_sub_risks(latest_result)
    mp, ml = set(), set()
    for li, lr in enumerate(latest):
        up = [(pi, pr) for pi, pr in enumerate(prior) if pi not in mp]
        if not up:
            break
        best_r, best_pi = 0.0, -1
        for pi, pr in up:
            r = difflib.SequenceMatcher(None, lr["norm"], pr["norm"]).ratio()
            if r > best_r:
                best_r, best_pi = r, pi
        if best_r >= 0.75:
            ml.add(li)
            mp.add(best_pi)
    return {
        "new_risks": [{"category": latest[i]["category"], "title": latest[i]["title"]}
                       for i in range(len(latest)) if i not in ml],
        "removed_risks": [{"category": prior[i]["category"], "title": prior[i]["title"]}
                           for i in range(len(prior)) if i not in mp],
    }
