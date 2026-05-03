"""Re-score agent priority (RPI) for every risks JSON under ``10k_filings/``
in S3 — without re-extracting risks.

For each ``10k_filings/<industry>/<company_dir>/<year>_10K_risks.json`` we
re-run :func:`agentcore_deploy.main._generate_agent_priority_report` (the
three-dimensional LLM scoring + agent report), mutate
``result["agent_report"]`` in place, and write the JSON back to the same
key. The ``risks`` array, ``company_overview``, and HTML are **not**
touched.

Use this when only the priority scoring layer has changed (new prompt,
new weights, new modelId — e.g. Nova Pro replaced Claude Opus 4.7) and you
want to refresh RPI without paying for a full Item 1A re-extraction. A
typical run costs roughly one Bedrock invocation per record (or one per
40-risk batch — see ``_PRIORITY_BATCH_SIZE`` in ``agentcore_deploy/agent.py``)
plus one for the executive-summary report.

Usage::

    # 1. Plan only — prints what would happen, no S3 writes, no Bedrock cost.
    python scripts/rescore_agent_priority.py --dry-run

    # 2. Real run. AWS + Bedrock credentials must be in env.
    python scripts/rescore_agent_priority.py --write

    # Filter to one industry / one ticker for partial roll-outs.
    python scripts/rescore_agent_priority.py --write --industry Technology
    python scripts/rescore_agent_priority.py --write --ticker AAPL

    # Skip records that already carry a successful agent_report (resume after
    # a partial failure or re-run only the records that originally errored).
    python scripts/rescore_agent_priority.py --write --skip-already-scored

    # Cap the run at N records (handy on Railway one-offs to bound cost).
    python scripts/rescore_agent_priority.py --write --limit 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extraction_pipeline as ep  # noqa: E402
from scripts.industry_mapping import COMPANIES  # noqa: E402

JSON_KEY_RE = re.compile(
    r"^10k_filings/(?P<industry>[^/]+)/(?P<dir>[^/]+)/(?P<year>\d{4})_10K_risks\.json$"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _list_risks_json_keys() -> list[str]:
    keys: list[str] = []
    paginator = ep.s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=ep.s3_bucket(), Prefix="10k_filings/"):
        for obj in page.get("Contents", []) or []:
            k = str(obj.get("Key") or "")
            if JSON_KEY_RE.match(k):
                keys.append(k)
    return sorted(keys)


def _resolve_company_name(company_dir: str, result: dict) -> str:
    """Pull company display name from the existing JSON's company_overview
    first; fall back to industry_mapping; last resort is the directory name
    with underscores replaced by spaces."""
    if isinstance(result, dict):
        overview = result.get("company_overview") if isinstance(result.get("company_overview"), dict) else {}
        name = str((overview or {}).get("company") or "").strip()
        if name:
            return name
    for ticker, meta in COMPANIES.items():
        if str(meta.get("dir") or "").lower() == company_dir.lower():
            return str(meta.get("name") or ticker)
    return company_dir.replace("_", " ")


def _ticker_for_company_dir(company_dir: str) -> Optional[str]:
    for ticker, meta in COMPANIES.items():
        if str(meta.get("dir") or "").lower() == company_dir.lower():
            return ticker
    return None


def _has_successful_agent_report(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    rep = result.get("agent_report") if isinstance(result.get("agent_report"), dict) else None
    if not rep:
        return False
    status = str(rep.get("scoring_status") or "").lower()
    if status in ("ok", "partial"):
        return True
    # Older records pre-date scoring_status — treat the presence of a non-empty
    # priority_matrix as evidence of a usable score.
    pm = rep.get("priority_matrix")
    return isinstance(pm, dict) and bool(pm)


def rescore(
    *,
    write: bool,
    industry_filter: str = "",
    ticker_filter: str = "",
    skip_already_scored: bool = False,
    limit: int = 0,
) -> dict:
    started = _now_iso()
    keys = _list_risks_json_keys()
    print(f"[plan] found {len(keys)} risks JSON objects under 10k_filings/", flush=True)

    if not write:
        print("[plan] DRY RUN — no S3 writes, no Bedrock invocations", flush=True)

    report: dict = {
        "started_at": started,
        "ended_at": None,
        "total": len(keys),
        "ok": [],
        "skipped": [],
        "failed": [],
        "write": bool(write),
        "industry_filter": industry_filter,
        "ticker_filter": ticker_filter,
        "skip_already_scored": bool(skip_already_scored),
        "limit": int(limit or 0),
    }

    processed = 0
    for idx, key in enumerate(keys, start=1):
        m = JSON_KEY_RE.match(key)
        if not m:
            continue
        industry = m.group("industry")
        company_dir = m.group("dir")
        year = int(m.group("year"))

        if industry_filter and industry != industry_filter:
            continue
        if ticker_filter:
            ticker = _ticker_for_company_dir(company_dir)
            if not ticker or ticker.upper() != ticker_filter.upper():
                continue
        if limit and processed >= limit:
            break
        processed += 1

        t0 = time.time()
        try:
            raw = ep.get_bytes(key)
            if not raw:
                raise RuntimeError("empty body")
            try:
                result = json.loads(raw.decode("utf-8", errors="ignore"))
            except Exception as exc:
                raise RuntimeError(f"could not parse JSON: {exc}") from exc
            if not isinstance(result, dict):
                raise RuntimeError(f"json root is {type(result).__name__}, not dict")

            if skip_already_scored and _has_successful_agent_report(result):
                duration = time.time() - t0
                print(
                    f"[{idx}/{len(keys)}] SKIP {key} reason=already_scored {duration:.1f}s",
                    flush=True,
                )
                report["skipped"].append({"key": key, "reason": "already_scored"})
                continue

            risks = result.get("risks", []) if isinstance(result.get("risks"), list) else []
            sub_risk_count = sum(
                len(b.get("sub_risks", []) or [])
                for b in (risks if isinstance(risks, list) else [])
                if isinstance(b, dict)
            )
            if not risks or sub_risk_count == 0:
                print(
                    f"[{idx}/{len(keys)}] SKIP {key} reason=no_risks_in_json",
                    flush=True,
                )
                report["skipped"].append({"key": key, "reason": "no_risks"})
                continue

            company = _resolve_company_name(company_dir, result)

            if not write:
                print(
                    f"[{idx}/{len(keys)}] PLAN {key}  company={company} year={year} sub_risks={sub_risk_count}",
                    flush=True,
                )
                report["ok"].append({
                    "key": key,
                    "industry": industry,
                    "company_dir": company_dir,
                    "year": year,
                    "sub_risk_count": sub_risk_count,
                    "planned": True,
                })
                continue

            # Real write below.
            agent_report, err = ep.attach_agent_priority_report(
                result, company=company, year=year,
            )
            if not isinstance(agent_report, dict):
                raise RuntimeError(f"agent_priority failed: {err or 'unknown'}")

            # Track when we last rescored — useful for forensics across runs.
            result["agent_report_rescored_at"] = _now_iso()

            payload = json.dumps(result, indent=2, ensure_ascii=False, default=str).encode("utf-8")
            ep.put_bytes(key, payload, content_type="application/json")

            duration = time.time() - t0
            status = str(agent_report.get("scoring_status") or "ok")
            scored = 0
            try:
                pm = agent_report.get("priority_matrix") if isinstance(agent_report, dict) else {}
                if isinstance(pm, dict):
                    for bucket in ("high", "medium", "low"):
                        bucket_obj = pm.get(bucket) if isinstance(pm.get(bucket), dict) else {}
                        scored += int((bucket_obj or {}).get("count") or 0)
            except Exception:
                pass
            print(
                f"[{idx}/{len(keys)}] OK   {industry}/{company_dir}/{year}  "
                f"status={status} scored={scored}/{sub_risk_count}  {duration:.1f}s",
                flush=True,
            )
            report["ok"].append({
                "key": key,
                "industry": industry,
                "company_dir": company_dir,
                "year": year,
                "sub_risk_count": sub_risk_count,
                "scored_count": scored,
                "scoring_status": status,
                "duration_s": round(duration, 2),
            })

        except Exception as exc:
            duration = time.time() - t0
            tb = traceback.format_exc()
            print(
                f"[{idx}/{len(keys)}] FAIL {key}  reason={type(exc).__name__}:{exc}  {duration:.1f}s",
                flush=True,
            )
            print(tb, flush=True)
            report["failed"].append({
                "key": key,
                "reason": f"{type(exc).__name__}: {exc}",
                "duration_s": round(duration, 2),
            })

    report["ended_at"] = _now_iso()
    print(
        f"[done] ok={len(report['ok'])} skipped={len(report['skipped'])} failed={len(report['failed'])}",
        flush=True,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Re-score agent priority (RPI) for every risks JSON under "
            "10k_filings/ in S3 without re-extracting risks."
        ),
    )
    parser.add_argument("--dry-run", dest="write", action="store_false",
                        help="Default. Print the rescoring plan; no S3 writes, no Bedrock invocations.")
    parser.add_argument("--write", dest="write", action="store_true",
                        help="Actually invoke Bedrock and write updated JSON back to S3.")
    parser.add_argument("--industry", default="",
                        help="Only rescore one industry directory (e.g., Technology).")
    parser.add_argument("--ticker", default="",
                        help="Only rescore one ticker (e.g., AAPL).")
    parser.add_argument("--skip-already-scored", action="store_true",
                        help="Skip records whose agent_report already has scoring_status in {ok, partial}.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Stop after processing N records (0 = no limit).")
    parser.add_argument("--report", default=str(ROOT / "scripts" / "rescore_agent_priority.report.json"),
                        help="Where to write the run report JSON.")
    parser.set_defaults(write=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ep.s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    report = rescore(
        write=args.write,
        industry_filter=args.industry,
        ticker_filter=args.ticker,
        skip_already_scored=args.skip_already_scored,
        limit=args.limit,
    )

    try:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[report] wrote {args.report}", flush=True)
    except Exception as exc:
        print(f"[report] could not write {args.report}: {exc}", file=sys.stderr)

    return 0 if not report.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
