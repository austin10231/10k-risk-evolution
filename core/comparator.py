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
                dashboard_category = sr.get("dashboard_category", "")
                original_category = sr.get("original_category", "") or cat
                labels = sr.get("labels", [])
            elif isinstance(sr, str):
                title = sr
                dashboard_category = ""
                original_category = cat
                labels = []
            else:
                title = str(sr)
                dashboard_category = ""
                original_category = cat
                labels = []
            items.append(
                {
                    "category": dashboard_category or cat,
                    "dashboard_category": dashboard_category,
                    "original_category": original_category,
                    "labels": labels if isinstance(labels, list) else [],
                    "title": title,
                    "norm": _normalize(title),
                }
            )
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
        "new_risks": [{
            "category": latest[i]["category"],
            "dashboard_category": latest[i].get("dashboard_category", ""),
            "original_category": latest[i].get("original_category", ""),
            "labels": latest[i].get("labels", []),
            "title": latest[i]["title"],
        }
                       for i in range(len(latest)) if i not in ml],
        "removed_risks": [{
            "category": prior[i]["category"],
            "dashboard_category": prior[i].get("dashboard_category", ""),
            "original_category": prior[i].get("original_category", ""),
            "labels": prior[i].get("labels", []),
            "title": prior[i]["title"],
        }
                           for i in range(len(prior)) if i not in mp],
    }
