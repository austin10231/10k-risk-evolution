"""
S3-based persistence layer.

Layout in S3 bucket:
  index.json
  html/{record_id}.html
  results/{record_id}.json
"""

import json
import uuid
import streamlit as st
import boto3
from datetime import datetime

# ── S3 client ─────────────────────────────────────────────────────────────────

def _get_s3():
    return boto3.client(
        "s3",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )

BUCKET = st.secrets["S3_BUCKET"]


def _s3_read(key: str) -> bytes | None:
    """Read a file from S3. Returns None if not found."""
    try:
        obj = _get_s3().get_object(Bucket=BUCKET, Key=key)
        return obj["Body"].read()
    except _get_s3().exceptions.NoSuchKey:
        return None
    except Exception as e:
        if "NoSuchKey" in str(e) or "404" in str(e):
            return None
        raise


def _s3_write(key: str, data: bytes):
    """Write bytes to S3."""
    _get_s3().put_object(Bucket=BUCKET, Key=key, Body=data)


def _s3_delete(key: str):
    """Delete a file from S3."""
    try:
        _get_s3().delete_object(Bucket=BUCKET, Key=key)
    except Exception:
        pass


# ── Index operations ──────────────────────────────────────────────────────────

def load_index() -> list[dict]:
    data = _s3_read("index.json")
    if data is None:
        return []
    return json.loads(data.decode("utf-8"))


def _save_index(index: list[dict]):
    _s3_write(
        "index.json",
        json.dumps(index, indent=2, default=str).encode("utf-8"),
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

def add_record(
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    html_bytes: bytes,
    result_json: dict,
) -> str:
    rid = uuid.uuid4().hex[:10]

    _s3_write(f"html/{rid}.html", html_bytes)
    _s3_write(
        f"results/{rid}.json",
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    index = load_index()
    index.append({
        "record_id": rid,
        "company": company,
        "industry": industry,
        "year": int(year),
        "filing_type": filing_type,
        "created_at": datetime.now().isoformat(),
    })
    _save_index(index)
    return rid


def get_result(record_id: str) -> dict | None:
    data = _s3_read(f"results/{record_id}.json")
    if data is None:
        return None
    return json.loads(data.decode("utf-8"))


def get_html(record_id: str) -> bytes | None:
    return _s3_read(f"html/{record_id}.html")


def delete_record(record_id: str):
    """Remove a record from the index and delete its files from S3."""
    index = load_index()
    index = [r for r in index if r["record_id"] != record_id]
    _save_index(index)
    _s3_delete(f"html/{record_id}.html")
    _s3_delete(f"results/{record_id}.json")


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
