"""S3-based persistence layer with deduplication."""

import json
import re
import uuid
import streamlit as st
import boto3
from datetime import datetime, timezone


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
RESULTS_PREFIX = "risk_analysis_results"
TABLES_PREFIX = "tables_extraction"
COMPARES_PREFIX = "compare_reports"
COMPARES_YOY_PREFIX = "compare_reports/same_company"
COMPARES_CROSS_PREFIX = "compare_reports/different_company"
AGENT_PREFIX = "agent_reports"
TICKER_MAP_KEY = "company_ticker_map.json"


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
    try:
        s3 = _get_s3()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                s3.delete_object(Bucket=BUCKET, Key=obj["Key"])
    except Exception:
        pass


def _sanitize_company(company: str) -> str:
    return re.sub(r"[^\w]", "", str(company or "").replace(" ", "_"))


def _sanitize_filing_type(filing_type: str) -> str:
    return re.sub(r"[^\w\-]", "", str(filing_type or "10-K"))


def _table_record_token(company: str, year, filing_type: str = "10-K") -> str:
    return f"{_sanitize_company(company)}_{int(year)}_{_sanitize_filing_type(filing_type)}"


def _list_s3_objects(prefix: str):
    items = []
    try:
        s3 = _get_s3()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
            items.extend(page.get("Contents", []))
    except Exception:
        return []
    return items


def load_index():
    data = _s3_read(INDEX_KEY)
    if data is None:
        return []
    return json.loads(data.decode("utf-8"))


def _save_index(index):
    _s3_write(INDEX_KEY, json.dumps(index, indent=2, default=str).encode("utf-8"))


def add_record(company, industry, year, filing_type, file_bytes, file_ext, result_json):
    year = int(year)

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


