"""Run Upload Phase 7 regression against recent SEC 10-K HTML filings.

This script intentionally uses the deterministic extraction path only. Bedrock
schema extraction requires AWS credentials and can add cost, so LLM/category
quality should be evaluated separately with an approved sample set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.extractor import extract_item1a_risks, locate_item1_overview, locate_item1a
from core.sec_edgar import (
    _sec_get_json,
    _submissions_for_cik,
    download_filing_html_by_cik,
    find_cik,
)


CASES = [
    {"company": "Apple Inc", "ticker": "AAPL"},
    {"company": "Microsoft Corporation", "ticker": "MSFT"},
    {"company": "NVIDIA Corporation", "ticker": "NVDA"},
    {"company": "Amazon.com Inc", "ticker": "AMZN"},
    {"company": "Alphabet Inc", "ticker": "GOOGL"},
    {"company": "Meta Platforms Inc", "ticker": "META"},
    {"company": "Tesla Inc", "ticker": "TSLA"},
    {"company": "JPMorgan Chase & Co.", "ticker": "JPM"},
    {"company": "Pfizer Inc", "ticker": "PFE"},
    {"company": "Lockheed Martin Corporation", "ticker": "LMT"},
]


def _rows_from_recent_payload(recent: dict) -> list[dict]:
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    total = min(len(forms), len(filing_dates), len(report_dates), len(accessions), len(primary_docs))
    out = []
    for idx in range(total):
        if str(forms[idx]).upper() != "10-K":
            continue
        report_date = str(report_dates[idx] or "")
        out.append(
            {
                "filing_date": str(filing_dates[idx] or ""),
                "report_date": report_date,
                "accession_number": str(accessions[idx] or ""),
                "primary_document": str(primary_docs[idx] or ""),
            }
        )
    return out


def _recent_10k_filings(cik: str, limit: int = 2) -> list[dict]:
    submissions = _submissions_for_cik(cik)
    filings = submissions.get("filings", {}) if isinstance(submissions, dict) else {}
    candidates = _rows_from_recent_payload(filings.get("recent", {}))

    for archive in filings.get("files", []) or []:
        if len(candidates) >= max(limit + 5, 10):
            break
        name = str((archive or {}).get("name", "") or "").strip()
        if not name:
            continue
        try:
            payload = _sec_get_json(f"https://data.sec.gov/submissions/{name}")
        except Exception:
            continue
        candidates.extend(_rows_from_recent_payload(payload))

    candidates.sort(key=lambda row: (row.get("report_date", ""), row.get("filing_date", "")), reverse=True)
    out = []
    seen_reports = set()
    for row in candidates:
        report_date = row.get("report_date", "")
        key = report_date or row.get("accession_number", "")
        if key in seen_reports:
            continue
        seen_reports.add(key)
        out.append(row)
        if len(out) >= limit:
            break
    return out


def _risk_count(blocks: list[dict]) -> int:
    return sum(len(block.get("sub_risks", []) or []) for block in blocks if isinstance(block, dict))


def run_regression() -> dict:
    rows = []
    for case in CASES:
        company = case["company"]
        ticker = case["ticker"]
        cik = find_cik(company, ticker)
        filings = _recent_10k_filings(cik, limit=2) if cik else []
        if not filings:
            rows.append(
                {
                    "company": company,
                    "ticker": ticker,
                    "cik": cik,
                    "ok": False,
                    "error": "No recent 10-K filings found.",
                }
            )
            continue

        for filing in filings:
            row = {
                "company": company,
                "ticker": ticker,
                "cik": cik,
                "filing_date": filing.get("filing_date", ""),
                "report_date": filing.get("report_date", ""),
                "primary_document": filing.get("primary_document", ""),
                "downloaded_document": "",
                "item1_chars": 0,
                "item1a_chars": 0,
                "risk_blocks": 0,
                "risk_items": 0,
                "ok": False,
                "error": "",
            }
            try:
                html, doc_name, err = download_filing_html_by_cik(
                    cik_10=cik,
                    accession_number=filing.get("accession_number", ""),
                    primary_document=filing.get("primary_document", ""),
                )
                row["downloaded_document"] = doc_name
                if not html:
                    row["error"] = err or "HTML download failed."
                    rows.append(row)
                    continue

                item1 = locate_item1_overview(html)
                item1a = locate_item1a(html)
                risks = extract_item1a_risks(html)
                row["item1_chars"] = len(item1 or "")
                row["item1a_chars"] = len(item1a or "")
                row["risk_blocks"] = len(risks or [])
                row["risk_items"] = _risk_count(risks or [])
                row["ok"] = bool(row["item1a_chars"] >= 500 and row["risk_items"] >= 8)
                if not row["ok"]:
                    row["error"] = "Item 1A located too short or fewer than 8 risk items."
            except Exception as exc:
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)

    total = len(rows)
    located = sum(1 for row in rows if int(row.get("item1a_chars", 0) or 0) >= 500)
    passed = sum(1 for row in rows if row.get("ok"))
    risk_counts = [int(row.get("risk_items", 0) or 0) for row in rows if row.get("ok")]
    summary = {
        "case_count": len(CASES),
        "filing_count": total,
        "item1a_located": located,
        "passed_minimum_risk_threshold": passed,
        "item1a_hit_rate": round(located / total, 4) if total else 0,
        "pass_rate": round(passed / total, 4) if total else 0,
        "average_risk_items_when_passed": round(sum(risk_counts) / len(risk_counts), 2) if risk_counts else 0,
        "classification_accuracy": None,
        "classification_accuracy_note": "Not measured: no AWS Bedrock credentials in local environment and no manual label set.",
    }
    return {"summary": summary, "rows": rows}


if __name__ == "__main__":
    print(json.dumps(run_regression(), ensure_ascii=False, indent=2))
