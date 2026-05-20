"""Bulk ingest 10-Q filings (Q1/Q2/Q3 only) for companies with 10-K records.

What it does
------------
1. Read existing records from backend index.
2. Build company seeds from companies that already have 10-K entries.
3. For each company, fetch recent 10-Q filings for the last N years
   (default: 3 years) and keep only Q1/Q2/Q3.
4. Run the same extraction + save pipeline used by runtime, and write
   each quarter as a separate 10-Q record with `filing_quarter`.

Notes
-----
* Dry-run by default. Use --write to persist.
* Q4 is intentionally skipped because annual risk context is represented by 10-K.
* SEC + extraction is done sequentially for stability and rate-limit safety.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402
from core import sec_edgar  # noqa: E402


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


def _norm_company(value: Any) -> str:
    return str(value or "").strip()


def _norm_ticker(value: Any) -> str:
    return str(value or "").strip().upper()


def _year_from_date(value: str) -> int:
    txt = str(value or "").strip()
    if len(txt) >= 4 and txt[:4].isdigit():
        return int(txt[:4])
    return 0


def _month_from_date(value: str) -> int:
    txt = str(value or "").strip()
    parts = txt.split("-")
    if len(parts) >= 2 and parts[1].isdigit():
        return int(parts[1])
    return 0


def _month_to_quarter(month: int) -> int:
    if month <= 0:
        return 0
    if month <= 3:
        return 1
    if month <= 6:
        return 2
    if month <= 9:
        return 3
    return 4


@dataclass
class CompanySeed:
    company: str
    ticker: str
    industry: str
    latest_10k_year: int
    records_count: int


def _build_company_seeds(records: List[dict]) -> List[CompanySeed]:
    by_key: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        if _norm_ft(rec.get("filing_type")) != "10-K":
            continue
        company = _norm_company(rec.get("company"))
        if not company:
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


def _select_10q_quarter_filings(submissions: dict, year: int, quarters: set[int]) -> Dict[int, dict]:
    recent = submissions.get("filings", {}).get("recent", {}) if isinstance(submissions, dict) else {}
    forms = recent.get("form", []) or []
    filing_dates = recent.get("filingDate", []) or []
    report_dates = recent.get("reportDate", []) or []
    accessions = recent.get("accessionNumber", []) or []
    primary_docs = recent.get("primaryDocument", []) or []
    total = min(len(forms), len(filing_dates), len(accessions), len(primary_docs))

    picked: Dict[int, dict] = {}
    for i in range(total):
        form = str(forms[i] or "").strip().upper()
        if form != "10-Q":
            continue
        filing_date = str(filing_dates[i] or "").strip()
        report_date = str(report_dates[i] or "").strip() if i < len(report_dates) else ""
        fy = _year_from_date(filing_date)
        ry = _year_from_date(report_date)
        # Prefer report-date year; fallback to filing-date year.
        matched_year = ry if ry > 0 else fy
        if matched_year != int(year):
            continue
        month = _month_from_date(report_date) or _month_from_date(filing_date)
        q = _month_to_quarter(month)
        if q not in quarters:
            continue
        item = {
            "filing_date": filing_date,
            "report_date": report_date,
            "report_year": ry,
            "accession_number": str(accessions[i] or "").strip(),
            "primary_document": str(primary_docs[i] or "").strip(),
            "filing_quarter": q,
        }
        if not item["accession_number"] or not item["primary_document"]:
            continue
        prev = picked.get(q)
        # Keep the latest filing date for the same quarter.
        if prev is None or str(item["filing_date"]) > str(prev.get("filing_date", "")):
            picked[q] = item
    return picked


def _ingest_one_filing(seed: CompanySeed, year: int, filing: dict) -> dict:
    q = _to_int(filing.get("filing_quarter"), 0)
    accession = str(filing.get("accession_number", "") or "").strip()
    primary_doc = str(filing.get("primary_document", "") or "").strip()
    if not accession or not primary_doc:
        return {"status": "fail", "year": year, "quarter": q, "error": "missing accession/document"}

    cik = sec_edgar.find_cik(seed.company, seed.ticker, "10-Q")
    if not cik:
        return {"status": "fail", "year": year, "quarter": q, "error": "Could not resolve CIK"}

    html_bytes, doc_name, err = sec_edgar.download_filing_html_by_cik(cik, accession, primary_doc)
    if not html_bytes:
        return {"status": "fail", "year": year, "quarter": q, "error": err or "Failed to download filing HTML"}

    result, extract_err = backend._manual_extract_result(
        file_bytes=html_bytes,
        file_name=f"{seed.company}_{year}_Q{q}.html",
        company=seed.company,
        industry=seed.industry,
        year=int(year),
        filing_type="10-Q",
        ticker=seed.ticker,
    )
    if not result:
        return {"status": "fail", "year": year, "quarter": q, "error": extract_err or "Extraction failed"}

    risks_for_agent = result.get("risks", []) if isinstance(result.get("risks"), list) else []
    if risks_for_agent:
        agent_report, agent_err = backend._generate_agent_priority_report(
            company=seed.company,
            year=int(year),
            risks=risks_for_agent,
        )
        if isinstance(agent_report, dict):
            result["agent_report"] = agent_report
        elif agent_err:
            result["agent_report_error"] = agent_err

    result["source"] = "sec_edgar_bulk_10q_q1q3"
    result["filing_quarter"] = q
    result["sec_meta"] = {
        "cik": cik,
        "ticker": seed.ticker,
        "year": int(year),
        "filing_date": str(filing.get("filing_date", "") or ""),
        "report_date": str(filing.get("report_date", "") or ""),
        "report_year": _to_int(filing.get("report_year"), 0),
        "accession_number": accession,
        "primary_document": primary_doc,
        "downloaded_document": doc_name,
        "auto_fetch": True,
        "filing_quarter": q,
        "filing_url": sec_edgar.build_filing_html_url(
            {
                "cik": cik,
                "accession_number": accession,
                "primary_document": primary_doc,
                "downloaded_document": doc_name,
            }
        ),
    }

    rec = backend._add_record(
        company=seed.company,
        industry=seed.industry,
        year=int(year),
        filing_type="10-Q",
        ticker=seed.ticker,
        file_bytes=html_bytes,
        file_ext="html",
        result_json=result,
        filing_quarter=q,
    )
    if seed.ticker:
        backend._upsert_company_ticker(seed.company, seed.ticker)
    if isinstance(result.get("agent_report"), dict):
        try:
            backend._append_agent_report_file(rec, result.get("agent_report"))
        except Exception:
            pass

    return {
        "status": "ok",
        "year": int(year),
        "quarter": q,
        "record_id": str(rec.get("record_id", "") or ""),
        "company": seed.company,
        "ticker": seed.ticker,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bulk ingest 10-Q Q1/Q2/Q3 for companies with existing 10-K records."
    )
    parser.add_argument("--write", action="store_true", help="Persist to S3/index (default is dry-run).")
    parser.add_argument("--years-back", type=int, default=3, help="Recent years per company (default: 3).")
    parser.add_argument(
        "--quarters",
        default="1,2,3",
        help="Quarter list to ingest (default: 1,2,3). Q4 usually covered by 10-K.",
    )
    parser.add_argument("--max-companies", type=int, default=0, help="Cap companies processed (0=all).")
    parser.add_argument("--sleep-sec", type=float, default=0.2, help="Sleep between company jobs (default: 0.2s).")
    parser.add_argument(
        "--report-path",
        default=str(ROOT / "scripts" / "bulk_ingest_10q_q1q3_from_10k_records.report.json"),
        help="Where to write report JSON.",
    )
    args = parser.parse_args()

    years_back = max(1, int(args.years_back))
    quarters = {q for q in [_to_int(x, 0) for x in str(args.quarters).split(",")] if q in {1, 2, 3, 4}}
    if not quarters:
        quarters = {1, 2, 3}
    if 4 in quarters:
        print("[warn] Q4 included in --quarters; you said Q4 is not needed. Keeping user choice.")

    records = backend._load_index()
    if not isinstance(records, list) or not records:
        print("[error] no records found in index.")
        return 1

    seeds = _build_company_seeds(records)
    if not seeds:
        print("[error] no 10-K company seeds found.")
        return 1
    if args.max_companies and int(args.max_companies) > 0:
        seeds = seeds[: int(args.max_companies)]

    planned_jobs = len(seeds) * years_back * len(quarters)
    eta_low_h = planned_jobs * 20 / 3600.0
    eta_high_h = planned_jobs * 55 / 3600.0
    print(
        f"[plan] companies={len(seeds)} years_back={years_back} quarters={sorted(quarters)} "
        f"jobs≈{planned_jobs} mode={'write' if args.write else 'dry-run'} "
        f"eta≈{eta_low_h:.1f}-{eta_high_h:.1f}h"
    )

    results: List[dict] = []
    ok_count = 0
    fail_count = 0
    skip_count = 0

    for idx, seed in enumerate(seeds, start=1):
        end_year = int(seed.latest_10k_year)
        start_year = max(1995, end_year - years_back + 1)
        company_result: dict = {
            "company": seed.company,
            "ticker": seed.ticker,
            "industry": seed.industry,
            "start_year": start_year,
            "end_year": end_year,
            "items": [],
        }
        print(f"[company {idx}/{len(seeds)}] {seed.company} ({seed.ticker or '-'}) {start_year}..{end_year}")

        cik = sec_edgar.find_cik(seed.company, seed.ticker, "10-Q")
        if not cik:
            company_result["items"].append({"status": "fail", "error": "Could not resolve CIK"})
            fail_count += 1
            results.append(company_result)
            continue

        try:
            submissions = sec_edgar._submissions_for_cik(cik)  # pylint: disable=protected-access
        except Exception as exc:
            company_result["items"].append({"status": "fail", "error": f"submissions error: {type(exc).__name__}: {exc}"})
            fail_count += 1
            results.append(company_result)
            continue

        for year in range(start_year, end_year + 1):
            picked = _select_10q_quarter_filings(submissions, year=year, quarters=quarters)
            for q in sorted(quarters):
                filing = picked.get(q)
                if filing is None:
                    item = {"status": "skip", "year": int(year), "quarter": int(q), "reason": "No 10-Q filing found for quarter"}
                    company_result["items"].append(item)
                    skip_count += 1
                    continue
                if not args.write:
                    item = {
                        "status": "plan",
                        "year": int(year),
                        "quarter": int(q),
                        "filing_date": filing.get("filing_date", ""),
                        "report_date": filing.get("report_date", ""),
                        "accession_number": filing.get("accession_number", ""),
                    }
                    company_result["items"].append(item)
                    continue
                out = _ingest_one_filing(seed, year=year, filing=filing)
                company_result["items"].append(out)
                if str(out.get("status")) == "ok":
                    ok_count += 1
                elif str(out.get("status")) == "skip":
                    skip_count += 1
                else:
                    fail_count += 1
            # Small pause between years to be nice to SEC APIs.
            time.sleep(max(0.0, float(args.sleep_sec)))

        results.append(company_result)

    report = {
        "ok": True,
        "generated_at": _now_iso(),
        "mode": "write" if args.write else "dry-run",
        "companies": len(seeds),
        "years_back": years_back,
        "quarters": sorted(quarters),
        "planned_jobs_estimate": planned_jobs,
        "saved_count": ok_count,
        "skipped_count": skip_count,
        "failed_count": fail_count,
        "results": results,
    }
    report_path = Path(str(args.report_path))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[report] {report_path}")
    print(f"[summary] saved={ok_count} skipped={skip_count} failed={fail_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

