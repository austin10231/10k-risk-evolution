"""Run one 10-Q auto-fetch + extraction test and print a compact quality summary.

Example:
  python3 scripts/test_10q_single_fetch.py --company Apple --ticker AAPL --year 2024 --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _risk_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    risks = _as_list(result.get("risks"))
    category_count = 0
    sub_risk_count = 0
    category_samples: List[str] = []
    for block in risks:
        if not isinstance(block, dict):
            continue
        cat = str(block.get("category", "") or "").strip()
        if cat:
            category_count += 1
            if len(category_samples) < 8:
                category_samples.append(cat)
        for sr in _as_list(block.get("sub_risks")):
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
            else:
                title = str(sr or "").strip()
            if title:
                sub_risk_count += 1
    return {
        "risk_category_blocks": category_count,
        "sub_risks": sub_risk_count,
        "category_samples": category_samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Single-company 10-Q extraction test.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--ticker", default="")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--industry", default="Other")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist into records/S3. Omit for dry-run plan only.",
    )
    args = parser.parse_args()

    if not args.write:
        print(
            json.dumps(
                {
                    "ok": True,
                    "mode": "dry-run",
                    "plan": {
                        "company": args.company,
                        "ticker": args.ticker.upper(),
                        "industry": args.industry,
                        "filing_type": "10-Q",
                        "start_year": int(args.year),
                        "end_year": int(args.year),
                    },
                    "hint": "Add --write to execute fetch + extraction.",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    payload = backend._auto_fetch_and_extract(
        company=str(args.company).strip(),
        ticker=str(args.ticker).strip().upper(),
        industry=str(args.industry).strip() or "Other",
        filing_type="10-Q",
        start_year=int(args.year),
        end_year=int(args.year),
    )
    out: Dict[str, Any] = {
        "ok": bool(payload.get("ok")) if isinstance(payload, dict) else False,
        "count": int(payload.get("count", 0)) if isinstance(payload, dict) else 0,
        "skipped": payload.get("skipped", []) if isinstance(payload, dict) else [],
    }

    successes = payload.get("successes", []) if isinstance(payload, dict) and isinstance(payload.get("successes"), list) else []
    if successes:
        first = successes[0]
        result = first.get("result", {}) if isinstance(first, dict) and isinstance(first.get("result"), dict) else {}
        record = first.get("record", {}) if isinstance(first, dict) and isinstance(first.get("record"), dict) else {}
        out["record"] = {
            "record_id": record.get("record_id"),
            "company": record.get("company"),
            "ticker": record.get("ticker"),
            "year": record.get("year"),
            "filing_type": record.get("filing_type"),
            "filing_quarter": record.get("filing_quarter"),
            "industry": record.get("industry"),
        }
        out["quality"] = _risk_stats(result)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
