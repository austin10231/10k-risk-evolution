#!/usr/bin/env python3
"""Offline evaluation harness for the Compare feature.

Usage
-----
    python scripts/eval_compare.py \
        --labels tests/compare_eval/labels.jsonl \
        --output scripts/eval_compare.report.json

The labels file is JSON-lines; each line describes one comparison:

    {
      "case_id": "AAPL-2023-vs-2022",
      "prior_path": "fixtures/AAPL_2022.json",
      "latest_path": "fixtures/AAPL_2023.json",
      "mode": "yoy",
      "ground_truth": [
        {"prior_title": "...", "latest_title": "...", "label": "retained"},
        {"prior_title": "...",                          "label": "removed"},
        {                       "latest_title": "...", "label": "added"}
      ]
    }

Where `label` is one of `retained | modified | added | removed`. The
script loads each filing's `result.json`, runs the comparator, then
compares predictions against ground truth, reporting:

- macro-F1 over the four classes
- pair-accuracy on the retained/modified rows
- per-category confusion counts

By design this script never calls Bedrock — embeddings are only used
when `--use-embeddings` is passed AND credentials are present. The
default lexical path is what gets enforced in CI.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.comparator import compare_risks


LABELS = ("retained", "modified", "added", "removed")


def _load_filing(path: str) -> Dict[str, Any]:
    abs_path = path if os.path.isabs(path) else os.path.join(_REPO_ROOT, path)
    with open(abs_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _predicted_label_map(prediction: Dict[str, Any]) -> Dict[Tuple[str, str], str]:
    """Return {(prior_title, latest_title): label}. For added/removed
    one side is empty string; same convention is expected in ground
    truth."""
    out: Dict[Tuple[str, str], str] = {}
    for p in prediction.get("pairs", {}).get("retained", []):
        out[(p["prior"]["title"], p["latest"]["title"])] = "retained"
    for p in prediction.get("pairs", {}).get("modified", []):
        out[(p["prior"]["title"], p["latest"]["title"])] = "modified"
    for it in prediction.get("pairs", {}).get("added", []):
        out[("", it["title"])] = "added"
    for it in prediction.get("pairs", {}).get("removed", []):
        out[(it["title"], "")] = "removed"
    return out


def _ground_truth_map(rows: List[Dict[str, Any]]) -> Dict[Tuple[str, str], str]:
    out: Dict[Tuple[str, str], str] = {}
    for row in rows or []:
        label = str(row.get("label", "") or "").strip().lower()
        if label not in LABELS:
            continue
        prior_title = str(row.get("prior_title", "") or "").strip()
        latest_title = str(row.get("latest_title", "") or "").strip()
        if label in ("retained", "modified"):
            if not prior_title or not latest_title:
                continue
            out[(prior_title, latest_title)] = label
        elif label == "added":
            if not latest_title:
                continue
            out[("", latest_title)] = label
        elif label == "removed":
            if not prior_title:
                continue
            out[(prior_title, "")] = label
    return out


def _macro_f1(per_class: Dict[str, Dict[str, int]]) -> float:
    f1s = []
    for cls in LABELS:
        tp = per_class[cls]["tp"]
        fp = per_class[cls]["fp"]
        fn = per_class[cls]["fn"]
        if tp + fp == 0 or tp + fn == 0:
            f1s.append(0.0)
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        if precision + recall == 0:
            f1s.append(0.0)
            continue
        f1s.append(2 * precision * recall / (precision + recall))
    return sum(f1s) / len(f1s) if f1s else 0.0


def _score_case(
    case_id: str,
    prediction: Dict[str, Any],
    ground_truth: List[Dict[str, Any]],
) -> Dict[str, Any]:
    pred_map = _predicted_label_map(prediction)
    truth_map = _ground_truth_map(ground_truth)

    per_class = {cls: {"tp": 0, "fp": 0, "fn": 0} for cls in LABELS}
    confusion = defaultdict(int)
    matches = []
    mismatches = []

    keys = set(pred_map.keys()) | set(truth_map.keys())
    for key in keys:
        pred = pred_map.get(key)
        truth = truth_map.get(key)
        if pred and truth and pred == truth:
            per_class[truth]["tp"] += 1
            confusion[(truth, pred)] += 1
            matches.append({"key": key, "label": truth})
        elif pred and truth:
            per_class[pred]["fp"] += 1
            per_class[truth]["fn"] += 1
            confusion[(truth, pred)] += 1
            mismatches.append({"key": key, "pred": pred, "truth": truth})
        elif pred:
            per_class[pred]["fp"] += 1
            confusion[("none", pred)] += 1
            mismatches.append({"key": key, "pred": pred, "truth": None})
        elif truth:
            per_class[truth]["fn"] += 1
            confusion[(truth, "none")] += 1
            mismatches.append({"key": key, "pred": None, "truth": truth})

    macro = _macro_f1(per_class)
    pair_rows = [r for r in ground_truth if r.get("label") in ("retained", "modified")]
    pair_correct = sum(
        1
        for r in pair_rows
        if pred_map.get((r.get("prior_title", ""), r.get("latest_title", ""))) == r.get("label")
    )
    pair_acc = pair_correct / len(pair_rows) if pair_rows else 0.0
    return {
        "case_id": case_id,
        "macro_f1": round(macro, 4),
        "pair_accuracy": round(pair_acc, 4),
        "per_class": per_class,
        "confusion": {f"{k[0]}->{k[1]}": v for k, v in confusion.items()},
        "summary": prediction.get("summary"),
        "scoring": prediction.get("scoring"),
        "mismatch_count": len(mismatches),
        "mismatch_examples": mismatches[:10],
    }


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True, help="Path to a JSONL labels file")
    parser.add_argument("--output", default="scripts/eval_compare.report.json")
    parser.add_argument("--use-embeddings", action="store_true",
                        help="Allow the Bedrock Titan path (requires AWS creds)")
    args = parser.parse_args(argv)

    labels_path = args.labels if os.path.isabs(args.labels) else os.path.join(_REPO_ROOT, args.labels)
    if not os.path.exists(labels_path):
        print(f"labels file not found: {labels_path}", file=sys.stderr)
        return 2

    embed_lookup = None
    if args.use_embeddings:
        try:
            from core.compare_embedding import build_lookup, is_enabled
            if is_enabled():
                embed_lookup = build_lookup()
        except Exception as exc:
            print(f"[warn] embedding service unavailable: {exc}", file=sys.stderr)

    case_reports = []
    aggregate = {cls: {"tp": 0, "fp": 0, "fn": 0} for cls in LABELS}
    with open(labels_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            entry = json.loads(line)
            case_id = entry.get("case_id") or f"line-{len(case_reports)+1}"
            prior = _load_filing(entry["prior_path"])
            latest = _load_filing(entry["latest_path"])
            mode = entry.get("mode") or "yoy"
            prediction = compare_risks(
                prior, latest, mode=mode, embed_lookup=embed_lookup
            )
            report = _score_case(case_id, prediction, entry.get("ground_truth", []))
            case_reports.append(report)
            for cls in LABELS:
                aggregate[cls]["tp"] += report["per_class"][cls]["tp"]
                aggregate[cls]["fp"] += report["per_class"][cls]["fp"]
                aggregate[cls]["fn"] += report["per_class"][cls]["fn"]

    overall_f1 = _macro_f1(aggregate)
    summary = {
        "cases": len(case_reports),
        "macro_f1_micro_aggregated": round(overall_f1, 4),
        "macro_f1_avg_of_cases": round(
            sum(r["macro_f1"] for r in case_reports) / len(case_reports), 4
        ) if case_reports else 0.0,
        "pair_accuracy_avg": round(
            sum(r["pair_accuracy"] for r in case_reports) / len(case_reports), 4
        ) if case_reports else 0.0,
        "per_class_totals": aggregate,
        "use_embeddings": bool(embed_lookup is not None),
    }

    out_path = args.output if os.path.isabs(args.output) else os.path.join(_REPO_ROOT, args.output)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "cases": case_reports}, f, indent=2, ensure_ascii=False)

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
