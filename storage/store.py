"""
S3-based persistence layer.

S3 layout (v5):
  filing_records_index.json
  10k_html_datasets/{rid}.html
  10k_pdf_datasets/{rid}.pdf
  analysis_results/{rid}.json
  compare_reports/{company}_{latest}_vs_{priors}_{ftype}_{id}.json
"""

import json
import re
import uuid
import streamlit as st
import boto3
from datetime import datetime


def _get_s3():
    return boto3.client(
        "s3",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )


BUCKET = st.secrets["S3_BUCKET"]

# ── S3 path constants ─────────────────────────────────────────────────────────
INDEX_KEY = "filing_records_index.json"
HTML_PREFIX = "10k_html_datasets"
PDF_PREFIX = "10k_pdf_datasets"
RESULTS_PREFIX = "analysis_results"
COMPARES_PREFIX = "compare_reports"


def _s3_read(key: str) -> bytes | None:
    try:
        obj = _get_s3().get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read()
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return None
        raise


def _s3_write(key: str, data: bytes):
    _get_s3().put_object(Bucket=BUCKET, Key=key, Body=data)


def _s3_delete(key: str):
    try:
        _get_s3().delete_object(Bucket=BUCKET, Key=key)
    except Exception:
        pass


# ── Index ─────────────────────────────────────────────────────────────────────

def load_index() -> list[dict]:
    data = _s3_read(INDEX_KEY)
    if data is None:
        return []
    return json.loads(data.decode("utf-8"))


def _save_index(index: list[dict]):
    _s3_write(
        INDEX_KEY,
        json.dumps(index, indent=2, default=str).encode("utf-8"),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_record(
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    file_bytes: bytes,
    file_ext: str,
    result_json: dict,
) -> str:
    safe_company = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    short_id = uuid.uuid4().hex[:4]
    rid = f"{safe_company}_{year}_{filing_type}_{short_id}"

    # Save original file to appropriate folder
    if file_ext == "pdf":
        _s3_write(f"{PDF_PREFIX}/{rid}.pdf", file_bytes)
    else:
        _s3_write(f"{HTML_PREFIX}/{rid}.html", file_bytes)

    # Save analysis result
    _s3_write(
        f"{RESULTS_PREFIX}/{rid}.json",
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    index = load_index()
    index.append({
        "record_id": rid,
        "company": company,
        "industry": industry,
        "year": int(year),
        "filing_type": filing_type,
        "file_ext": file_ext,
        "created_at": datetime.now().isoformat(),
    })
    _save_index(index)
    return rid


def get_result(record_id: str) -> dict | None:
    data = _s3_read(f"{RESULTS_PREFIX}/{record_id}.json")
    if data is None:
        return None
    return json.loads(data.decode("utf-8"))


def get_original_file(record_id: str, file_ext: str = "html") -> bytes | None:
    if file_ext == "pdf":
        return _s3_read(f"{PDF_PREFIX}/{record_id}.pdf")
    return _s3_read(f"{HTML_PREFIX}/{record_id}.html")


def delete_record(record_id: str):
    index = load_index()
    # Find file_ext before removing
    rec = next((r for r in index if r["record_id"] == record_id), None)
    file_ext = rec.get("file_ext", "html") if rec else "html"

    index = [r for r in index if r["record_id"] != record_id]
    _save_index(index)

    if file_ext == "pdf":
        _s3_delete(f"{PDF_PREFIX}/{record_id}.pdf")
    else:
        _s3_delete(f"{HTML_PREFIX}/{record_id}.html")
    _s3_delete(f"{RESULTS_PREFIX}/{record_id}.json")


def save_compare_result(
    company: str,
    filing_type: str,
    latest_year: int,
    prior_years: list[int],
    compare_json: dict,
) -> str:
    safe_company = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    prior_str = "&".join(str(y) for y in sorted(prior_years, reverse=True))
    short_id = uuid.uuid4().hex[:4]
    safe_ftype = re.sub(r"[^\w\-]", "", filing_type)
    key = f"{COMPARES_PREFIX}/{safe_company}_{latest_year}_vs_{prior_str}_{safe_ftype}_{short_id}.json"

    _s3_write(
        key,
        json.dumps(compare_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    return key


def filter_records(
    industry=None, company=None, year=None, filing_type=None,
) -> list[dict]:
    recs = load_index()
    if industry and industry != "All":
        recs = [r for r in recs if r["industry"] == industry]
    if company and company != "All":
        recs = [r for r in recs if r["company"] == company]
    if year and year != "All":
        recs = [r for r in recs if str(r["year"]) == str(year)]
    if filing_type and filing_type != "All":
        recs = [r for r in recs if r["filing_type"] == filing_type]
    return recs
