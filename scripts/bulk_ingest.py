"""Part 2 of S3_PLAN.md: bulk-ingest ~80 SEC 10-K filings into the new
`10k_filings/` layout. Reuses the same extraction + priority pipeline as
Part 1 so quality is consistent.

Pipeline per (ticker, year)
---------------------------
1. Skip if `index.json` already records this (company_dir, year) pair AND
   the destination keys exist on S3.
2. Download HTML via `core.sec_edgar.download_10k_html_for_company_year`.
3. Extract risks (overview + sub_risks + dashboard_category + RPI scores).
4. Persist HTML + JSON under `10k_filings/<industry>/<company_dir>/`.
5. Update `index.json` (atomic flush every 5 successful records).
6. Append a per-record log line and accumulate the run report.

Safety
------
* `--dry-run` (default) prints the plan without S3 writes or Bedrock cost.
* `--write` enables real writes; `--limit N` caps the number of new records.
* `--start-year` / `--end-year` (defaults 2021–2025) define the year range.
* `--max-failures-per-company N` short-circuits a stuck company.

Run from a host with `AWS_*`, `BEDROCK_*`, `S3_BUCKET` set in env.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402
from core import sec_edgar  # noqa: E402
from scripts import extraction_pipeline as ep  # noqa: E402
from scripts.industry_mapping import (  # noqa: E402
    COMPANIES,
    cik_for,
    last_year_for,
)
from scripts.bulk_ingest_targets import TARGETS  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _existing_pairs(index_doc: dict) -> set[tuple[str, int]]:
    out: set[tuple[str, int]] = set()
    industries = index_doc.get("industries", {}) if isinstance(index_doc, dict) else {}
    if not isinstance(industries, dict):
        return out
    for ind_dir, companies in industries.items():
        if not isinstance(companies, dict):
            continue
        for company_dir, block in companies.items():
            for f in (block or {}).get("filings", []) or []:
                try:
                    out.add((str(company_dir), int(f.get("year") or 0)))
                except Exception:
                    continue
    return out


def _expanded_year_range(ticker: str, start_year: int, end_year: int) -> list[int]:
    last_y = last_year_for(ticker)
    if last_y is not None:
        end_year = min(end_year, last_y)
    if start_year > end_year:
        return []
    return list(range(start_year, end_year + 1))


def _seed_cik_for_ticker(ticker: str) -> None:
    """If COMPANIES specifies a hardcoded CIK (BRK.B), seed sec_edgar's
    cache so `find_cik(...)` returns it without hitting the SEC ticker
    map (which doesn't carry BRK.B)."""
    cik = cik_for(ticker)
    if not cik:
        return
    try:
        cache = sec_edgar._TICKER_CIK_CACHE  # type: ignore[attr-defined]
        data = cache.get("data") if isinstance(cache, dict) else None
        if not isinstance(data, dict):
            data = {}
        normalized = sec_edgar._normalize_ticker(ticker)  # type: ignore[attr-defined]
        data[normalized] = {
            "cik": cik.zfill(10),
            "title": COMPANIES.get(ticker, {}).get("sec_name", ""),
            "ticker": normalized,
        }
        cache["data"] = data
        if not cache.get("ts"):
            cache["ts"] = time.time()
    except Exception:
        # Best-effort cache seed; if internals change we fall back to the
        # normal SEC ticker-map lookup, which usually works for most tickers.
        pass


# ──────────────────────────────────────────────────────────────────────
#  Per-ticker work
# ──────────────────────────────────────────────────────────────────────


def _ingest_one(
    ticker: str,
    year: int,
    *,
    write: bool,
    existing_pairs: set[tuple[str, int]],
    index_doc: dict,
) -> dict:
    meta = COMPANIES.get(ticker)
    if not meta:
        return {"status": "fail", "reason": f"unknown_ticker:{ticker}", "year": year}
    industry_dir = meta["industry"]
    company_dir = meta["dir"]
    company_name = meta["name"]
    sec_name = meta.get("sec_name") or meta["name"]
    cik = meta.get("cik", "") or ""

    h_key = ep.html_key_for(industry_dir, company_dir, year)
    j_key = ep.json_key_for(industry_dir, company_dir, year)

    if (company_dir, year) in existing_pairs and ep.head_exists(h_key) and ep.head_exists(j_key):
        return {"status": "skip", "reason": "already_in_index_and_s3",
                "industry": industry_dir, "company_dir": company_dir, "year": year}

    if not write:
        return {"status": "plan", "industry": industry_dir,
                "company_dir": company_dir, "year": year, "ticker": ticker,
                "html_key": h_key, "json_key": j_key}

    t0 = time.time()
    _seed_cik_for_ticker(ticker)
    try:
        html_bytes, sec_meta, sec_err = sec_edgar.download_10k_html_for_company_year(
            company_name=sec_name, year=year, ticker=ticker,
        )
    except Exception as exc:
        return {"status": "fail", "reason": f"SEC_DOWNLOAD_FAIL:{type(exc).__name__}:{exc}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    if not html_bytes:
        return {"status": "fail", "reason": f"SEC_DOWNLOAD_FAIL:{sec_err or 'no html'}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    try:
        result, err = ep.extract_risks_for_html(
            html_bytes,
            company_display_name=company_name,
            industry_label=industry_dir,
            year=year,
            filing_type="10-K",
        )
    except Exception as exc:
        return {"status": "fail", "reason": f"EXTRACT_EXCEPTION:{type(exc).__name__}:{exc}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    if not result:
        return {"status": "fail", "reason": f"EXTRACT_EMPTY_RISKS:{err or 'unknown'}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    risks = result.get("risks", []) if isinstance(result, dict) else []
    sub_risk_count = sum(
        len(b.get("sub_risks", []) or []) for b in risks if isinstance(b, dict)
    )
    if sub_risk_count < 5:
        return {"status": "fail",
                "reason": f"EXTRACT_LOW_COVERAGE:{sub_risk_count}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    _agent_report, agent_err = ep.attach_agent_priority_report(
        result, company=company_name, year=year,
    )
    if agent_err:
        # Not fatal — we'd rather store the filing without RPI than skip
        # the whole record. A later /api/dashboard/ensure-priority retry
        # can backfill the agent report.
        pass

    result["source"] = "s3_bulk_ingest_part2"
    result["sec_meta"] = {
        **(sec_meta if isinstance(sec_meta, dict) else {}),
        "ticker": ticker,
        "cik": cik or (sec_meta.get("cik") if isinstance(sec_meta, dict) else ""),
        "year": year,
        "auto_fetch": True,
    }

    try:
        ep.write_filing_to_new_layout(
            industry_dir=industry_dir,
            company_dir=company_dir,
            year=year,
            html_bytes=html_bytes,
            risks_json=result,
            skip_html_if_exists=True,
            skip_json_if_exists=False,
        )
    except Exception as exc:
        return {"status": "fail", "reason": f"S3_WRITE_FAIL:{type(exc).__name__}:{exc}",
                "year": year, "duration_s": round(time.time() - t0, 2)}

    ep.upsert_filing_into_index(
        index_doc,
        industry_dir=industry_dir,
        company_dir=company_dir,
        company_display_name=company_name,
        ticker=ticker,
        cik=cik or str((sec_meta or {}).get("cik") or ""),
        year=year,
        html_key=h_key,
        json_key=j_key,
        sub_risk_count=sub_risk_count,
        extracted_at=_now_iso(),
        filing_type="10-K",
    )
    existing_pairs.add((company_dir, year))

    return {
        "status": "ok",
        "industry": industry_dir, "company_dir": company_dir,
        "year": year, "ticker": ticker, "sub_risk_count": sub_risk_count,
        "duration_s": round(time.time() - t0, 2),
    }


# ──────────────────────────────────────────────────────────────────────
#  Driver
# ──────────────────────────────────────────────────────────────────────


def run(
    *,
    write: bool,
    start_year: int,
    end_year: int,
    max_failures_per_company: int,
    limit: int,
) -> dict:
    started = _now_iso()
    print(f"[plan] starting bulk_ingest write={write} years={start_year}-{end_year}", flush=True)

    index_doc = ep.load_new_index() if write else ep.empty_index_doc()
    if not isinstance(index_doc, dict) or not index_doc:
        index_doc = ep.empty_index_doc()
    existing = _existing_pairs(index_doc)
    print(f"[plan] {len(existing)} (company,year) pairs already present in index", flush=True)

    report: dict = {
        "started_at": started,
        "ended_at": None,
        "write": bool(write),
        "year_range": [start_year, end_year],
        "ok": [], "skipped": [], "failed": [],
        "by_company": {},
    }

    new_writes = 0
    flush_pending = 0
    completed_companies = 0

    for ticker, _planned_industry in TARGETS:
        meta = COMPANIES.get(ticker)
        if not meta:
            print(f"[skip] {ticker} — not in COMPANIES table", flush=True)
            continue

        years = _expanded_year_range(ticker, start_year, end_year)
        if not years:
            print(f"[skip] {ticker} — no years to fetch (delisted before start_year?)", flush=True)
            continue

        per_company = report["by_company"].setdefault(ticker, {"ok": [], "skipped": [], "failed": []})
        local_failures = 0

        for year in years:
            if limit and new_writes >= limit:
                print(f"[stop] hit --limit {limit}", flush=True)
                break

            outcome = _ingest_one(
                ticker, year,
                write=write,
                existing_pairs=existing,
                index_doc=index_doc,
            )
            status = outcome.get("status")
            if status == "ok":
                report["ok"].append(outcome)
                per_company["ok"].append(outcome)
                new_writes += 1
                flush_pending += 1
                print(f"[ok]   {ticker} {year}  {outcome.get('sub_risk_count')} risks  {outcome.get('duration_s')}s", flush=True)
                if write and flush_pending >= 5:
                    ep.save_new_index(index_doc)
                    flush_pending = 0
                    print(f"  · checkpoint flush of index.json", flush=True)
            elif status == "skip":
                report["skipped"].append(outcome)
                per_company["skipped"].append(outcome)
                print(f"[skip] {ticker} {year}  {outcome.get('reason')}", flush=True)
            elif status == "plan":
                report["ok"].append(outcome)
                per_company["ok"].append(outcome)
                print(f"[plan] {ticker} {year} -> {outcome.get('json_key')}", flush=True)
            else:  # fail
                report["failed"].append(outcome)
                per_company["failed"].append(outcome)
                local_failures += 1
                print(f"[fail] {ticker} {year}  {outcome.get('reason')}", flush=True)
                if local_failures >= max_failures_per_company:
                    print(f"[abort-company] {ticker} — {local_failures} failures, skipping remaining years", flush=True)
                    break

        if limit and new_writes >= limit:
            break
        completed_companies += 1

    if write and flush_pending:
        ep.save_new_index(index_doc)
        print(f"[done] final flush of index.json (after {completed_companies} companies)", flush=True)

    report["ended_at"] = _now_iso()
    print(
        f"[done] ok={len(report['ok'])} skipped={len(report['skipped'])} failed={len(report['failed'])}",
        flush=True,
    )

    if write:
        # Best-effort upload of the run report to S3 for ops history.
        try:
            stamp = started.replace(":", "-")
            key = f"{ep.NEW_FILINGS_PREFIX}/_ingest_reports/{stamp}.json"
            ep.put_bytes(
                key,
                json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
                content_type="application/json",
            )
            print(f"[report] uploaded {key}", flush=True)
        except Exception as exc:
            print(f"[report] failed to upload run report to S3: {exc}", flush=True)

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bulk-ingest SEC 10-K filings into the new 10k_filings layout (S3_PLAN.md Part 2).")
    parser.add_argument("--dry-run", dest="write", action="store_false",
                        help="Default. Print the plan; no SEC fetches, no Bedrock invokes, no S3 writes.")
    parser.add_argument("--write", dest="write", action="store_true",
                        help="Enable real SEC + Bedrock + S3 writes.")
    parser.add_argument("--start-year", type=int, default=2021)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--max-failures-per-company", type=int, default=2,
                        help="Stop a single company once it accumulates this many failed years.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Cap on the total number of NEW records to write this run (0 = no cap).")
    parser.add_argument("--report", default=str(ROOT / "scripts" / "bulk_ingest.report.json"),
                        help="Where to write the run report JSON locally.")
    parser.set_defaults(write=False)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ep.s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    report = run(
        write=args.write,
        start_year=args.start_year,
        end_year=args.end_year,
        max_failures_per_company=args.max_failures_per_company,
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
