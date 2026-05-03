"""Shared S3 + extraction helpers used by Part 1 (migrate_s3_layout) and
Part 2 (bulk_ingest) of S3_PLAN.md.

We deliberately reuse the production code paths from `agentcore_deploy.main`
so any improvement that lands in the API runtime (priority scoring,
dashboard_category annotation, etc.) is automatically picked up by the
batch jobs — guaranteeing "新旧公司 JSON 格式与质量完全一致" as the plan
demands.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

import boto3

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentcore_deploy import main as backend  # noqa: E402  — repo-root injected above


NEW_FILINGS_PREFIX = "10k_filings"
NEW_INDEX_KEY = f"{NEW_FILINGS_PREFIX}/index.json"


def s3_bucket() -> str:
    bucket = os.getenv("S3_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("S3_BUCKET env var is required.")
    return bucket


def s3_client():
    """Single boto3 client for the whole script run, reusing the runtime's
    cached client when running in-process so credentials / region match."""
    return backend._s3_client()


# ── CIK verification (P0 of EXTRACTION_FIX_PLAN.md) ───────────────────────────
# Apple_AAPL/2025 turned out to be Apple Hospitality REIT (APLE, CIK 0001418121)
# misnamed at upload time. The HTML's inline XBRL header carries the true CIK
# regardless of what the filename says, so we extract and compare it before
# trusting the layout.

_CIK_TAG_RES = (
    re.compile(rb"<(?:ix:nonNumeric|dei:EntityCentralIndexKey)[^>]*?>\s*([0-9]{1,10})\s*<", re.IGNORECASE),
    re.compile(rb"name=[\"']dei:EntityCentralIndexKey[\"'][^>]*>\s*([0-9]{1,10})\s*<", re.IGNORECASE),
    re.compile(rb"EntityCentralIndexKey[^0-9<]{0,40}([0-9]{6,10})", re.IGNORECASE),
    re.compile(rb"CIK[^A-Za-z0-9]{0,10}0{0,4}([0-9]{6,10})", re.IGNORECASE),
)


def extract_cik_from_html(html_bytes: bytes) -> str:
    """Read the first ~64 KB of an SEC 10-K HTML and return the inline XBRL
    EntityCentralIndexKey, zero-padded to 10 digits. Returns "" if no CIK
    can be located."""
    head = (html_bytes or b"")[:65536]
    if not head:
        return ""
    for pat in _CIK_TAG_RES:
        m = pat.search(head)
        if m:
            cik = m.group(1).decode("ascii", errors="ignore").lstrip("0")
            if cik.isdigit() and 4 <= len(cik) <= 10:
                return cik.zfill(10)
    return ""


def verify_cik(html_bytes: bytes, expected_cik: str) -> tuple[bool, str]:
    """Compare the HTML's inline XBRL CIK to the expected CIK.

    Returns (ok, found_cik). `ok` is True when:
      - expected_cik is empty (no expectation, can't verify), or
      - found CIK matches expected (compared as zero-padded 10-digit strings)
      - no CIK could be extracted from HTML (skip rather than fail-noisily on
        non-XBRL legacy filings; caller decides whether to treat as error)
    """
    expected = str(expected_cik or "").strip().lstrip("0")
    if not expected:
        return True, ""
    found = extract_cik_from_html(html_bytes)
    if not found:
        return True, ""
    return found.lstrip("0") == expected.lstrip("0"), found


def html_key_for(industry_dir: str, company_dir: str, year: int) -> str:
    return f"{NEW_FILINGS_PREFIX}/{industry_dir}/{company_dir}/{int(year)}_10K.html"


def json_key_for(industry_dir: str, company_dir: str, year: int) -> str:
    return f"{NEW_FILINGS_PREFIX}/{industry_dir}/{company_dir}/{int(year)}_10K_risks.json"


def head_exists(key: str) -> bool:
    try:
        s3_client().head_object(Bucket=s3_bucket(), Key=key)
        return True
    except Exception:
        return False


def put_bytes(key: str, data: bytes, content_type: Optional[str] = None) -> None:
    kwargs = {"Bucket": s3_bucket(), "Key": key, "Body": data}
    if content_type:
        kwargs["ContentType"] = content_type
    s3_client().put_object(**kwargs)


def get_bytes(key: str) -> Optional[bytes]:
    try:
        obj = s3_client().get_object(Bucket=s3_bucket(), Key=key)
        return obj["Body"].read()
    except Exception:
        return None


def extract_risks_for_html(
    html_bytes: bytes,
    company_display_name: str,
    industry_label: str,
    *,
    year: int = 0,
    filing_type: str = "10-K",
    expected_cik: str = "",
) -> tuple[Optional[dict], str]:
    """Run the same Bedrock-backed extraction pipeline that powers
    `/api/upload/manual`. Returns (result_dict, error_str).

    P0: when `expected_cik` is provided, refuse to extract if the HTML's
    inline XBRL CIK disagrees — that's the Apple_AAPL/2025-vs-APLE failure
    mode and we never want to silently extract REIT data and label it as
    Apple Inc. Pass empty string to skip the check.

    On success the result schema matches what `_manual_extract_result`
    persists under `risk_analysis_results/<rid>.json`:
        {"company_overview": {...}, "risks": [{"category", "sub_risks":[{"title","dashboard_category","original_category",...}]}]}
    """
    if expected_cik:
        ok, found = verify_cik(html_bytes, expected_cik)
        if not ok:
            return None, (
                f"cik_mismatch: html_cik={found or 'unknown'} "
                f"expected_cik={str(expected_cik or '').strip()}"
            )
    fname = f"{company_display_name}_{int(year or 0)}.html"
    return backend._manual_extract_result(
        file_bytes=html_bytes,
        file_name=fname,
        company=company_display_name,
        industry=industry_label,
        year=int(year or 0),
        filing_type=str(filing_type or "10-K"),
    )


def attach_agent_priority_report(result: dict, *, company: str, year: int) -> tuple[Optional[dict], str]:
    """Run the same priority/agent pipeline used by `_auto_fetch_and_extract`
    so dashboard RPI is computable for migrated/bulk-ingested filings.

    On success mutates `result["agent_report"]` in place and returns
    (agent_report, ""). On failure returns (None, err_msg) and stores
    `result["agent_report_error"]` for forensics.
    """
    if not isinstance(result, dict):
        return None, "result must be a dict"
    risks = result.get("risks", []) if isinstance(result.get("risks"), list) else []
    if not risks:
        return None, "no risks to score"

    report, err = backend._generate_agent_priority_report(
        company=str(company or "").strip(),
        year=int(year or 0),
        risks=risks,
    )
    if isinstance(report, dict):
        result["agent_report"] = report
        result.pop("agent_report_error", None)
        return report, ""
    if err:
        result["agent_report_error"] = err
    return None, err or "agent priority scoring failed"


def write_filing_to_new_layout(
    *,
    industry_dir: str,
    company_dir: str,
    year: int,
    html_bytes: bytes,
    risks_json: dict,
    skip_html_if_exists: bool = True,
    skip_json_if_exists: bool = False,
) -> tuple[str, str]:
    """Upload (html, json) pair under 10k_filings/<industry>/<company>/<year>_10K.*.

    Returns (html_key, json_key). If `skip_html_if_exists` and the HTML key
    is already in S3 we don't reupload (saves 5–12 MB per record on rerun).
    The JSON is always overwritten by default — re-running extraction
    intentionally overwrites stale JSON.
    """
    h_key = html_key_for(industry_dir, company_dir, year)
    j_key = json_key_for(industry_dir, company_dir, year)

    if not (skip_html_if_exists and head_exists(h_key)):
        put_bytes(h_key, html_bytes, content_type="text/html; charset=utf-8")

    if not (skip_json_if_exists and head_exists(j_key)):
        payload = json.dumps(risks_json, indent=2, ensure_ascii=False, default=str).encode("utf-8")
        put_bytes(j_key, payload, content_type="application/json")

    return h_key, j_key


def read_filing_from_new_layout(
    industry_dir: str, company_dir: str, year: int,
) -> tuple[Optional[bytes], Optional[dict]]:
    """Read back (html, json) from the new layout. Either may be None."""
    html = get_bytes(html_key_for(industry_dir, company_dir, year))
    raw_json = get_bytes(json_key_for(industry_dir, company_dir, year))
    parsed: Optional[dict] = None
    if raw_json:
        try:
            obj = json.loads(raw_json.decode("utf-8", errors="ignore"))
            if isinstance(obj, dict):
                parsed = obj
        except Exception:
            parsed = None
    return html, parsed


def load_new_index() -> dict:
    """Load the new layout's index.json. Returns {} if absent."""
    raw = get_bytes(NEW_INDEX_KEY)
    if not raw:
        return {}
    try:
        obj = json.loads(raw.decode("utf-8", errors="ignore"))
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {}


def save_new_index(index_doc: dict) -> None:
    """Atomic put of the index.json (file is small; no need to chunk)."""
    payload = json.dumps(index_doc, indent=2, ensure_ascii=False, default=str).encode("utf-8")
    put_bytes(NEW_INDEX_KEY, payload, content_type="application/json")


def empty_index_doc() -> dict:
    return {
        "version": 1,
        "schema": {
            "html_key": f"{NEW_FILINGS_PREFIX}/<industry>/<company_dir>/<year>_10K.html",
            "json_key": f"{NEW_FILINGS_PREFIX}/<industry>/<company_dir>/<year>_10K_risks.json",
        },
        "industries": {},
    }


def upsert_filing_into_index(
    index_doc: dict,
    *,
    industry_dir: str,
    company_dir: str,
    company_display_name: str,
    ticker: str,
    cik: str,
    year: int,
    html_key: str,
    json_key: str,
    sub_risk_count: int,
    extracted_at: str,
    filing_type: str = "10-K",
) -> None:
    """Add or replace one filing entry in `index_doc.industries[...]`."""
    industries = index_doc.setdefault("industries", {})
    industry_block = industries.setdefault(industry_dir, {})

    company_block = industry_block.setdefault(company_dir, {
        "company": company_display_name,
        "ticker": ticker,
        "industry": industry_dir,
        "cik": cik,
        "filings": [],
    })
    # Keep the first-seen identity but always honor a more specific value.
    if company_display_name and not company_block.get("company"):
        company_block["company"] = company_display_name
    if ticker and not company_block.get("ticker"):
        company_block["ticker"] = ticker
    if cik and not company_block.get("cik"):
        company_block["cik"] = cik

    filings: list = company_block.setdefault("filings", [])
    filings[:] = [f for f in filings if int(f.get("year") or 0) != int(year)]
    filings.append({
        "year": int(year),
        "filing_type": str(filing_type or "10-K"),
        "html_key": html_key,
        "json_key": json_key,
        "sub_risk_count": int(sub_risk_count or 0),
        "extracted_at": str(extracted_at or ""),
    })
    filings.sort(key=lambda r: int(r.get("year") or 0))
