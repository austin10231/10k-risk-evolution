"""Bulk ingest 10-Q filings for companies already present in records.

Default behavior
----------------
1. Read existing records via `agentcore_deploy.main._load_index()`.
2. Build a unique company list (prefer ticker as identity key).
3. For each company, ingest the most recent `N` years of 10-Q
   (default: 3 years) through the runtime's own ingestion path:
   `_auto_fetch_and_extract(... filing_type="10-Q")`.

Safety
------
* Dry-run by default (no writes).
* Use `--write` to persist records to S3/index.
* Optional caps for companies and total jobs.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _norm_ft(value: Any) -> str:
    txt = str(value or "").strip().upper()
    if txt in {"10Q", "10-Q"}:
        return "10-Q"
    return "10-K"


def _norm_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _norm_company(value: Any) -> str:
    return str(value or "").strip()


@dataclass
class CompanySeed:
    company: str
    ticker: str
    industry: str
    latest_10k_year: int
    records_count: int


def _build_company_seeds(records: List[dict], only_from_10k: bool = True) -> List[CompanySeed]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        company = _norm_company(rec.get("company"))
        if not company:
            continue
        ft = _norm_ft(rec.get("filing_type"))
        if only_from_10k and ft != "10-K":
            continue
        ticker = _norm_ticker(rec.get("ticker"))
        key = f"tk:{ticker}" if ticker else f"co:{company.lower()}"
        year = _to_int(rec.get("year"), 0)
        industry = str(rec.get("industry", "") or "").strip() or "Other"

        item = by_key.setdefault(
            key,
            {
                "company": company,
                "ticker": ticker,
                "industry": industry,
                "latest_10k_year": 0,
                "records_count": 0,
            },
        )
        if len(company) > len(str(item.get("company", ""))):
            item["company"] = company
        if ticker and not str(item.get("ticker", "")).strip():
            item["ticker"] = ticker
        if year > _to_int(item.get("latest_10k_year"), 0):
            item["latest_10k_year"] = year
        item["records_count"] = _to_int(item.get("records_count"), 0) + 1
        # Prefer non-Other industry if present.
        if str(item.get("industry", "")).strip() in {"", "Other"} and industry != "Other":
            item["industry"] = industry

    out: List[CompanySeed] = []
    for item in by_key.values():
        latest = _to_int(item.get("latest_10k_year"), 0)
        if latest <= 0:
            continue
        out.append(
            CompanySeed(
                company=str(item.get("company", "")).strip(),
                ticker=_norm_ticker(item.get("ticker")),
                industry=str(item.get("industry", "Other") or "Other").strip() or "Other",
                latest_10k_year=latest,
                records_count=_to_int(item.get("records_count"), 0),
            )
        )
    out.sort(key=lambda x: (x.company.lower(), -x.latest_10k_year))
    return out


def _run_for_company(seed: CompanySeed, years_back: int, write: bool) -> dict:
    end_year = int(seed.latest_10k_year)
    start_year = max(1995, end_year - max(1, years_back) + 1)
    plan = {
        "company": seed.company,
        "ticker": seed.ticker,
        "industry": seed.industry,
        "start_year": start_year,
        "end_year": end_year,
        "years_back": years_back,
    }
    if not write:
        return {"status": "plan", **plan}

    try:
        payload = backend._auto_fetch_and_extract(
            company=seed.company,
            ticker=seed.ticker,
            industry=seed.industry,
            filing_type="10-Q",
            start_year=start_year,
            end_year=end_year,
        )
    except Exception as exc:
        return {"status": "fail", **plan, "error": f"{type(exc).__name__}: {exc}"}

    if not isinstance(payload, dict):
        return {"status": "fail", **plan, "error": "invalid_response"}
    ok = bool(payload.get("ok"))
    return {
        "status": "ok" if ok else "fail",
        **plan,
        "ok": ok,
        "count": _to_int(payload.get("count"), 0),
        "successes": payload.get("successes", []) if isinstance(payload.get("successes"), list) else [],
        "skipped": payload.get("skipped", []) if isinstance(payload.get("skipped"), list) else [],
        "error": str(payload.get("error", "") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk ingest 10-Q for companies already present in records."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist data (default is dry-run).",
    )
    parser.add_argument(
        "--years-back",
        type=int,
        default=3,
        help="How many recent years per company to ingest (default: 3).",
    )
    parser.add_argument(
        "--max-companies",
        type=int,
        default=0,
        help="Cap companies processed (0 = all).",
    )
    parser.add_argument(
        "--limit-total-jobs",
        type=int,
        default=0,
        help="Cap total company jobs (0 = unlimited).",
    )
    parser.add_argument(
        "--include-non-10k",
        action="store_true",
        help="Also include companies that only appear in non-10-K records.",
    )
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "scripts" / "bulk_ingest_10q_from_records.report.json"),
        help="Where to write run report JSON.",
    )
    args = parser.parse_args()

    records = backend._load_index()
    if not isinstance(records, list) or not records:
        print("[error] no records found in index.")
        return 1

    seeds = _build_company_seeds(records, only_from_10k=not args.include_non_10k)
    if not seeds:
        print("[error] no eligible companies found.")
        return 1

    if args.max_companies and args.max_companies > 0:
        seeds = seeds[: int(args.max_companies)]

    print(
        f"[plan] companies={len(seeds)} years_back={max(1, int(args.years_back))} "
        f"mode={'write' if args.write else 'dry-run'}"
    )

    results: List[dict] = []
    processed = 0
    for seed in seeds:
        if args.limit_total_jobs and args.limit_total_jobs > 0 and processed >= int(args.limit_total_jobs):
            break
        item = _run_for_company(seed, years_back=max(1, int(args.years_back)), write=bool(args.write))
        results.append(item)
        processed += 1
        if item.get("status") == "plan":
            print(
                f"[plan] {seed.company} ({seed.ticker or '-'}) "
                f"{item.get('start_year')}..{item.get('end_year')}"
            )
        elif item.get("status") == "ok":
            print(
                f"[ok]   {seed.company} ({seed.ticker or '-'}) "
                f"saved={item.get('count', 0)} skipped={len(item.get('skipped', []) or [])}"
            )
        else:
            print(f"[fail] {seed.company} ({seed.ticker or '-'}) err={item.get('error')}")

    total_saved = sum(_to_int(r.get("count"), 0) for r in results if isinstance(r, dict))
    total_skipped = sum(len(r.get("skipped", []) or []) for r in results if isinstance(r, dict))
    total_failed = sum(1 for r in results if str(r.get("status")) == "fail")

    report = {
        "ok": True,
        "generated_at": _now_iso(),
        "mode": "write" if args.write else "dry-run",
        "years_back": max(1, int(args.years_back)),
        "companies_planned": len(seeds),
        "jobs_executed": len(results),
        "saved_count": total_saved,
        "skipped_count": total_skipped,
        "failed_jobs": total_failed,
        "results": results,
    }
    report_path = Path(str(args.report_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[report] {report_path}")
    print(
        f"[summary] jobs={len(results)} saved={total_saved} skipped={total_skipped} failed={total_failed}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

