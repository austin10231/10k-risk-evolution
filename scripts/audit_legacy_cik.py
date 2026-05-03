"""Audit every HTML under ``10k_filings/<industry>/<company_dir>/<year>_10K.html``
in S3 and compare its inline XBRL EntityCentralIndexKey against the expected
CIK from ``industry_mapping.COMPANIES`` (or, for tickers without an explicit
``cik`` field, the SEC ticker→CIK map via ``core.sec_edgar.find_cik``).

Output: a JSON report that lists matches, mismatches, and "no cik in HTML"
cases so the user can decide what to delete / quarantine / re-fetch.

This is the P0 audit step from EXTRACTION_FIX_PLAN.md. The original Apple_AAPL
data turned out to be Apple Hospitality REIT (APLE, CIK 0001418121); checking
filename tokens isn't enough — the inline XBRL CIK is authoritative.

Usage::

    # Default report path: scripts/cik_mismatch_report.json
    python scripts/audit_legacy_cik.py

    # Specify a different output path
    python scripts/audit_legacy_cik.py --report /tmp/cik_report.json

    # Limit to one industry / one ticker (useful for spot checks)
    python scripts/audit_legacy_cik.py --industry Technology --ticker AAPL
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import extraction_pipeline as ep  # noqa: E402
from scripts.industry_mapping import COMPANIES  # noqa: E402

NEW_FILINGS_PREFIX = "10k_filings/"
HTML_KEY_RE = re.compile(
    r"^10k_filings/(?P<industry>[^/]+)/(?P<dir>[^/]+)/(?P<year>\d{4})_10K\.html$"
)


def _list_filing_html_keys() -> list[str]:
    keys: list[str] = []
    paginator = ep.s3_client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=ep.s3_bucket(), Prefix=NEW_FILINGS_PREFIX):
        for obj in page.get("Contents", []) or []:
            k = str(obj.get("Key") or "")
            if HTML_KEY_RE.match(k):
                keys.append(k)
    return sorted(keys)


def _ticker_for_company_dir(company_dir: str) -> Optional[str]:
    for ticker, meta in COMPANIES.items():
        if str(meta.get("dir") or "").lower() == company_dir.lower():
            return ticker
    return None


def _expected_cik_for_ticker(ticker: str) -> str:
    meta = COMPANIES.get(ticker) or {}
    cik = str(meta.get("cik", "") or "").strip()
    if cik:
        return cik.zfill(10)
    # Fall back to SEC ticker map. Imported lazily so the script still loads
    # in environments without core.sec_edgar's internet dependency.
    try:
        from core import sec_edgar  # noqa: WPS433

        resolved = sec_edgar.find_cik(meta.get("sec_name") or meta.get("name") or "", ticker)
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip().zfill(10)
    except Exception as exc:  # pragma: no cover — diagnostic-only path
        print(f"[audit] could not resolve CIK for {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return ""


def audit(industry_filter: str = "", ticker_filter: str = "") -> dict:
    keys = _list_filing_html_keys()
    print(f"[audit] scanning {len(keys)} HTML objects under {NEW_FILINGS_PREFIX}", flush=True)

    report: dict = {
        "total": 0,
        "matched": [],
        "mismatched": [],
        "missing_cik_in_html": [],
        "missing_expected_cik": [],
        "skipped": [],
    }

    for key in keys:
        m = HTML_KEY_RE.match(key)
        if not m:
            continue
        industry = m.group("industry")
        company_dir = m.group("dir")
        year = int(m.group("year"))

        if industry_filter and industry != industry_filter:
            continue

        ticker = _ticker_for_company_dir(company_dir)
        if ticker_filter and (not ticker or ticker.upper() != ticker_filter.upper()):
            continue

        report["total"] += 1
        if not ticker:
            report["skipped"].append({
                "key": key,
                "reason": f"no_ticker_for_dir:{company_dir}",
            })
            continue

        expected = _expected_cik_for_ticker(ticker)
        if not expected:
            report["missing_expected_cik"].append({
                "key": key, "ticker": ticker, "industry": industry,
                "company_dir": company_dir, "year": year,
            })
            print(f"  · {key}  ticker={ticker}  expected_cik=UNKNOWN", flush=True)
            continue

        body = ep.get_bytes(key)
        if not body:
            report["skipped"].append({"key": key, "reason": "empty_body"})
            continue
        found = ep.extract_cik_from_html(body)
        record = {
            "key": key, "ticker": ticker, "industry": industry,
            "company_dir": company_dir, "year": year,
            "expected_cik": expected, "found_cik": found,
        }
        if not found:
            report["missing_cik_in_html"].append(record)
            print(f"  · {key}  expected={expected}  found=NONE", flush=True)
        elif found.lstrip("0") == expected.lstrip("0"):
            report["matched"].append(record)
            print(f"  ✓ {key}  cik={expected}", flush=True)
        else:
            report["mismatched"].append(record)
            print(
                f"  ✗ {key}  expected={expected}  found={found}  "
                f"(possible mis-uploaded filing)",
                flush=True,
            )

    print(
        f"[audit] done. matched={len(report['matched'])} "
        f"mismatched={len(report['mismatched'])} "
        f"missing_cik_in_html={len(report['missing_cik_in_html'])} "
        f"missing_expected_cik={len(report['missing_expected_cik'])} "
        f"skipped={len(report['skipped'])}",
        flush=True,
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit inline XBRL CIKs in 10k_filings/ against industry_mapping.",
    )
    parser.add_argument("--report", default=str(ROOT / "scripts" / "cik_mismatch_report.json"),
                        help="Where to write the JSON report (default: scripts/cik_mismatch_report.json).")
    parser.add_argument("--industry", default="",
                        help="Only audit one industry directory (e.g., Technology).")
    parser.add_argument("--ticker", default="",
                        help="Only audit one ticker (e.g., AAPL).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        ep.s3_bucket()
    except RuntimeError as exc:
        print(f"[fatal] {exc}", file=sys.stderr)
        return 2

    report = audit(industry_filter=args.industry, ticker_filter=args.ticker)
    try:
        Path(args.report).write_text(
            json.dumps(report, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        print(f"[report] wrote {args.report}", flush=True)
    except Exception as exc:
        print(f"[report] could not write {args.report}: {exc}", file=sys.stderr)

    # Exit 1 only when there is at least one true mismatch — that's the
    # actionable signal. Other categories are diagnostic.
    return 0 if not report.get("mismatched") else 1


if __name__ == "__main__":
    raise SystemExit(main())
