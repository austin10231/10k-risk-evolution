"""
S3-based persistence layer.

S3 layout (v6):
  filing_records_index.json
  10k_html_datasets/{rid}.html
  10k_pdf_datasets/{rid}.pdf
  analysis_results/{rid}.json
  table_results/{company}_{year}_{ftype}_{id}.json     ★ NEW
  compare_reports/{...}.json
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

INDEX_KEY = "filing_records_index.json"
HTML_PREFIX = "10k_html_datasets"
PDF_PREFIX = "10k_pdf_datasets"
RESULTS_PREFIX = "analysis_results"
TABLES_PREFIX = "table_results"
COMPARES_PREFIX = "compare_reports"


def _s3_read(key):
    try:
        obj = _get_s3().get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read()
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return None
        raise


def _s3_write(key, data):
    _get_s3().put_object(Bucket=BUCKET, Key=key, Body=data)


def _s3_delete(key):
    try:
        _get_s3().delete_object(Bucket=BUCKET, Key=key)
    except Exception:
        pass


def load_index():
    data = _s3_read(INDEX_KEY)
    if data is None:
        return []
    return json.loads(data.decode("utf-8"))


def _save_index(index):
    _s3_write(INDEX_KEY, json.dumps(index, indent=2, default=str).encode("utf-8"))


def add_record(company, industry, year, filing_type, file_bytes, file_ext, result_json):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sid = uuid.uuid4().hex[:4]
    rid = f"{safe}_{year}_{filing_type}_{sid}"
    prefix = PDF_PREFIX if file_ext == "pdf" else HTML_PREFIX
    ext = "pdf" if file_ext == "pdf" else "html"
    _s3_write(f"{prefix}/{rid}.{ext}", file_bytes)
    _s3_write(
        f"{RESULTS_PREFIX}/{rid}.json",
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    index = load_index()
    index.append({
        "record_id": rid, "company": company, "industry": industry,
        "year": int(year), "filing_type": filing_type, "file_ext": file_ext,
        "created_at": datetime.now().isoformat(),
    })
    _save_index(index)
    return rid


def get_result(record_id):
    data = _s3_read(f"{RESULTS_PREFIX}/{record_id}.json")
    return json.loads(data.decode("utf-8")) if data else None


def get_original_file(record_id, file_ext="html"):
    prefix = PDF_PREFIX if file_ext == "pdf" else HTML_PREFIX
    ext = "pdf" if file_ext == "pdf" else "html"
    return _s3_read(f"{prefix}/{record_id}.{ext}")


def delete_record(record_id):
    index = load_index()
    rec = next((r for r in index if r["record_id"] == record_id), None)
    fe = rec.get("file_ext", "html") if rec else "html"
    index = [r for r in index if r["record_id"] != record_id]
    _save_index(index)
    prefix = PDF_PREFIX if fe == "pdf" else HTML_PREFIX
    ext = "pdf" if fe == "pdf" else "html"
    _s3_delete(f"{prefix}/{record_id}.{ext}")
    _s3_delete(f"{RESULTS_PREFIX}/{record_id}.json")


def save_compare_result(company, filing_type, latest_year, prior_years, compare_json):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    ps = "&".join(str(y) for y in sorted(prior_years, reverse=True))
    sid = uuid.uuid4().hex[:4]
    sf = re.sub(r"[^\w\-]", "", filing_type)
    key = f"{COMPARES_PREFIX}/{safe}_{latest_year}_vs_{ps}_{sf}_{sid}.json"
    _s3_write(key, json.dumps(compare_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
    return key


def save_table_result(company, year, filing_type, table_json):
    """Save extracted table data to S3. Returns the S3 key."""
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sid = uuid.uuid4().hex[:4]
    sf = re.sub(r"[^\w\-]", "", filing_type)
    key = f"{TABLES_PREFIX}/{safe}_{year}_{sf}_{sid}.json"
    _s3_write(key, json.dumps(table_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
    return key


def filter_records(industry=None, company=None, year=None, filing_type=None, fmt=None):
    recs = load_index()
    if industry and industry != "All":
        recs = [r for r in recs if r["industry"] == industry]
    if company and company != "All":
        recs = [r for r in recs if r["company"] == company]
    if year and year != "All":
        recs = [r for r in recs if str(r["year"]) == str(year)]
    if filing_type and filing_type != "All":
        recs = [r for r in recs if r["filing_type"] == filing_type]
    if fmt and fmt != "All":
        recs = [r for r in recs if r.get("file_ext", "html").upper() == fmt]
    return recs
