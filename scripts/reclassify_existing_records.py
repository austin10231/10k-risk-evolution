"""Backfill dashboard_category/original_category for stored risk result JSON.

Default mode is a dry run. Use --write only from an environment with Bedrock
runtime credentials, otherwise weak keyword matches would be written as
"General & Other" instead of using the LLM fallback.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend


def _has_missing_dashboard_categories(result: dict) -> bool:
    for block in result.get("risks", []) if isinstance(result, dict) else []:
        if not isinstance(block, dict):
            continue
        for sub in block.get("sub_risks", []) or []:
            if not isinstance(sub, dict):
                return True
            if str(sub.get("dashboard_category", "") or "").strip() not in backend.FIXED_RISK_CATEGORIES:
                return True
            if not str(sub.get("original_category", "") or "").strip():
                return True
    return False


def run(limit: int = 0, write: bool = False, allow_no_llm: bool = False) -> dict:
    if write and not allow_no_llm and not backend._has_bedrock_runtime_credentials():
        return {
            "ok": False,
            "error": "Refusing to write without Bedrock runtime credentials. Re-run with credentials, or pass --allow-no-llm.",
        }

    records = backend._load_index()
    if limit > 0:
        records = records[:limit]

    processed = 0
    changed = 0
    written = 0
    skipped = 0
    errors = []
    examples = []

    for rec in records:
        record_id = str((rec or {}).get("record_id", "") or "").strip()
        if not record_id:
            skipped += 1
            continue
        try:
            result = backend._load_result(record_id)
            if not isinstance(result, dict) or not isinstance(result.get("risks"), list):
                skipped += 1
                continue
            processed += 1
            needs_update = _has_missing_dashboard_categories(result)
            annotated = backend._result_with_dashboard_categories(result)
            if not needs_update and annotated == result:
                skipped += 1
                continue

            changed += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "record_id": record_id,
                        "company": rec.get("company", ""),
                        "year": rec.get("year", ""),
                    }
                )
            if write:
                backend._write_s3_bytes(
                    f"{backend.RESULTS_PREFIX}/{record_id}.json",
                    json.dumps(annotated, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
                )
                written += 1
        except Exception as exc:
            errors.append({"record_id": record_id, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": not errors,
        "mode": "write" if write else "dry-run",
        "processed": processed,
        "changed": changed,
        "written": written,
        "skipped": skipped,
        "errors": errors[:30],
        "examples": examples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of index records to scan.")
    parser.add_argument("--write", action="store_true", help="Write changed result JSON back to S3.")
    parser.add_argument(
        "--allow-no-llm",
        action="store_true",
        help="Allow writes without Bedrock credentials; weak matches will become General & Other.",
    )
    args = parser.parse_args()
    payload = run(limit=args.limit, write=args.write, allow_no_llm=args.allow_no_llm)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
