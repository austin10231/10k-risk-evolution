"""
S3-based persistence layer with deduplication.

S3 layout:
  filing_records_index.json
  10k_html_datasets/{rid}.html
  10k_pdf_datasets/{rid}.pdf
  analysis_results/{rid}.json
  table_results/{company}_{year}_{ftype}_{id}.json
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


def _delete_by_prefix(prefix):
    """Delete ALL S3 objects whose key starts with prefix."""
    try:
        s3 = _get_s3()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
    except Exception:
        pass


# ── Index ─────────────────────────────────────────────────────────────────────

def load_index():
    data = _s3_read(INDEX_KEY)
    if data is None:
        return []
    return json.loads(data.decode("utf-8"))


def _save_index(index):
    _s3_write(INDEX_KEY, json.dumps(index, indent=2, default=str).encode("utf-8"))


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_record(company, industry, year, filing_type, file_bytes, file_ext, result_json):
    year = int(year)

    # ── Dedup: remove ALL existing records with same company+year+filing_type
    index = load_index()
    dupes = [r for r in index
             if r["company"] == company and r["year"] == year and r["filing_type"] == filing_type]
    for d in dupes:
        oid = d["record_id"]
        oext = d.get("file_ext", "html")
        opfx = PDF_PREFIX if oext == "pdf" else HTML_PREFIX
        osuf = "pdf" if oext == "pdf" else "html"
        _s3_delete(f"{opfx}/{oid}.{osuf}")
        _s3_delete(f"{RESULTS_PREFIX}/{oid}.json")

    index = [r for r in index
             if not (r["company"] == company and r["year"] == year and r["filing_type"] == filing_type)]

    # ── Save new ──────────────────────────────────────────────────────
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sid = uuid.uuid4().hex[:4]
    rid = f"{safe}_{year}_{filing_type}_{sid}"
    pfx = PDF_PREFIX if file_ext == "pdf" else HTML_PREFIX
    ext = "pdf" if file_ext == "pdf" else "html"

    _s3_write(f"{pfx}/{rid}.{ext}", file_bytes)
    _s3_write(
        f"{RESULTS_PREFIX}/{rid}.json",
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    index.append({
        "record_id": rid, "company": company, "industry": industry,
        "year": year, "filing_type": filing_type, "file_ext": file_ext,
        "created_at": datetime.now().isoformat(),
    })
    _save_index(index)
    return rid


def get_result(record_id):
    data = _s3_read(f"{RESULTS_PREFIX}/{record_id}.json")
    return json.loads(data.decode("utf-8")) if data else None


def get_original_file(record_id, file_ext="html"):
    pfx = PDF_PREFIX if file_ext == "pdf" else HTML_PREFIX
    ext = "pdf" if file_ext == "pdf" else "html"
    return _s3_read(f"{pfx}/{record_id}.{ext}")


def delete_record(record_id):
    index = load_index()
    rec = next((r for r in index if r["record_id"] == record_id), None)
    fe = rec.get("file_ext", "html") if rec else "html"
    index = [r for r in index if r["record_id"] != record_id]
    _save_index(index)
    pfx = PDF_PREFIX if fe == "pdf" else HTML_PREFIX
    ext = "pdf" if fe == "pdf" else "html"
    _s3_delete(f"{pfx}/{record_id}.{ext}")
    _s3_delete(f"{RESULTS_PREFIX}/{record_id}.json")


def save_table_result(company, year, filing_type, table_json):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sf = re.sub(r"[^\w\-]", "", filing_type)

    # Dedup: delete ALL old table results for same company+year+ftype
    _delete_by_prefix(f"{TABLES_PREFIX}/{safe}_{year}_{sf}_")

    sid = uuid.uuid4().hex[:4]
    key = f"{TABLES_PREFIX}/{safe}_{year}_{sf}_{sid}.json"
    _s3_write(key, json.dumps(table_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
    return key


def save_compare_result(company, filing_type, latest_year, prior_years, compare_json):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    ps = "&".join(str(y) for y in sorted(prior_years, reverse=True))
    sf = re.sub(r"[^\w\-]", "", filing_type)

    # Dedup: delete ALL old compare results for same company+years+ftype
    _delete_by_prefix(f"{COMPARES_PREFIX}/{safe}_{latest_year}_vs_{ps}_{sf}_")

    sid = uuid.uuid4().hex[:4]
    key = f"{COMPARES_PREFIX}/{safe}_{latest_year}_vs_{ps}_{sf}_{sid}.json"
    _s3_write(key, json.dumps(compare_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
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