def save_table_result(company, year, filing_type, table_json, csv_string=""):
    safe = _sanitize_company(company)
    sf = _sanitize_filing_type(filing_type)

    _delete_by_prefix(f"{TABLES_PREFIX}/{safe}_{year}_{sf}_")

    sid = uuid.uuid4().hex[:4]
    base = f"{TABLES_PREFIX}/{safe}_{year}_{sf}_{sid}"

    _s3_write(
        f"{base}_tables.json",
        json.dumps(table_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    if csv_string:
        _s3_write(f"{base}_tables.csv", csv_string.encode("utf-8"))

    return base


def _latest_table_keys(company, year, filing_type="10-K"):
    token = _table_record_token(company, year, filing_type)
    prefix = f"{TABLES_PREFIX}/{token}_"
    objs = _list_s3_objects(prefix)
    if not objs:
        return None, None, None

    json_objs = [o for o in objs if str(o.get("Key", "")).endswith("_tables.json")]
    csv_objs = [o for o in objs if str(o.get("Key", "")).endswith("_tables.csv")]
    if not json_objs and not csv_objs:
        return None, None, None

    epoch = datetime.fromtimestamp(0, tz=timezone.utc)
    json_key = ""
    csv_key = ""
    base = ""

    if json_objs:
        latest_json = max(json_objs, key=lambda o: o.get("LastModified", epoch))
        json_key = str(latest_json.get("Key", "") or "")
        if json_key:
            base = json_key[:-len("_tables.json")]
            candidate_csv = f"{base}_tables.csv"
            if any(str(o.get("Key", "")) == candidate_csv for o in objs):
                csv_key = candidate_csv
            return base, json_key, csv_key or None

    latest_csv = max(csv_objs, key=lambda o: o.get("LastModified", epoch))
    csv_key = str(latest_csv.get("Key", "") or "")
    if not csv_key:
        return None, None, None
    base = csv_key[:-len("_tables.csv")]
    candidate_json = f"{base}_tables.json"
    if any(str(o.get("Key", "")) == candidate_json for o in objs):
        json_key = candidate_json
    return base, json_key or None, csv_key


def has_table_result(company, year, filing_type="10-K", presence_tokens=None):
    token = _table_record_token(company, year, filing_type)
    if isinstance(presence_tokens, set):
        return token in presence_tokens
    _, json_key, csv_key = _latest_table_keys(company, year, filing_type)
    return bool(json_key or csv_key)


def load_table_result(company, year, filing_type="10-K"):
    _, json_key, _ = _latest_table_keys(company, year, filing_type)
    if not json_key:
        return None
    data = _s3_read(json_key)
    if not data:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return None


def load_table_csv(company, year, filing_type="10-K"):
    _, _, csv_key = _latest_table_keys(company, year, filing_type)
    if not csv_key:
        return ""
    data = _s3_read(csv_key)
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except Exception:
        return ""


def load_table_presence_tokens():
    """Return a set of '<safe_company>_<year>_<safe_filing_type>' tokens with table JSON present."""
    tokens = set()
    objs = _list_s3_objects(f"{TABLES_PREFIX}/")
    for obj in objs:
        key = str(obj.get("Key", "") or "")
        if not (key.endswith("_tables.json") or key.endswith("_tables.csv")):
            continue
        name = key.split("/", 1)[-1]
        if key.endswith("_tables.json"):
            base = name[:-len("_tables.json")]
        else:
            base = name[:-len("_tables.csv")]
        token = base.rsplit("_", 1)[0] if "_" in base else ""
        if token:
            tokens.add(token)
    return tokens


def save_compare_result(company, filing_type, latest_year, prior_years, compare_json, mode="yoy"):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sf = re.sub(r"[^\w\-]", "", filing_type)

    if mode == "cross":
        # company is "CoA vs CoB", filename: CoA_YrA_vs_CoB_YrB
        prefix = COMPARES_CROSS_PREFIX
        base_name = re.sub(r"[^\w]", "", company.replace(" ", "_").replace("vs", "vs"))
        _delete_by_prefix(f"{prefix}/{base_name}_")
        sid = uuid.uuid4().hex[:4]
        key = f"{prefix}/{base_name}_{sid}.json"
    else:
        prefix = COMPARES_YOY_PREFIX
        ps = "&".join(str(y) for y in sorted(prior_years, reverse=True))
        _delete_by_prefix(f"{prefix}/{safe}_{latest_year}_vs_{ps}_{sf}_")
        sid = uuid.uuid4().hex[:4]
        key = f"{prefix}/{safe}_{latest_year}_vs_{ps}_{sf}_{sid}.json"

    _s3_write(key, json.dumps(compare_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"))
    return key


def save_agent_report(company, year, filing_type, report_json):
    safe = re.sub(r"[^\w]", "", company.replace(" ", "_"))
    sf = re.sub(r"[^\w\-]", "", filing_type)
    ts = datetime.now().strftime("%Y%m%d")

    # Delete any previous agent report for the same company/year/filing_type
    _delete_by_prefix(f"{AGENT_PREFIX}/{safe}_{year}_{sf}_")

    key = f"{AGENT_PREFIX}/{safe}_{year}_{sf}_{ts}.json"
    _s3_write(
        key,
        json.dumps(report_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    return key


def load_agent_reports():
    """Load all agent report JSONs from the agent_reports/ prefix.
    Returns a list of parsed report dicts."""
    reports = []
    try:
        s3 = _get_s3()
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=BUCKET, Prefix=AGENT_PREFIX + "/"):
            for obj in page.get("Contents", []):
                data = _s3_read(obj["Key"])
                if data:
                    reports.append(json.loads(data.decode("utf-8")))
    except Exception:
        pass
    return reports


def load_company_ticker_map():
    """Load persisted company->ticker mapping."""
    data = _s3_read(TICKER_MAP_KEY)
    if not data:
        return {}
    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out = {}
    for company, ticker in parsed.items():
        c = str(company or "").strip()
        t = str(ticker or "").strip().upper()
        if c and t:
            out[c] = t
    return out


def save_company_ticker_map(mapping):
    """Persist full company->ticker mapping."""
    if not isinstance(mapping, dict):
        mapping = {}
    cleaned = {}
    for company, ticker in mapping.items():
        c = str(company or "").strip()
        t = str(ticker or "").strip().upper()
        if c and t:
            cleaned[c] = t
    _s3_write(TICKER_MAP_KEY, json.dumps(cleaned, indent=2, ensure_ascii=False).encode("utf-8"))
    return cleaned


def upsert_company_ticker(company, ticker):
    """Set or update a single company ticker mapping."""
    c = str(company or "").strip()
    t = str(ticker or "").strip().upper()
    if not c or not t:
        return load_company_ticker_map()
    mapping = load_company_ticker_map()
    mapping[c] = t
    return save_company_ticker_map(mapping)


def remove_company_ticker(company):
    """Remove a company from persisted ticker mapping."""
    c = str(company or "").strip()
    mapping = load_company_ticker_map()
    if c in mapping:
        mapping.pop(c, None)
        save_company_ticker_map(mapping)
    return mapping


def get_company_ticker(company, default=""):
    """Get mapped ticker for a company, or default."""
    c = str(company or "").strip()
    if not c:
        return str(default or "")
    return load_company_ticker_map().get(c, str(default or ""))


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
