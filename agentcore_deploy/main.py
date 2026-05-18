"""Minimal AgentCore HTTP runtime + product REST API."""

from __future__ import annotations

import base64
import json
import os
import re
import ssl
import sys
import time
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import boto3
import certifi

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from core.comparator import compare_risks
except Exception:
    compare_risks = None

try:
    from core.extractor import (
        extract_item1_overview_bedrock,
        extract_item1a_risks_bedrock,
        extract_item1_overview_from_text,
        extract_item1a_risks_from_text,
        extract_text_from_pdf,
        locate_item1a,
    )
except Exception:
    extract_item1_overview_bedrock = None
    extract_item1a_risks_bedrock = None
    extract_item1_overview_from_text = None
    extract_item1a_risks_from_text = None
    extract_text_from_pdf = None
    locate_item1a = None

try:
    from core.sec_edgar import (
        download_10k_html_for_company_year,
        download_10q_html_for_company_year,
        build_filing_html_url,
    )
except Exception:
    download_10k_html_for_company_year = None
    download_10q_html_for_company_year = None
    download_10k_pdf_for_company_year = None
    build_filing_html_url = None

try:
    from core.sec_edgar import download_10k_pdf_for_company_year
except Exception:
    download_10k_pdf_for_company_year = None

try:
    from core.table_extractor import extract_tables_from_pdf
except Exception:
    extract_tables_from_pdf = None

_RUN_AGENT = None
_RUN_CHAT_AGENT = None
_LLM_INVOKE = None
_LLM_EXTRACTION_INVOKE = None
_LLM_INVOKE_WITH_TOOLS = None
_MODEL_ID = None
_EXTRACTION_MODEL_ID = None

INDEX_KEY = "filing_records_index.json"
RESULTS_PREFIX = "risk_analysis_results"
AGENT_PREFIX = "agent_reports"
TICKER_MAP_KEY = "company_ticker_map.json"
HTML_PREFIX = "10k_html_datasets"
PDF_PREFIX = "10k_pdf_datasets"
TABLES_PREFIX = "tables_extraction"
LEGACY_10Q_FILINGS_PREFIX = "10Q_fillings"

# ── New S3 layout (parallel 10-K / 10-Q folders) ─────────────────────
# When USE_NEW_S3_LAYOUT=1:
#   - 10-K lives under 10k_filings/<industry>/<company_dir>/...
#   - 10-Q lives under 10Q_fillings/<industry>/<company_dir>/...
# Each prefix has its own index.json. The runtime merges both indexes for
# records listing and lookup.
NEW_FILINGS_PREFIX = "10k_filings"
NEW_INDEX_KEY = f"{NEW_FILINGS_PREFIX}/index.json"
NEW_10Q_FILINGS_PREFIX = "10Q_fillings"
NEW_10Q_INDEX_KEY = f"{NEW_10Q_FILINGS_PREFIX}/index.json"
USE_NEW_LAYOUT = os.getenv("USE_NEW_S3_LAYOUT", "0").strip() == "1"
NEW_RECORD_ID_RE = re.compile(
    r"^(?P<dir>[A-Za-z0-9._\-]+)_(?P<year>\d{4})_(?P<form>10K|10Q)(?:_Q(?P<quarter>[1-4]))?$"
)
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_CACHE_TTL_SECONDS = 120
_STOCK_PROVIDER_STATE: Dict[str, Dict[str, Any]] = {}
_STOCK_PROVIDER_DEFAULT_COOLDOWN_SECONDS = 70
_STOCK_QUOTE_CACHE: Dict[str, Dict[str, Any]] = {}
_STOCK_QUOTE_CACHE_TTL_SECONDS = 600
_STOCK_QUOTE_CACHE_PREFIX = "stock_quote_cache_v1"
_WIKIDATA_STOCK_PROFILE_CACHE: Dict[str, Dict[str, Any]] = {}
_WIKIDATA_STOCK_PROFILE_TTL_SECONDS = 60 * 60 * 24
_S3_CLIENT = None
_S3_CLIENT_LOCK = threading.Lock()
_INDEX_CACHE: Dict[str, Any] = {"ts": 0.0, "data": []}
_INDEX_CACHE_TTL_SECONDS = 20
_RESULT_CACHE: Dict[str, Dict[str, Any]] = {}
_RESULT_CACHE_TTL_SECONDS = 300
_RESULT_CACHE_MAX_ENTRIES = 600
_TICKER_MAP_CACHE: Dict[str, Any] = {"ts": 0.0, "data": {}}
_TICKER_MAP_CACHE_TTL_SECONDS = 60
_AGENT_REPORTS_CACHE: Dict[str, Any] = {"ts": 0.0, "data": []}
_AGENT_REPORTS_CACHE_TTL_SECONDS = 90
_RECORDS_LIST_CACHE: Dict[str, Dict[str, Any]] = {}
_RECORDS_LIST_CACHE_TTL_SECONDS = 30
_DASHBOARD_SUMMARY_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_DASHBOARD_SUMMARY_CACHE_TTL_SECONDS = 300
_FORCED_INDUSTRY_BY_TICKER: Dict[str, str] = {
    "AAPL": "Technology",
}


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


def _canonical_filing_type(value: Any) -> str:
    txt = str(value or "").strip().upper()
    if txt in {"10Q", "10-Q"}:
        return "10-Q"
    return "10-K"


def _filing_type_token(value: Any) -> str:
    return "10Q" if _canonical_filing_type(value) == "10-Q" else "10K"


def _legacy_html_prefix_for_filing_type(value: Any) -> str:
    return f"{HTML_PREFIX}/{_canonical_filing_type(value)}"


def _legacy_html_keys_for_record(record_id: str, filing_type: Any) -> List[str]:
    rid = str(record_id or "").strip()
    if not rid:
        return []
    keys = [
        f"{_legacy_html_prefix_for_filing_type(filing_type)}/{rid}.html",
        f"{HTML_PREFIX}/{rid}.html",  # backward-compatible legacy flat key
    ]
    out: List[str] = []
    for key in keys:
        if key and key not in out:
            out.append(key)
    return out


def _legacy_10q_html_key(
    *,
    industry: str,
    company_dir: str,
    year: int,
    filing_quarter: int,
) -> str:
    q = filing_quarter if filing_quarter in {1, 2, 3, 4} else 0
    q_suffix = f"_Q{q}" if q > 0 else ""
    return (
        f"{LEGACY_10Q_FILINGS_PREFIX}/{str(industry or 'Other').strip() or 'Other'}/"
        f"{str(company_dir or '').strip()}/{int(year or 0)}_10Q{q_suffix}.html"
    )


def _legacy_10q_result_key(
    *,
    industry: str,
    company_dir: str,
    year: int,
    filing_quarter: int,
) -> str:
    q = filing_quarter if filing_quarter in {1, 2, 3, 4} else 0
    q_suffix = f"_Q{q}" if q > 0 else ""
    return (
        f"{LEGACY_10Q_FILINGS_PREFIX}/{str(industry or 'Other').strip() or 'Other'}/"
        f"{str(company_dir or '').strip()}/{int(year or 0)}_10Q{q_suffix}_risks.json"
    )


def _coerce_filing_quarter(value: Any, filing_type: Any) -> int:
    try:
        q = int(value or 0)
    except Exception:
        q = 0
    if _canonical_filing_type(filing_type) != "10-Q":
        return 0
    return q if q in {1, 2, 3, 4} else 0


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


def _infer_filing_quarter(sec_meta: Any, filing_type: Any) -> int:
    if _canonical_filing_type(filing_type) != "10-Q" or not isinstance(sec_meta, dict):
        return 0
    for key in ("report_date", "filing_date"):
        raw = str(sec_meta.get(key, "") or "").strip()
        parts = raw.split("-")
        if len(parts) >= 2 and parts[1].isdigit():
            return _month_to_quarter(int(parts[1]))
    return 0


def _extract_10q_incremental_update(item1a_text: str) -> dict:
    """Parse 10-Q Item 1A and extract incremental risk updates (if any).

    Many 10-Q filings use wording like "Except as set forth below, there
    have been no material changes..." and then list only newly added or
    changed risks. This helper extracts that delta slice without changing
    the primary `risks` structure.
    """
    raw = str(item1a_text or "").replace("\xa0", " ")
    norm = re.sub(r"[ \t]+", " ", raw)
    norm = re.sub(r"\n{3,}", "\n\n", norm).strip()
    out = {
        "detected": False,
        "has_incremental_updates": False,
        "trigger_phrase": "",
        "incremental_risk_items": [],
        "incremental_count": 0,
        "source_excerpt": "",
    }
    if len(norm) < 120:
        return out

    trigger_patterns = [
        re.compile(r"except as set forth below", re.IGNORECASE),
        re.compile(r"except as discussed below", re.IGNORECASE),
        re.compile(r"except as (?:described|noted) below", re.IGNORECASE),
        re.compile(r"there have been no material changes?[^.:\n]{0,240}risk factors?", re.IGNORECASE),
    ]

    trigger_match = None
    for pat in trigger_patterns:
        m = pat.search(norm)
        if m and (trigger_match is None or m.start() < trigger_match.start()):
            trigger_match = m
    if not trigger_match:
        return out

    out["detected"] = True
    out["trigger_phrase"] = str(trigger_match.group(0) or "").strip()
    tail = norm[trigger_match.end():].strip()
    if not tail:
        return out

    # Trim at next item heading if present.
    end_m = re.search(r"(?im)^\s*item\s*1b\b|^\s*item\s*2\b", tail)
    if end_m:
        tail = tail[: end_m.start()].strip()
    if not tail:
        return out

    # Candidate slices: paragraphs first; if too coarse, split by sentences.
    para_candidates = [p.strip(" -•\n\t") for p in re.split(r"\n{2,}", tail) if p and p.strip()]
    units: List[str] = []
    risk_cue = re.compile(
        r"\b(risk|risks|regulation|regulatory|compliance|antitrust|litigation|lawsuit|"
        r"investigation|competition|contract|agreement|dependency|enforcement|penalt(?:y|ies)|"
        r"dma|doj|search)\b",
        re.IGNORECASE,
    )

    for para in para_candidates:
        p = re.sub(r"\s+", " ", para).strip()
        if len(p) < 50:
            continue
        # Skip header/disclaimer phrases.
        if re.search(r"no material changes?", p, re.IGNORECASE):
            continue
        if len(p) <= 420:
            if risk_cue.search(p):
                units.append(p)
            continue
        # Split very long paragraphs into sentence-like units.
        for sent in re.split(r"(?<=[\.;])\s+(?=[A-Z])", p):
            s = re.sub(r"\s+", " ", sent).strip(" -•\t\n")
            if len(s) < 60 or len(s) > 520:
                continue
            if risk_cue.search(s):
                units.append(s)

    # Dedupe while preserving order.
    seen: Set[str] = set()
    deduped: List[str] = []
    for item in units:
        k = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if not k or k in seen:
            continue
        seen.add(k)
        deduped.append(item)

    if deduped:
        out["has_incremental_updates"] = True
        out["incremental_risk_items"] = deduped[:30]
        out["incremental_count"] = len(out["incremental_risk_items"])
    out["source_excerpt"] = tail[:1200]
    return out


def _bucket() -> str:
    return _env("S3_BUCKET", "").strip()


def _aws_region() -> str:
    return _env("AWS_REGION", "us-west-1").strip() or "us-west-1"


def _s3_client():
    global _S3_CLIENT
    if _S3_CLIENT is not None:
        return _S3_CLIENT
    with _S3_CLIENT_LOCK:
        if _S3_CLIENT is not None:
            return _S3_CLIENT
        kwargs = {"region_name": _aws_region()}
        access_key = _env("AWS_ACCESS_KEY_ID", "").strip()
        secret_key = _env("AWS_SECRET_ACCESS_KEY", "").strip()
        session_token = _env("AWS_SESSION_TOKEN", "").strip()
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                kwargs["aws_session_token"] = session_token
        _S3_CLIENT = boto3.client("s3", **kwargs)
        return _S3_CLIENT


def _invalidate_runtime_caches(storage_key: str = "") -> None:
    key = str(storage_key or "").strip()
    now = 0.0
    if not key:
        _INDEX_CACHE["ts"] = now
        _TICKER_MAP_CACHE["ts"] = now
        _AGENT_REPORTS_CACHE["ts"] = now
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        _RECORDS_LIST_CACHE.clear()
        _RESULT_CACHE.clear()
        return

    if key == INDEX_KEY:
        _INDEX_CACHE["ts"] = now
        _RECORDS_LIST_CACHE.clear()
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return

    if key == TICKER_MAP_KEY:
        _TICKER_MAP_CACHE["ts"] = now
        _RECORDS_LIST_CACHE.clear()
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return

    if key.startswith(f"{RESULTS_PREFIX}/"):
        rid = key.rsplit("/", 1)[-1].replace(".json", "")
        if rid:
            _RESULT_CACHE.pop(rid, None)
        _RECORDS_LIST_CACHE.clear()
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return

    if key.startswith(f"{AGENT_PREFIX}/"):
        _AGENT_REPORTS_CACHE["ts"] = now
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return

    if key == NEW_INDEX_KEY:
        _INDEX_CACHE["ts"] = now
        _TICKER_MAP_CACHE["ts"] = now
        _RECORDS_LIST_CACHE.clear()
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return

    if key.startswith(f"{NEW_FILINGS_PREFIX}/") or key.startswith(f"{NEW_10Q_FILINGS_PREFIX}/"):
        # Any write under 10k_filings/... or 10Q_fillings/...
        # invalidates the per-record cache + the dashboard summary cache.
        # We don't try to derive the synthetic record_id from the key
        # (it would require re-reading the index); clearing the whole
        # _RESULT_CACHE is cheap and safe.
        _RESULT_CACHE.clear()
        _RECORDS_LIST_CACHE.clear()
        _DASHBOARD_SUMMARY_CACHE["ts"] = now
        return


def _read_s3_bytes(key: str) -> Optional[bytes]:
    bucket = _bucket()
    if not bucket:
        return None
    try:
        obj = _s3_client().get_object(Bucket=bucket, Key=key)
        return obj["Body"].read()
    except Exception as e:
        msg = str(e)
        if (
            "NoSuchKey" in msg
            or "404" in msg
            or "NoSuchBucket" in msg
            or "Invalid bucket name" in msg
            or "AccessDenied" in msg
        ):
            return None
        raise


def _write_s3_bytes(key: str, data: bytes) -> None:
    bucket = _bucket()
    if not bucket:
        raise RuntimeError("S3_BUCKET is not configured.")
    _s3_client().put_object(Bucket=bucket, Key=key, Body=data)
    _invalidate_runtime_caches(key)


def _delete_s3_key(key: str) -> None:
    bucket = _bucket()
    if not bucket:
        return
    try:
        _s3_client().delete_object(Bucket=bucket, Key=key)
        _invalidate_runtime_caches(key)
    except Exception:
        return


def _list_s3_keys(prefix: str) -> List[str]:
    bucket = _bucket()
    if not bucket:
        return []
    keys: List[str] = []
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                k = str(item.get("Key", "") or "")
                if k:
                    keys.append(k)
    except Exception:
        return []
    return keys


def _json_from_bytes(data: Optional[bytes], fallback: Any):
    if not data:
        return fallback
    try:
        return json.loads(data.decode("utf-8"))
    except Exception:
        return fallback


def _new_layout_record_id(
    company_dir: str,
    year: int,
    filing_type: str = "10-K",
    filing_quarter: int = 0,
) -> str:
    """Synthetic record_id for a filing in the new layout. The format
    mirrors `<dir>_<year>_<form_token>` so it is parseable back into
    (dir, year, form) via NEW_RECORD_ID_RE without an extra round-trip
    to the index."""
    base = f"{str(company_dir or '').strip()}_{int(year or 0)}_{_filing_type_token(filing_type)}"
    q = _coerce_filing_quarter(filing_quarter, filing_type)
    if _canonical_filing_type(filing_type) == "10-Q" and q > 0:
        return f"{base}_Q{q}"
    return base


def _new_layout_keys_for_record_id(rid: str) -> Optional[tuple[str, str, str, int, str, int]]:
    """Parse a new-layout rid into
    (industry_dir, company_dir, json_key, year, filing_type, filing_quarter).

    Requires the new index to be readable so we can resolve which
    industry directory the company sits under. Returns None if the rid
    is not in the new layout — callers fall back to the legacy paths.
    """
    m = NEW_RECORD_ID_RE.match(str(rid or "").strip())
    if not m:
        return None
    company_dir = m.group("dir")
    year = int(m.group("year"))
    filing_type = "10-Q" if m.group("form") == "10Q" else "10-K"
    filing_quarter = int(m.group("quarter")) if m.group("quarter") else 0

    new_index = _load_new_layout_10q_index_doc() if filing_type == "10-Q" else _load_new_layout_index_doc()
    industries = new_index.get("industries", {}) if isinstance(new_index, dict) else {}
    for ind_dir, companies in (industries or {}).items():
        if not isinstance(companies, dict):
            continue
        block = companies.get(company_dir)
        if not isinstance(block, dict):
            continue
        filings = block.get("filings", [])
        if isinstance(filings, list):
            for filing in filings:
                if not isinstance(filing, dict):
                    continue
                try:
                    f_year = int(filing.get("year") or 0)
                except Exception:
                    continue
                f_type = _canonical_filing_type(filing.get("filing_type"))
                f_quarter = _coerce_filing_quarter(filing.get("filing_quarter"), f_type)
                quarter_match = True
                if f_type == "10-Q" and filing_quarter > 0:
                    quarter_match = f_quarter == filing_quarter
                if f_year == year and f_type == filing_type and quarter_match:
                    json_key = str(filing.get("json_key", "") or "").strip()
                    if json_key:
                        return ind_dir, company_dir, json_key, year, filing_type, f_quarter
        # Backward-compatible fallback for legacy 10-K / 10-Q path shapes.
        if filing_type == "10-K":
            json_key = f"{NEW_FILINGS_PREFIX}/{ind_dir}/{company_dir}/{year}_10K_risks.json"
            return ind_dir, company_dir, json_key, year, filing_type, 0
        if filing_type == "10-Q":
            q_suffix = f"_Q{filing_quarter}" if filing_quarter > 0 else ""
            json_key = f"{NEW_10Q_FILINGS_PREFIX}/{ind_dir}/{company_dir}/{year}_10Q{q_suffix}_risks.json"
            return ind_dir, company_dir, json_key, year, filing_type, filing_quarter
    return None


def _load_new_layout_index_doc() -> dict:
    """Read the dict-shaped index.json under 10k_filings/. Distinct from
    `_load_index()` (which returns a flat list of records). Cached via
    the same `_INDEX_CACHE` slot using the dict shape.
    """
    raw = _json_from_bytes(_read_s3_bytes(NEW_INDEX_KEY), {})
    return raw if isinstance(raw, dict) else {}


def _load_new_layout_10q_index_doc() -> dict:
    """Read the dict-shaped index.json under 10Q_fillings/."""
    raw = _json_from_bytes(_read_s3_bytes(NEW_10Q_INDEX_KEY), {})
    return raw if isinstance(raw, dict) else {}


def _flatten_new_layout_index(doc: dict) -> List[dict]:
    """Convert the dict-shaped 10k_filings/index.json into the flat
    record list the rest of the runtime expects. Each filing becomes one
    record with synthetic `record_id = <company_dir>_<year>_<form>`.
    """
    out: List[dict] = []
    industries = doc.get("industries", {}) if isinstance(doc, dict) else {}
    if not isinstance(industries, dict):
        return out
    for ind_dir, companies in industries.items():
        if not isinstance(companies, dict):
            continue
        for company_dir, block in companies.items():
            if not isinstance(block, dict):
                continue
            company = str(block.get("company", "") or "").strip() or company_dir.replace("_", " ")
            ticker = str(block.get("ticker", "") or "").strip().upper()
            for f in block.get("filings", []) or []:
                if not isinstance(f, dict):
                    continue
                try:
                    year = int(f.get("year") or 0)
                except Exception:
                    continue
                out.append({
                    "record_id": _new_layout_record_id(
                        company_dir,
                        year,
                        str(f.get("filing_type", "10-K") or "10-K"),
                        _coerce_filing_quarter(f.get("filing_quarter"), f.get("filing_type")),
                    ),
                    "company": company,
                    "ticker": ticker,
                    "industry": ind_dir,
                    "year": year,
                    "filing_type": str(f.get("filing_type", "10-K") or "10-K"),
                    "filing_quarter": _coerce_filing_quarter(f.get("filing_quarter"), f.get("filing_type")),
                    "file_ext": "html",
                    "risk_items": int(f.get("sub_risk_count") or 0),
                    "risk_categories": 0,
                    "has_ai_summary": False,
                    "created_at": str(f.get("extracted_at", "") or ""),
                    "_source_layout": "new",
                })
    return out


def _load_index() -> List[dict]:
    now = time.time()
    cached_ts = float(_INDEX_CACHE.get("ts", 0.0) or 0.0)
    cached_data = _INDEX_CACHE.get("data", [])
    if (now - cached_ts) <= _INDEX_CACHE_TTL_SECONDS and isinstance(cached_data, list):
        return [r for r in cached_data if isinstance(r, dict)]

    out: List[dict] = []
    if USE_NEW_LAYOUT:
        new_doc_10k = _load_new_layout_index_doc()
        new_doc_10q = _load_new_layout_10q_index_doc()
        out = _flatten_new_layout_index(new_doc_10k) + _flatten_new_layout_index(new_doc_10q)
        # De-dupe by record_id in case of accidental overlap during migration.
        deduped: Dict[str, dict] = {}
        for rec in out:
            rid = str(rec.get("record_id", "") or "").strip()
            if not rid:
                continue
            prev = deduped.get(rid)
            if not isinstance(prev, dict):
                deduped[rid] = rec
                continue
            prev_ts = str(prev.get("created_at", "") or "")
            curr_ts = str(rec.get("created_at", "") or "")
            if curr_ts > prev_ts:
                deduped[rid] = rec
        out = list(deduped.values())
        if not out:
            # Soft fallback — if the new index hasn't been published yet
            # we still want the API to surface the legacy data instead
            # of an empty list.
            raw = _json_from_bytes(_read_s3_bytes(INDEX_KEY), [])
            if isinstance(raw, list):
                out = [r for r in raw if isinstance(r, dict)]
            elif isinstance(raw, dict):
                candidates = raw.get("items")
                if isinstance(candidates, list):
                    out = [r for r in candidates if isinstance(r, dict)]
    else:
        raw = _json_from_bytes(_read_s3_bytes(INDEX_KEY), [])
        if isinstance(raw, list):
            out = [r for r in raw if isinstance(r, dict)]
        elif isinstance(raw, dict):
            candidates = raw.get("items")
            if isinstance(candidates, list):
                out = [r for r in candidates if isinstance(r, dict)]

    _INDEX_CACHE["ts"] = now
    _INDEX_CACHE["data"] = out
    return out


def _load_result(record_id: str) -> Optional[dict]:
    rid = str(record_id or "").strip()
    if not rid:
        return None
    cached = _RESULT_CACHE.get(rid)
    now = time.time()
    if isinstance(cached, dict):
        ts = float(cached.get("ts", 0.0) or 0.0)
        if now - ts <= _RESULT_CACHE_TTL_SECONDS:
            payload = cached.get("data")
            if isinstance(payload, dict):
                return payload

    payload: Optional[dict] = None

    rec = next((r for r in _load_index() if str(r.get("record_id", "") or "").strip() == rid), None)
    if isinstance(rec, dict):
        rec_result_key = str(rec.get("result_key", "") or "").strip()
        if rec_result_key:
            payload = _json_from_bytes(_read_s3_bytes(rec_result_key), None)

    # New-layout rids look like "<company_dir>_<year>_<form>"; resolve their
    # JSON via the dict-shaped index.json. Falls through to legacy on miss.
    new_keys = _new_layout_keys_for_record_id(rid)
    if new_keys and not isinstance(payload, dict):
        _ind, _comp, json_key, _year, _filing_type, _filing_quarter = new_keys
        payload = _json_from_bytes(_read_s3_bytes(json_key), None)

    if not isinstance(payload, dict):
        payload = _json_from_bytes(_read_s3_bytes(f"{RESULTS_PREFIX}/{rid}.json"), None)

    if isinstance(payload, dict):
        _RESULT_CACHE[rid] = {"ts": now, "data": payload}
        if len(_RESULT_CACHE) > _RESULT_CACHE_MAX_ENTRIES:
            oldest_key = min(_RESULT_CACHE.items(), key=lambda kv: float(kv[1].get("ts", 0.0) or 0.0))[0]
            _RESULT_CACHE.pop(oldest_key, None)
    return payload


def _load_company_ticker_map() -> Dict[str, str]:
    now = time.time()
    cached_ts = float(_TICKER_MAP_CACHE.get("ts", 0.0) or 0.0)
    cached_data = _TICKER_MAP_CACHE.get("data", {})
    if (now - cached_ts) <= _TICKER_MAP_CACHE_TTL_SECONDS and isinstance(cached_data, dict):
        return {str(k): str(v) for k, v in cached_data.items()}

    out: Dict[str, str] = {}

    # In the new layout the ticker map is implicit in 10k_filings/index.json
    # (each company block carries `company` + `ticker`). Use it as the
    # primary source so we don't need to maintain a parallel JSON file.
    if USE_NEW_LAYOUT:
        new_doc = _load_new_layout_index_doc()
        for ind in (new_doc.get("industries", {}) or {}).values():
            if not isinstance(ind, dict):
                continue
            for block in ind.values():
                if not isinstance(block, dict):
                    continue
                c = str(block.get("company", "") or "").strip()
                t = str(block.get("ticker", "") or "").strip().upper()
                if c and t:
                    out[c] = t

    if not out:
        raw = _json_from_bytes(_read_s3_bytes(TICKER_MAP_KEY), {})
        if isinstance(raw, dict):
            for company, ticker in raw.items():
                c = str(company or "").strip()
                t = str(ticker or "").strip().upper()
                if c and t:
                    out[c] = t

    _TICKER_MAP_CACHE["ts"] = now
    _TICKER_MAP_CACHE["data"] = out
    return out


def _normalize_ticker(raw: Any) -> str:
    return re.sub(r"[^A-Z0-9.\-]", "", str(raw or "").strip().upper())


def _company_lookup_key(raw: Any) -> str:
    s = str(raw or "").strip().lower()
    if not s:
        return ""
    s = re.sub(r"[.,()'’]", " ", s)
    s = re.sub(r"\b(inc|incorporated|corp|corporation|company|co|ltd|limited|plc|holdings?|group|class [ab])\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _build_ticker_lookup() -> tuple[Dict[str, str], Dict[str, str]]:
    raw = _load_company_ticker_map()
    exact: Dict[str, str] = {}
    canonical: Dict[str, str] = {}
    for company, ticker in raw.items():
        c = str(company or "").strip()
        t = _normalize_ticker(ticker)
        if not c or not t:
            continue
        exact[c] = t
        key = _company_lookup_key(c)
        if key and key not in canonical:
            canonical[key] = t
    return exact, canonical


def _resolve_record_ticker(rec: dict, ticker_lookup: Optional[tuple[Dict[str, str], Dict[str, str]]] = None) -> str:
    direct = _normalize_ticker(rec.get("ticker"))
    if direct:
        return direct

    company = str(rec.get("company", "") or "").strip()
    if not company:
        return ""

    exact_map, canonical_map = ticker_lookup if ticker_lookup else _build_ticker_lookup()
    from_exact = _normalize_ticker(exact_map.get(company))
    if from_exact:
        return from_exact

    key = _company_lookup_key(company)
    if not key:
        return ""
    return _normalize_ticker(canonical_map.get(key))


def _token_set(text: str) -> Set[str]:
    return {t for t in str(text or "").split() if t}


def _similarity_token_score(a: str, b: str) -> int:
    ta = _token_set(_company_lookup_key(a))
    tb = _token_set(_company_lookup_key(b))
    if not ta or not tb:
        return 0
    overlap = len(ta.intersection(tb))
    if overlap <= 0:
        return 0
    return overlap * 8


def _is_us_equity_exchange(raw: Any) -> bool:
    text = str(raw or "").strip().upper()
    if not text:
        return False
    markers = [
        "NMS",
        "NCM",
        "NGM",
        "NYQ",
        "ASE",
        "PCX",
        "BATS",
        "NASDAQ",
        "NYSE",
        "AMEX",
        "NYSEARCA",
        "NASDAQGS",
        "NASDAQGM",
    ]
    return any(m in text for m in markers)


def _search_yahoo_ticker_by_company(company: str, ticker_hint: str = "") -> Optional[dict]:
    comp = str(company or "").strip()
    if not comp:
        return None

    params = {
        "q": comp,
        "quotesCount": 12,
        "newsCount": 0,
        "enableFuzzyQuery": "true",
        "lang": "en-US",
        "region": "US",
    }
    url = f"https://query2.finance.yahoo.com/v1/finance/search?{urlencode(params)}"
    payload = _yahoo_json(url)
    rows = payload.get("quotes", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list) or not rows:
        return None

    hint = _normalize_ticker(ticker_hint)
    comp_key = _company_lookup_key(comp)
    comp_tokens = _token_set(comp_key)
    best: Optional[dict] = None
    best_score = -1

    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = _normalize_ticker(row.get("symbol"))
        if not symbol:
            continue

        qtype = str(row.get("quoteType") or row.get("typeDisp") or "").strip().upper()
        if qtype and ("EQUITY" not in qtype and "ETF" not in qtype):
            continue

        name = str(row.get("shortname") or row.get("longname") or "").strip()
        exchange = str(row.get("exchange") or row.get("exchDisp") or "").strip()
        name_key = _company_lookup_key(name)
        name_tokens = _token_set(name_key)

        score = 0
        if comp_key and name_key and comp_key == name_key:
            score += 120
        elif comp_key and name_key and (comp_key in name_key or name_key in comp_key):
            score += 75
        else:
            overlap = len(comp_tokens.intersection(name_tokens))
            if overlap > 0:
                score += overlap * 15

        score += _similarity_token_score(comp, name)
        if _is_us_equity_exchange(exchange):
            score += 24
        if qtype == "EQUITY":
            score += 16
        elif "ETF" in qtype:
            score += 6
        if hint:
            if symbol == hint:
                score += 10
            elif symbol.split(".")[0] == hint.split(".")[0]:
                score += 6
        if "." not in symbol and "-" not in symbol:
            score += 4
        if len(symbol) <= 5:
            score += 3

        if score > best_score:
            best_score = score
            best = {
                "ticker": symbol,
                "name": name,
                "exchange": exchange,
                "quote_type": qtype,
                "score": score,
            }

    return best


def _resolve_ticker_for_company(company: str, ticker_hint: str = "") -> dict:
    comp = str(company or "").strip()
    hint = _normalize_ticker(ticker_hint)
    if not comp:
        return {"ok": False, "error": "company is required"}

    exact_map, canonical_map = _build_ticker_lookup()
    mapped = _normalize_ticker(exact_map.get(comp))
    if not mapped:
        mapped = _normalize_ticker(canonical_map.get(_company_lookup_key(comp)))

    candidates: List[str] = []
    if hint:
        candidates.append(hint)
    if mapped and mapped not in candidates:
        candidates.append(mapped)

    search_hit = None
    try:
        search_hit = _search_yahoo_ticker_by_company(comp, ticker_hint=hint)
    except Exception:
        search_hit = None
    if search_hit and _normalize_ticker(search_hit.get("ticker")) not in candidates:
        candidates.append(_normalize_ticker(search_hit.get("ticker")))

    checked: List[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        checked.append(candidate)
        try:
            payload = _stock_quote(candidate, lite=False)
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("error"):
            continue
        if _to_float(payload.get("change_percent")) is None and _to_float(payload.get("change")) is None:
            continue
        return {
            "ok": True,
            "company": comp,
            "ticker": candidate,
            "source": "search" if search_hit and candidate == _normalize_ticker(search_hit.get("ticker")) else "mapping",
            "checked": checked,
            "search": search_hit or {},
        }

    if search_hit and _normalize_ticker(search_hit.get("ticker")):
        found = _normalize_ticker(search_hit.get("ticker"))
        return {
            "ok": True,
            "company": comp,
            "ticker": found,
            "source": "search_unverified",
            "checked": checked,
            "search": search_hit,
        }

    return {
        "ok": False,
        "company": comp,
        "error": "No usable ticker found from mapping/search.",
        "checked": checked,
        "search": search_hit or {},
    }


def _save_index(index: List[dict]) -> None:
    payload = json.dumps(index, indent=2, default=str, ensure_ascii=False).encode("utf-8")
    _write_s3_bytes(INDEX_KEY, payload)


def _save_company_ticker_map(mapping: Dict[str, str]) -> None:
    payload = json.dumps(mapping, indent=2, ensure_ascii=False).encode("utf-8")
    _write_s3_bytes(TICKER_MAP_KEY, payload)


def _upsert_company_ticker(company: str, ticker: str) -> None:
    c = str(company or "").strip()
    t = str(ticker or "").strip().upper()
    if not c or not t:
        return
    mapping = _load_company_ticker_map()
    mapping[c] = t
    _save_company_ticker_map(mapping)


def _sanitize_company(company: str) -> str:
    return re.sub(r"[^\w]", "", str(company or "").replace(" ", "_"))


def _sanitize_filing_type(filing_type: str) -> str:
    return re.sub(r"[^\w\-]", "", str(filing_type or "10-K"))


def _delete_s3_prefix(prefix: str) -> None:
    bucket = _bucket()
    if not bucket:
        return
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []) or []:
                key = str(obj.get("Key", "") or "")
                if key:
                    s3.delete_object(Bucket=bucket, Key=key)
    except Exception:
        return


def _table_record_token(company: str, year: int, filing_type: str = "10-K") -> str:
    return f"{_sanitize_company(company)}_{int(year)}_{_sanitize_filing_type(filing_type)}"


_TABLE_DISPLAY_ORDER = [
    "income_statement",
    "comprehensive_income",
    "balance_sheet",
    "shareholders_equity",
    "cash_flow",
]


def _count_found_tables(data: dict) -> int:
    if not isinstance(data, dict):
        return 0
    return sum(1 for key in _TABLE_DISPLAY_ORDER if isinstance(data.get(key), dict) and data.get(key, {}).get("found"))


def _classified_to_csv(data: dict) -> str:
    if not isinstance(data, dict):
        return ""
    rows: List[str] = []
    for cat_key in _TABLE_DISPLAY_ORDER:
        cat_data = data.get(cat_key, {})
        if not isinstance(cat_data, dict) or not cat_data.get("found"):
            continue
        display_name = str(cat_data.get("display_name", cat_key) or cat_key)
        unit = str(cat_data.get("unit", "") or "")
        headers = cat_data.get("headers", []) if isinstance(cat_data.get("headers"), list) else []
        table_rows = cat_data.get("rows", []) if isinstance(cat_data.get("rows"), list) else []

        rows.append(f"=== {display_name} ===")
        if unit:
            rows.append(f"({unit})")
        rows.append("")
        if headers:
            rows.append(",".join([str(v or "").replace(",", " ") for v in headers]))
        for row in table_rows:
            if isinstance(row, list):
                rows.append(",".join([str(v or "").replace(",", " ") for v in row]))
        rows.append("")
        rows.append("")

    return "\n".join(rows)


def _save_table_result(company: str, year: int, filing_type: str, table_json: dict, csv_string: str = "") -> str:
    token = _table_record_token(company, year, filing_type)
    _delete_s3_prefix(f"{TABLES_PREFIX}/{token}_")

    sid = uuid.uuid4().hex[:4]
    base = f"{TABLES_PREFIX}/{token}_{sid}"
    _write_s3_bytes(
        f"{base}_tables.json",
        json.dumps(table_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    if csv_string:
        _write_s3_bytes(f"{base}_tables.csv", csv_string.encode("utf-8"))
    return base


def _load_table_result(company: str, year: int, filing_type: str = "10-K") -> Optional[dict]:
    token = _table_record_token(company, year, filing_type)
    prefix = f"{TABLES_PREFIX}/{token}_"
    keys = [k for k in _list_s3_keys(prefix) if k.endswith("_tables.json")]
    if not keys:
        return None
    keys.sort(reverse=True)
    data = _read_s3_bytes(keys[0])
    if not data:
        return None
    try:
        payload = json.loads(data.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _extract_tables_for_pdf(
    *,
    pdf_bytes: bytes,
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    source: str,
) -> tuple[Optional[dict], str, str]:
    if extract_tables_from_pdf is None:
        return None, "", "Tables extraction pipeline is unavailable in runtime."
    try:
        classified = extract_tables_from_pdf(pdf_bytes)
    except Exception as exc:
        return None, "", f"Textract extraction failed: {type(exc).__name__}: {exc}"

    found_count = _count_found_tables(classified)
    if found_count <= 0:
        return None, "", "No core financial tables could be identified in this filing PDF."

    result = {
        "company": str(company or "").strip(),
        "industry": str(industry or "Other").strip() or "Other",
        "year": int(year),
        "filing_type": str(filing_type or "10-K").strip() or "10-K",
        "tables_found": found_count,
        "source": source or "tables_manual_pdf",
        **(classified if isinstance(classified, dict) else {}),
    }
    key = _save_table_result(
        company=result["company"],
        year=result["year"],
        filing_type=result["filing_type"],
        table_json=result,
        csv_string=_classified_to_csv(classified),
    )
    return result, key, ""


def _add_record(
    *,
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    ticker: str,
    file_bytes: bytes,
    file_ext: str,
    result_json: dict,
    filing_quarter: int = 0,
) -> dict:
    company = str(company or "").strip()
    industry = str(industry or "Other").strip() or "Other"
    filing_type = _canonical_filing_type(filing_type)
    filing_quarter = _coerce_filing_quarter(filing_quarter, filing_type)
    ticker = _normalize_ticker(ticker)
    year = int(year or 0)
    ext = "pdf" if str(file_ext or "").strip().lower() == "pdf" else "html"

    index = _load_index()
    dupes = [
        r
        for r in index
        if str(r.get("company", "")) == company
        and int(r.get("year", 0) or 0) == year
        and str(r.get("filing_type", "")) == filing_type
        and (
            filing_type != "10-Q"
            or _coerce_filing_quarter(r.get("filing_quarter"), r.get("filing_type")) == filing_quarter
        )
    ]
    for d in dupes:
        old_id = str(d.get("record_id", "") or "")
        if not old_id:
            continue
        old_ext = "pdf" if str(d.get("file_ext", "html")).lower() == "pdf" else "html"
        if old_ext == "pdf":
            _delete_s3_key(f"{PDF_PREFIX}/{old_id}.{old_ext}")
        else:
            old_ft = str(d.get("filing_type", "") or filing_type)
            for key in _legacy_html_keys_for_record(old_id, old_ft):
                _delete_s3_key(key)
        old_result_key = str(d.get("result_key", "") or "").strip()
        if old_result_key:
            _delete_s3_key(old_result_key)
        _delete_s3_key(f"{RESULTS_PREFIX}/{old_id}.json")

    index = [
        r
        for r in index
        if not (
            str(r.get("company", "")) == company
            and int(r.get("year", 0) or 0) == year
            and str(r.get("filing_type", "")) == filing_type
            and (
                filing_type != "10-Q"
                or _coerce_filing_quarter(r.get("filing_quarter"), r.get("filing_type")) == filing_quarter
            )
        )
    ]

    risk_items = 0
    risk_categories = 0
    has_ai_summary = False
    try:
        extracted = _extract_sub_risks(result_json) if isinstance(result_json, dict) else []
        risk_items = len(extracted)
        risk_categories = len(
            {
                str(x.get("category", "") or "").strip()
                for x in extracted
                if str(x.get("category", "") or "").strip()
            }
        )
        has_ai_summary = bool(str((result_json or {}).get("ai_summary", "") or "").strip()) if isinstance(result_json, dict) else False
    except Exception:
        risk_items = 0
        risk_categories = 0
        has_ai_summary = False

    if USE_NEW_LAYOUT:
        # Resolve directory layout via the new index. PDFs are not yet
        # supported by the new layout; fall back to legacy keys for them
        # so existing PDF flows keep working untouched.
        company_dir = _new_layout_company_dir(company, ticker)
        if ext == "html" and company_dir:
            ft_token = _filing_type_token(filing_type)
            quarter_suffix = f"_Q{filing_quarter}" if filing_type == "10-Q" and filing_quarter > 0 else ""
            base_prefix = NEW_10Q_FILINGS_PREFIX if filing_type == "10-Q" else NEW_FILINGS_PREFIX
            index_key = NEW_10Q_INDEX_KEY if filing_type == "10-Q" else NEW_INDEX_KEY
            html_key = f"{base_prefix}/{industry}/{company_dir}/{year}_{ft_token}{quarter_suffix}.html"
            json_key = f"{base_prefix}/{industry}/{company_dir}/{year}_{ft_token}{quarter_suffix}_risks.json"
            _write_s3_bytes(html_key, file_bytes)
            _write_s3_bytes(
                json_key,
                json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
            )

            rid = _new_layout_record_id(company_dir, year, filing_type, filing_quarter)
            new_index_doc = _load_new_layout_10q_index_doc() if filing_type == "10-Q" else _load_new_layout_index_doc()
            if not isinstance(new_index_doc, dict) or not new_index_doc:
                new_index_doc = {
                    "version": 1,
                    "schema": {
                        "html_key": f"{base_prefix}/<industry>/<company_dir>/<year>_{ft_token}{quarter_suffix}.html",
                        "json_key": f"{base_prefix}/<industry>/<company_dir>/<year>_{ft_token}{quarter_suffix}_risks.json",
                    },
                    "industries": {},
                }
            _upsert_new_layout_index(
                new_index_doc,
                industry_dir=industry, company_dir=company_dir,
                company=company, ticker=ticker,
                year=year, html_key=html_key, json_key=json_key,
                sub_risk_count=int(risk_items), filing_type=filing_type, filing_quarter=filing_quarter,
                extracted_at=datetime.now(timezone.utc).isoformat(),
            )
            _write_s3_bytes(index_key, json.dumps(new_index_doc, indent=2, ensure_ascii=False, default=str).encode("utf-8"))

            return {
                "record_id": rid,
                "company": company,
                "ticker": ticker,
                "industry": industry,
                "year": year,
                "filing_type": filing_type,
                "filing_quarter": filing_quarter,
                "file_ext": ext,
                "file_key": html_key,
                "result_key": json_key,
                "risk_items": int(risk_items),
                "risk_categories": int(risk_categories),
                "has_ai_summary": bool(has_ai_summary),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        # PDF or no resolvable directory → fall through to legacy write.

    safe = _sanitize_company(company)
    sid = uuid.uuid4().hex[:4]
    quarter_token = f"_Q{filing_quarter}" if filing_type == "10-Q" and filing_quarter > 0 else ""
    rid = f"{safe}_{year}_{_sanitize_filing_type(filing_type)}{quarter_token}_{sid}"
    if ext == "pdf":
        data_key = f"{PDF_PREFIX}/{rid}.{ext}"
        result_key = f"{RESULTS_PREFIX}/{rid}.json"
    else:
        if filing_type == "10-Q":
            company_dir = _new_layout_company_dir(company, ticker) or _sanitize_company(company)
            data_key = _legacy_10q_html_key(
                industry=industry,
                company_dir=company_dir,
                year=year,
                filing_quarter=filing_quarter,
            )
            result_key = _legacy_10q_result_key(
                industry=industry,
                company_dir=company_dir,
                year=year,
                filing_quarter=filing_quarter,
            )
        else:
            data_key = f"{_legacy_html_prefix_for_filing_type(filing_type)}/{rid}.{ext}"
            result_key = f"{RESULTS_PREFIX}/{rid}.json"

    _write_s3_bytes(data_key, file_bytes)
    _write_s3_bytes(
        result_key,
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    record = {
        "record_id": rid,
        "company": company,
        "ticker": ticker,
        "industry": industry,
        "year": year,
        "filing_type": filing_type,
        "filing_quarter": filing_quarter,
        "file_ext": ext,
        "file_key": data_key,
        "result_key": result_key,
        "risk_items": int(risk_items),
        "risk_categories": int(risk_categories),
        "has_ai_summary": bool(has_ai_summary),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    index.append(record)
    _save_index(index)
    return record


def _new_layout_company_dir(company: str, ticker: str) -> str:
    """Look up the canonical S3 directory name for `company` in the new
    layout. Tries the existing index first (so duplicate uploads land in
    the same folder); falls back to a synthesized `<Company>_<TICKER>`
    name and lastly to the legacy `_sanitize_company` value."""
    company = str(company or "").strip()
    ticker = _normalize_ticker(ticker)
    if not company:
        return ""
    new_doc = _load_new_layout_index_doc()
    industries = new_doc.get("industries", {}) if isinstance(new_doc, dict) else {}
    if isinstance(industries, dict):
        for ind in industries.values():
            if not isinstance(ind, dict):
                continue
            for company_dir, block in ind.items():
                if not isinstance(block, dict):
                    continue
                if str(block.get("company", "")).strip() == company:
                    return str(company_dir)
                if ticker and _normalize_ticker(block.get("ticker", "")) == ticker:
                    return str(company_dir)
    safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", company.replace(" ", "_")).strip("_")
    if ticker:
        return f"{safe_name}_{ticker}"
    return safe_name or _sanitize_company(company)


def _upsert_new_layout_index(
    index_doc: dict,
    *,
    industry_dir: str,
    company_dir: str,
    company: str,
    ticker: str,
    year: int,
    html_key: str,
    json_key: str,
    sub_risk_count: int,
    filing_type: str,
    filing_quarter: int = 0,
    extracted_at: str,
    cik: str = "",
) -> None:
    filing_type = _canonical_filing_type(filing_type)
    filing_quarter = _coerce_filing_quarter(filing_quarter, filing_type)
    industries = index_doc.setdefault("industries", {})
    industry_block = industries.setdefault(industry_dir, {})
    company_block = industry_block.setdefault(company_dir, {
        "company": company,
        "ticker": _normalize_ticker(ticker),
        "industry": industry_dir,
        "cik": cik,
        "filings": [],
    })
    if company and not company_block.get("company"):
        company_block["company"] = company
    if ticker and not company_block.get("ticker"):
        company_block["ticker"] = _normalize_ticker(ticker)
    if cik and not company_block.get("cik"):
        company_block["cik"] = cik

    filings = company_block.setdefault("filings", [])
    next_filings: List[dict] = []
    for f in filings:
        try:
            same_year = int(f.get("year") or 0) == int(year)
        except Exception:
            same_year = False
        same_type = _canonical_filing_type(f.get("filing_type")) == filing_type
        same_quarter = True
        if filing_type == "10-Q":
            same_quarter = (
                _coerce_filing_quarter(f.get("filing_quarter"), f.get("filing_type"))
                == filing_quarter
            )
        if same_year and same_type and same_quarter:
            continue
        next_filings.append(f)
    filings[:] = next_filings
    filings.append({
        "year": int(year),
        "filing_type": filing_type,
        "filing_quarter": filing_quarter,
        "html_key": html_key,
        "json_key": json_key,
        "sub_risk_count": int(sub_risk_count or 0),
        "extracted_at": str(extracted_at or ""),
    })
    filings.sort(key=lambda r: int(r.get("year") or 0))


def _load_agent_reports() -> List[dict]:
    now = time.time()
    cached_ts = float(_AGENT_REPORTS_CACHE.get("ts", 0.0) or 0.0)
    cached_data = _AGENT_REPORTS_CACHE.get("data", [])
    if (now - cached_ts) <= _AGENT_REPORTS_CACHE_TTL_SECONDS and isinstance(cached_data, list):
        return [r for r in cached_data if isinstance(r, dict)]

    reports: List[dict] = []
    try:
        for key in _list_s3_keys(f"{AGENT_PREFIX}/"):
            if not key.endswith(".json"):
                continue
            payload = _json_from_bytes(_read_s3_bytes(key), None)
            if isinstance(payload, dict):
                reports.append(payload)
    except Exception:
        return []
    _AGENT_REPORTS_CACHE["ts"] = now
    _AGENT_REPORTS_CACHE["data"] = reports
    return reports


def _normalize_title(value: Any) -> str:
    txt = str(value or "").strip()
    return " ".join(txt.lower().split())


FIXED_RISK_CATEGORIES: List[str] = [
    "Strategy & Market",
    "Operations & Supply Chain",
    "Financial & Liquidity",
    "Legal & Regulatory",
    "Technology & Cybersecurity",
    "People & Governance",
    "ESG & Sustainability",
    "Capital Markets",
    "General & Other",
]

_RISK_CATEGORY_KEYWORDS: Dict[str, List[tuple[str, int]]] = {
    "Capital Markets": [
        ("common stock", 3), ("stockholder", 3), ("shareholder", 2),
        ("market price of our", 3), ("dividend", 3), ("dilution", 3),
        ("equity offering", 3), ("ownership of our stock", 3),
        ("public offering", 2), ("listing", 1),
    ],
    "Financial & Liquidity": [
        ("liquidity", 3), ("cash flow", 3), ("debt", 2), ("credit risk", 3),
        ("interest rate", 3), ("refinancing", 3), ("impairment", 3),
        ("foreign exchange", 3), ("currency", 2), ("solvency", 3),
        ("capital resources", 3), ("inflation", 2), ("hedging", 2),
    ],
    "Legal & Regulatory": [
        ("regulation", 3), ("regulatory", 3), ("compliance", 2),
        ("litigation", 3), ("antitrust", 3), ("sanction", 3), ("bribery", 3),
        ("intellectual property", 3), ("patent", 2),
        ("data privacy law", 3), ("gdpr", 3), ("ccpa", 3),
        ("tax-related", 2), ("status as a reit", 3),
        # P4: regulators frequently appear with "requirement" / "action" /
        # "investigation"; pure "regulation" alone is not enough signal.
        ("regulatory requirement", 2), ("regulatory action", 2),
        ("regulatory investigation", 2), ("government investigation", 2),
        ("legal proceeding", 2),
    ],
    "Technology & Cybersecurity": [
        ("cybersecurity", 3), ("cyber attack", 3), ("cyber-attack", 3),
        ("data breach", 3),
        ("information security", 3), ("ransomware", 3), ("system outage", 3),
        ("it system", 3), ("personal information", 2),
        ("artificial intelligence", 2), ("generative ai", 3),
        # P4: keyword table missed bare "technology" + common SEC phrasings.
        ("technology", 1), ("technology disruption", 3),
        ("information system", 2), ("digital platform", 3),
        ("digital service", 2), ("data integrity", 2),
        ("cyber incident", 3), ("cybersecurity incident", 3),
        ("network security", 3), ("software vulnerability", 3),
        ("unauthorized access", 3), ("access to our information", 2),
        ("hacker", 3), ("malicious", 1),
        ("data security", 3), ("data privacy", 2),
    ],
    "Operations & Supply Chain": [
        ("supply chain", 3), ("supplier", 3), ("procurement", 2),
        ("manufacturing", 2), ("logistics", 2), ("distribution", 2),
        ("inventory", 2), ("business continuity", 3),
        ("single source", 3), ("contract manufacturer", 3),
        # P4: retail / consumer 10-K product-quality/safety phrasing.
        ("product safety", 3), ("product quality", 3),
        ("product recall", 3), ("production disruption", 3),
        ("merchandise availability", 3), ("third-party manufacturer", 3),
        ("operational disruption", 2),
        # SEC writers often invert the phrase ("safety of our products").
        ("safety of products", 3), ("quality of products", 3),
        ("safety of our products", 3), ("quality of our products", 3),
        ("product safety or quality", 3), ("product quality or safety", 3),
    ],
    "People & Governance": [
        ("workforce", 3), ("union", 3), ("human capital", 3),
        ("talent", 3), ("retention of key", 3),
        ("internal control", 3), ("succession", 2), ("board of directors", 3),
        ("labor union", 3), ("work stoppage", 3),
        ("key personnel", 2), ("executive officer", 1),
    ],
    "ESG & Sustainability": [
        ("climate change", 3), ("greenhouse gas", 3), ("carbon emissions", 3),
        ("environmental regulation", 3), ("esg", 3),
        ("sustainability", 2), ("renewable", 2),
        ("emission", 2), ("carbon", 1), ("water scarcity", 2),
        ("environmental impact", 2),
    ],
    "Strategy & Market": [
        ("competition", 3), ("competitive landscape", 3),
        ("market share", 3), ("pricing pressure", 3),
        ("customer concentration", 3), ("new entrants", 2),
        ("brand", 2), ("reputation", 2), ("geopolitical", 3),
        ("macroeconomic", 3),
        ("customer demand", 2), ("consumer preference", 2),
        ("product launch", 2),
    ],
}


# P4: tie-breaker rules. When two buckets land within `tolerance` of each other
# in raw score, look for a strong phrase in title to decide the winner.
# `(winner, loser, [phrases])`: if any phrase appears in title or labels, the
# winner is preferred. Order matters — first match wins.
_RISK_CATEGORY_TIEBREAKERS: List[tuple[str, str, List[str]]] = [
    # cyber phrasing should beat regulatory / legal
    ("Technology & Cybersecurity", "Legal & Regulatory", [
        "cyber-attack", "cyber attack", "cybersecurity", "data breach",
        "information security", "ransomware", "cyber incident",
    ]),
    # supply chain / operations should beat people&gov when both appear
    ("Operations & Supply Chain", "People & Governance", [
        "supplier", "supply chain", "single source", "third-party manufacturer",
        "product safety", "product quality",
    ]),
    # ESG should beat regulatory when climate / emission language present
    ("ESG & Sustainability", "Legal & Regulatory", [
        "climate", "emission", "greenhouse", "renewable", "carbon",
    ]),
    # cyber should beat strategy/market when both touched
    ("Technology & Cybersecurity", "Strategy & Market", [
        "cyber-attack", "cybersecurity", "data breach", "ransomware",
    ]),
    # operations should beat strategy/market when product-quality phrasing
    ("Operations & Supply Chain", "Strategy & Market", [
        "product safety", "product quality", "product recall",
        "safety of products", "quality of products",
        "safety of our products", "quality of our products",
    ]),
    # operations should beat legal when product safety/quality phrasing
    ("Operations & Supply Chain", "Legal & Regulatory", [
        "product safety", "product quality", "product recall",
        "safety of products", "quality of products",
        "safety of our products", "quality of our products",
    ]),
    # cyber should beat operations when unauthorized access / breach phrasing
    # appears alongside supplier mentions (Boeing-style title)
    ("Technology & Cybersecurity", "Operations & Supply Chain", [
        "unauthorized access", "data breach", "cyber-attack",
        "cyber attack", "cybersecurity", "ransomware",
    ]),
]


def _apply_category_tiebreakers(
    scores: Dict[str, int],
    full_text: str,
    title_lower: str,
) -> Dict[str, int]:
    """Adjust `scores` so each tie-breaker can flip the ranking when a strong
    phrase is present. When the strong phrase is in the haystack we guarantee
    the winner's score strictly outranks the loser's by at least 1 (preventing
    alphabetical-tie wins for the wrong bucket)."""
    haystack = " ".join(s for s in [title_lower, full_text] if s)
    boosted = dict(scores)
    for winner, loser, phrases in _RISK_CATEGORY_TIEBREAKERS:
        for phrase in phrases:
            if phrase in haystack:
                w = boosted.get(winner, 0)
                l = boosted.get(loser, 0)
                if w <= l:
                    boosted[winner] = l + 2
                else:
                    boosted[winner] = w + 1
                break
    return boosted


def _normalize_risk_category(category: Any, title: Any = "", labels: Optional[List[Any]] = None) -> tuple[str, int]:
    cat_text = str(category or "").strip()
    title_text = str(title or "").strip()
    label_text = " ".join([str(x or "").strip() for x in (labels or []) if str(x or "").strip()])
    full_text = " ".join([cat_text, title_text, label_text]).strip().lower()
    if not full_text:
        return "General & Other", 0

    scores: Dict[str, int] = {k: 0 for k in FIXED_RISK_CATEGORIES}
    # Track the heaviest single keyword weight that contributed to each bucket.
    # Used downstream to detect "all weight-1" wins — those should fall through
    # to the LLM fallback even when raw score happens to clear the threshold.
    max_weights: Dict[str, int] = {k: 0 for k in FIXED_RISK_CATEGORIES}
    cat_lower = cat_text.lower()
    title_lower = title_text.lower()

    def _add_match_points(target: str, phrase: str, weight: int) -> None:
        bumped = False
        if phrase in full_text:
            scores[target] = scores.get(target, 0) + int(weight)
            bumped = True
        if phrase in cat_lower:
            scores[target] = scores.get(target, 0) + int(weight)
            bumped = True
        if bumped and int(weight) > max_weights.get(target, 0):
            max_weights[target] = int(weight)

    for target, weighted in _RISK_CATEGORY_KEYWORDS.items():
        for phrase, weight in weighted:
            _add_match_points(target, phrase, weight)

    # P4: tie-breakers nudge the right bucket up when a strong phrase appears.
    scores = _apply_category_tiebreakers(scores, full_text, title_lower)

    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_cat, best_score = ranked[0]
    # When the best bucket only got there from weight-1 keyword hits we have
    # no strong signal — surface that by returning a negative-coded score so
    # the caller's `score < 2` check trips the LLM fallback.
    if best_score >= 1 and max_weights.get(best_cat, 0) <= 1 and best_score < 4:
        # weight-1 wins are demoted to score 1 so caller's threshold catches them.
        return best_cat, 1
    if best_score >= 1:
        return best_cat, int(best_score)
    return "General & Other", 0


_LLM_CLASSIFY_CACHE: Dict[str, str] = {}


def _has_bedrock_runtime_credentials() -> bool:
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        return True
    if os.getenv("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI") or os.getenv("AWS_CONTAINER_CREDENTIALS_FULL_URI"):
        return True
    return False


def _bucket_from_source_heading(category: Any) -> str:
    """Map extractor-provided source headings to dashboard buckets.

    This acts as a conservative anchor when per-title keyword scoring is weak.
    It prevents 10-Q records from collapsing into a single dashboard bucket
    due to sparse title-level signals.
    """
    low = str(category or "").strip().lower()
    if not low:
        return ""

    if any(k in low for k in ("legal", "regulatory", "compliance", "antitrust", "litigation", "law")):
        return "Legal & Regulatory"
    if any(k in low for k in ("cyber", "technology", "information security", "data privacy", "data security")):
        return "Technology & Cybersecurity"
    if any(k in low for k in ("strategy", "market", "commercial", "competition", "customer demand")):
        return "Strategy & Market"
    if any(k in low for k in ("operations", "operational", "supply chain", "supplier", "manufacturing", "logistics")):
        return "Operations & Supply Chain"
    if any(k in low for k in ("financial", "liquidity", "capital resources", "credit", "debt", "cash flow")):
        return "Financial & Liquidity"
    if any(k in low for k in ("governance", "workforce", "human capital", "board", "talent", "labor")):
        return "People & Governance"
    if any(k in low for k in ("esg", "sustainability", "climate", "environmental", "carbon")):
        return "ESG & Sustainability"
    if any(k in low for k in ("capital markets", "shareholder", "stockholder", "common stock", "dividend")):
        return "Capital Markets"
    return ""


def _is_generic_source_category(category: Any) -> bool:
    low = str(category or "").strip().lower()
    if not low:
        return True
    generic_tokens = {
        "risk factors",
        "risks",
        "general risks",
        "general risk",
        "general",
        "other",
        "other risks",
    }
    return low in generic_tokens


def _resolve_dashboard_bucket(
    *,
    original_category: str,
    title: str,
    labels: List[str],
    pre_dashboard: str = "",
) -> str:
    """Stable dashboard bucket resolver with source-heading anchoring.

    Goal: keep 10-Q blocks from collapsing into a single Legal bucket when
    the extractor already produced meaningful thematic block headings.
    """
    if pre_dashboard in FIXED_RISK_CATEGORIES:
        return pre_dashboard

    heading_bucket = _bucket_from_source_heading(original_category)
    mapped, score = _normalize_risk_category(original_category, title, labels)

    # Strong anchor: when source block heading is non-generic and explicitly
    # maps to a dashboard bucket, prefer it unless title-level evidence is
    # very strong in another direction.
    if heading_bucket and not _is_generic_source_category(original_category):
        if mapped == heading_bucket:
            return mapped
        if score <= 4:
            return heading_bucket
        # For very strong signals (score>=5), keep title mapping.
        return mapped

    if score < 2:
        return _classify_with_llm_fallback(original_category, title, labels)
    return mapped


def _json_obj_from_text(text: str) -> dict:
    raw = str(text or "").strip().replace("```json", "").replace("```", "").strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    left = raw.find("{")
    right = raw.rfind("}")
    if left >= 0 and right > left:
        try:
            obj = json.loads(raw[left : right + 1])
            return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    return {}


def _classify_with_llm_fallback(category: str, title: str, labels: List[str]) -> str:
    cache_key = (str(category or "") + "||" + str(title or ""))[:300]
    if cache_key in _LLM_CLASSIFY_CACHE:
        return _LLM_CLASSIFY_CACHE[cache_key]

    if not _has_bedrock_runtime_credentials():
        _LLM_CLASSIFY_CACHE[cache_key] = "General & Other"
        return "General & Other"

    bucket_list = "\n".join(f"- {c}" for c in FIXED_RISK_CATEGORIES)
    prompt = f"""You map an SEC filing risk factor into ONE of these 9 dashboard categories:
{bucket_list}

Risk source category (LLM-named): {category!r}
Risk title: {title!r}
Labels: {labels!r}

Return ONLY a JSON object: {{"bucket": "<exactly one of the 9 names>"}}."""
    try:
        invoke = _get_extraction_llm_invoke()
        raw = invoke(prompt, 60)
        bucket = str(_json_obj_from_text(raw).get("bucket", "")).strip()
        if bucket in FIXED_RISK_CATEGORIES:
            _LLM_CLASSIFY_CACHE[cache_key] = bucket
            return bucket
        for candidate in FIXED_RISK_CATEGORIES:
            if candidate in str(raw or ""):
                _LLM_CLASSIFY_CACHE[cache_key] = candidate
                return candidate
    except Exception:
        pass

    _LLM_CLASSIFY_CACHE[cache_key] = "General & Other"
    return "General & Other"


def _extract_sub_risks(result: dict) -> List[dict]:
    out: List[dict] = []
    for cat_block in result.get("risks", []) if isinstance(result, dict) else []:
        original_category = str(cat_block.get("category", "Unknown") or "Unknown")
        for sr in cat_block.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = sr.get("labels", []) if isinstance(sr.get("labels"), list) else []
                pre_dashboard = str(sr.get("dashboard_category", "") or "").strip()
                pre_original = str(sr.get("original_category", "") or "").strip()
            else:
                title = str(sr or "").strip()
                labels = []
                pre_dashboard = ""
                pre_original = ""
            if not title:
                continue
            mapped_category = _resolve_dashboard_bucket(
                original_category=original_category,
                title=title,
                labels=labels,
                pre_dashboard=pre_dashboard,
            )
            out.append(
                {
                    "category": mapped_category,
                    "dashboard_category": mapped_category,
                    "original_category": pre_original or original_category,
                    "title": title,
                    "labels": labels,
                }
            )
    return out


def _annotate_dashboard_category(risks_blocks: list) -> list:
    for block in risks_blocks if isinstance(risks_blocks, list) else []:
        if not isinstance(block, dict):
            continue
        original_category = str(block.get("category", "") or "").strip() or "Unknown"
        new_subs = []
        for sr in block.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = sr.get("labels", []) if isinstance(sr.get("labels"), list) else []
                if not title:
                    continue
                mapped = str(sr.get("dashboard_category", "") or "").strip()
                mapped = _resolve_dashboard_bucket(
                    original_category=original_category,
                    title=title,
                    labels=labels,
                    pre_dashboard=mapped,
                )
                sr_out = dict(sr)
                sr_out["title"] = title
                sr_out["labels"] = labels
                sr_out["original_category"] = str(sr.get("original_category", "") or "").strip() or original_category
                sr_out["dashboard_category"] = mapped
                new_subs.append(sr_out)
            else:
                title = str(sr or "").strip()
                if not title:
                    continue
                mapped = _resolve_dashboard_bucket(
                    original_category=original_category,
                    title=title,
                    labels=[],
                    pre_dashboard="",
                )
                new_subs.append(
                    {
                        "title": title,
                        "labels": [],
                        "original_category": original_category,
                        "dashboard_category": mapped,
                    }
                )
        block["sub_risks"] = new_subs
    return risks_blocks if isinstance(risks_blocks, list) else []


def _result_with_dashboard_categories(result: dict) -> dict:
    if not isinstance(result, dict):
        return result
    risks = result.get("risks")
    if not isinstance(risks, list):
        return result
    cloned = dict(result)
    cloned["risks"] = _annotate_dashboard_category([dict(block) if isinstance(block, dict) else block for block in risks])
    return cloned


def _generate_agent_priority_report(company: str, year: int, risks: list) -> tuple[Optional[dict], str]:
    try:
        run_agent = _get_run_agent()
    except Exception as exc:
        return None, f"Agent runtime unavailable: {type(exc).__name__}: {exc}"

    try:
        report = run_agent(
            user_query="Prioritize all risks and identify the top 5 most critical threats",
            company=str(company or "").strip(),
            year=int(year or 0),
            risks=risks if isinstance(risks, list) else [],
            compare_data=None,
        )
    except Exception as exc:
        return None, f"Agent run failed: {type(exc).__name__}: {exc}"

    if not isinstance(report, dict):
        return None, "Agent report format is invalid."
    return report, ""


def _append_agent_report_file(record: dict, report: dict) -> None:
    if not isinstance(record, dict) or not isinstance(report, dict):
        return
    company = str(record.get("company", "") or "").strip()
    filing_type = str(record.get("filing_type", "10-K") or "10-K").strip() or "10-K"
    year = _to_int_safe(record.get("year"), 0)
    record_id = str(record.get("record_id", "") or "").strip()
    if not company or year <= 0 or not record_id:
        return
    payload = {
        **report,
        "company": report.get("company") or company,
        "year": _to_int_safe(report.get("year"), year),
        "filing_type": report.get("filing_type") or filing_type,
        "record_id": record_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    key = (
        f"{AGENT_PREFIX}/"
        f"{_sanitize_company(company)}_{year}_{_sanitize_filing_type(filing_type)}_{record_id}_{uuid.uuid4().hex[:6]}.json"
    )
    _write_s3_bytes(key, json.dumps(payload, indent=2, default=str, ensure_ascii=False).encode("utf-8"))


def _ensure_record_priority(rec: dict, force: bool = False) -> tuple[bool, str]:
    if not isinstance(rec, dict):
        return False, "Invalid record payload."
    record_id = str(rec.get("record_id", "") or "").strip()
    if not record_id:
        return False, "Missing record_id."

    result = _load_result(record_id)
    if not isinstance(result, dict):
        return False, "Result JSON not found."

    existing_counts = _extract_priority_counts_from_result(result)
    if not force and int(existing_counts.get("total", 0) or 0) > 0:
        return False, "Priority already exists."

    risks = result.get("risks", []) if isinstance(result.get("risks"), list) else []
    if not risks:
        return False, "No risks available to score."

    company = str(rec.get("company", "") or "").strip() or str((result.get("company_overview") or {}).get("company", "") or "")
    year = _to_int_safe(rec.get("year"), 0) or _to_int_safe((result.get("company_overview") or {}).get("year"), 0)
    if not company or year <= 0:
        return False, "Missing company/year context."

    report, err = _generate_agent_priority_report(company=company, year=year, risks=risks)
    if not report:
        return False, err or "Agent scoring failed."

    result["agent_report"] = report
    _write_s3_bytes(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    try:
        _append_agent_report_file(rec, report)
    except Exception:
        pass
    return True, ""


def _ensure_priority_for_all_records(force: bool = False, limit: int = 0) -> dict:
    index = _load_index()
    if not index:
        return {"ok": True, "processed": 0, "updated": 0, "skipped": 0, "errors": []}

    records = sorted(index, key=lambda r: str(r.get("created_at", "")), reverse=True)
    max_n = int(limit or 0)
    if max_n > 0:
        records = records[:max_n]

    updated = 0
    skipped = 0
    errors: List[dict] = []
    for rec in records:
        success, reason = _ensure_record_priority(rec, force=force)
        if success:
            updated += 1
            continue
        # classify soft skips vs hard errors
        low = str(reason or "").lower()
        if any(k in low for k in ("already exists", "no risks", "not found")):
            skipped += 1
        else:
            errors.append({"record_id": str(rec.get("record_id", "") or ""), "reason": reason or "Unknown error"})

    return {
        "ok": True,
        "processed": len(records),
        "updated": updated,
        "skipped": skipped,
        "errors": errors[:30],
    }


def _manual_extract_result(
    *,
    file_bytes: bytes,
    file_name: str,
    company: str,
    industry: str,
    year: int,
    filing_type: str,
    ticker: str = "",
) -> tuple[Optional[dict], str]:
    if (
        extract_item1_overview_bedrock is None
        or extract_item1a_risks_bedrock is None
        or extract_item1_overview_from_text is None
        or extract_item1a_risks_from_text is None
        or extract_text_from_pdf is None
    ):
        return None, "Extraction pipeline is unavailable in runtime."

    company_name = str(company or "").strip()
    if not company_name:
        return None, "Company name is required."

    is_pdf = str(file_name or "").strip().lower().endswith(".pdf")
    industry_name = str(industry or "Other").strip() or "Other"
    ft = _canonical_filing_type(filing_type)
    yy = int(year or 0)
    tkr = _normalize_ticker(ticker)

    def _count_sub_risks(blocks: Any) -> int:
        total = 0
        for b in blocks if isinstance(blocks, list) else []:
            if not isinstance(b, dict):
                continue
            for sr in b.get("sub_risks", []) or []:
                if isinstance(sr, dict):
                    title = str(sr.get("title", "") or "").strip()
                else:
                    title = str(sr or "").strip()
                if title:
                    total += 1
        return total

    def _is_sparse_or_generic_10q(blocks: Any) -> bool:
        if not isinstance(blocks, list) or not blocks:
            return True
        cnt = _count_sub_risks(blocks)
        first_cat = str((blocks[0] or {}).get("category", "") if isinstance(blocks[0], dict) else "").strip().lower()
        generic_cat = first_cat in {"risk factors", "general risks", "general", "other", "risks"}
        # 10-Q Item 1A often says "no material changes" and gives very few lines.
        if cnt <= 3:
            return True
        if len(blocks) == 1 and generic_cat and cnt <= 12:
            return True
        # Sparse 10-Q extraction tends to underrepresent enterprise risk landscape.
        if cnt < 6:
            return True
        return False

    def _dashboard_distribution(blocks: Any) -> tuple[int, Dict[str, int]]:
        try:
            flat = _extract_sub_risks({"risks": blocks}) if isinstance(blocks, list) else []
        except Exception:
            flat = []
        counts: Dict[str, int] = {}
        for item in flat:
            if not isinstance(item, dict):
                continue
            b = str(item.get("dashboard_category", "") or item.get("category", "") or "").strip() or "General & Other"
            counts[b] = counts.get(b, 0) + 1
        return len(flat), counts

    def _is_legal_collapsed_10q(blocks: Any, incremental_info: Any) -> bool:
        if not isinstance(incremental_info, dict) or not incremental_info.get("has_incremental_updates"):
            return False
        total, counts = _dashboard_distribution(blocks)
        if total < 6 or not counts:
            return False
        uniq = len(counts)
        top_bucket, top_count = max(counts.items(), key=lambda kv: kv[1])
        top_share = float(top_count) / float(total or 1)
        if uniq <= 1:
            return True
        if top_bucket == "Legal & Regulatory" and top_share >= 0.75:
            return True
        return False

    def _delta_bucket_hint(title: str) -> str:
        low = str(title or "").strip().lower()
        if not low:
            return ""
        # App Store / business-terms / partner relationships are primarily
        # market-strategy risks even when discussed in legal contexts.
        if any(k in low for k in (
            "app store", "business terms", "fee structure", "distribution",
            "payment processing", "commercial relationship", "business partner",
            "search services", "default search", "customer demand",
        )):
            return "Strategy & Market"
        # Platform and developer-surface changes are product/technology risks.
        if any(k in low for k in (
            "ios", "ipados", "safari", "api", "developer", "operating system",
            "technology", "machine learning", "artificial intelligence",
        )):
            return "Technology & Cybersecurity"
        # Supply/ops style phrasing.
        if any(k in low for k in ("supply chain", "operations", "distribution channel", "reseller")):
            return "Operations & Supply Chain"
        return ""

    def _rebalance_10q_legal_collapse(blocks: list, incremental_info: dict) -> list:
        if not isinstance(blocks, list):
            return blocks
        if not _is_legal_collapsed_10q(blocks, incremental_info):
            return blocks
        # Re-map titles with strong 10-Q delta cues away from Legal bucket.
        for block in blocks:
            if not isinstance(block, dict):
                continue
            for sr in block.get("sub_risks", []) or []:
                if not isinstance(sr, dict):
                    continue
                current_bucket = str(sr.get("dashboard_category", "") or "").strip()
                if current_bucket != "Legal & Regulatory":
                    continue
                title = str(sr.get("title", "") or "").strip()
                hint = _delta_bucket_hint(title)
                if hint in FIXED_RISK_CATEGORIES and hint != "Legal & Regulatory":
                    sr["dashboard_category"] = hint
        return blocks

    try:
        item1a_raw_text = ""
        if is_pdf:
            pdf_text = extract_text_from_pdf(file_bytes)
            if not pdf_text:
                return None, "Textract could not extract text from this PDF."
            overview = extract_item1_overview_from_text(pdf_text, company_name, industry_name)
            risks = extract_item1a_risks_from_text(pdf_text)
            item1a_raw_text = str(pdf_text or "")
        else:
            # Keep both pipelines while removing user-facing mode choice:
            # HTML defaults to AI-enhanced with internal fallback to standard.
            overview = extract_item1_overview_bedrock(file_bytes, company_name, industry_name)
            risks = extract_item1a_risks_bedrock(file_bytes, company_name, ft)
            if locate_item1a is not None:
                try:
                    item1a_raw_text = str(locate_item1a(file_bytes, filing_type=ft) or "")
                except Exception:
                    item1a_raw_text = ""
    except Exception as exc:
        return None, f"Extraction failed: {type(exc).__name__}: {exc}"

    if not risks:
        return None, "Could not extract risks from Item 1A."

    incremental_update = {}
    if ft == "10-Q":
        incremental_update = _extract_10q_incremental_update(item1a_raw_text)

    if isinstance(risks, list):
        risks = _annotate_dashboard_category(risks)
        if ft == "10-Q" and isinstance(incremental_update, dict):
            risks = _rebalance_10q_legal_collapse(risks, incremental_update)

    overview = dict(overview or {})
    overview["year"] = yy
    overview["filing_type"] = ft
    overview["company"] = overview.get("company") or company_name
    overview["industry"] = overview.get("industry") or industry_name

    result_payload = {"company_overview": overview, "risks": risks}
    if ft == "10-Q":
        result_payload["incremental_10q_update"] = incremental_update
        result_payload["has_incremental_risk_updates"] = bool(
            isinstance(incremental_update, dict) and incremental_update.get("has_incremental_updates")
        )
    return result_payload, ""


def _auto_fetch_and_extract(
    *,
    company: str,
    ticker: str,
    industry: str,
    filing_type: str,
    start_year: int,
    end_year: int,
) -> dict:
    ft = _canonical_filing_type(filing_type)
    html_downloader = download_10q_html_for_company_year if ft == "10-Q" else download_10k_html_for_company_year
    if html_downloader is None:
        return {"ok": False, "error": "SEC auto-fetch is unavailable in runtime."}

    comp = str(company or "").strip()
    tk = str(ticker or "").strip().upper()
    ind = str(industry or "Other").strip() or "Other"
    if _normalize_ticker(tk) == "AAPL":
        ind = "Technology"
    sy = int(start_year or 0)
    ey = int(end_year or 0)
    if not comp:
        return {"ok": False, "error": "Company name is required."}
    if sy <= 0 or ey <= 0 or sy > ey:
        return {"ok": False, "error": "Invalid year range."}

    successes: List[dict] = []
    skipped: List[dict] = []
    for yy in range(sy, ey + 1):
        try:
            html_bytes, sec_meta, sec_err = html_downloader(comp, yy, tk)
        except Exception as exc:
            skipped.append({"year": yy, "reason": f"SEC request failed: {type(exc).__name__}: {exc}"})
            continue

        if not html_bytes:
            skipped.append({"year": yy, "reason": sec_err or f"Could not fetch {ft} HTML from SEC EDGAR."})
            continue

        result, extract_err = _manual_extract_result(
            file_bytes=html_bytes,
            file_name=f"{comp}_{yy}.html",
            company=comp,
            industry=ind,
            year=yy,
            filing_type=ft,
            ticker=tk,
        )
        if not result:
            skipped.append({"year": yy, "reason": extract_err or "Extraction failed."})
            continue

        risks_for_agent = result.get("risks", []) if isinstance(result.get("risks"), list) else []
        if risks_for_agent:
            agent_report, agent_err = _generate_agent_priority_report(company=comp, year=yy, risks=risks_for_agent)
            if isinstance(agent_report, dict):
                result["agent_report"] = agent_report
            elif agent_err:
                result["agent_report_error"] = agent_err

        result["source"] = "sec_edgar_auto_fetch"
        filing_quarter = _infer_filing_quarter(sec_meta, ft)
        if ft == "10-Q" and filing_quarter > 0:
            result["filing_quarter"] = filing_quarter
        result["sec_meta"] = {
            **(sec_meta if isinstance(sec_meta, dict) else {}),
            "auto_fetch": True,
            "ticker": tk,
            "filing_quarter": filing_quarter,
            "filing_url": build_filing_html_url(sec_meta) if build_filing_html_url and isinstance(sec_meta, dict) else "",
        }

        try:
            rec = _add_record(
                company=comp,
                industry=ind,
                year=yy,
                filing_type=ft,
                ticker=tk,
                file_bytes=html_bytes,
                file_ext="html",
                result_json=result,
                filing_quarter=filing_quarter,
            )
            if tk:
                _upsert_company_ticker(comp, tk)
            if isinstance(result.get("agent_report"), dict):
                try:
                    _append_agent_report_file(rec, result.get("agent_report"))
                except Exception:
                    pass
            successes.append({"year": yy, "record": _record_summary(rec, include_result=True), "result": result})
        except Exception as exc:
            skipped.append({"year": yy, "reason": f"Save failed: {type(exc).__name__}: {exc}"})

    return {
        "ok": True,
        "count": len(successes),
        "successes": successes,
        "skipped": skipped,
    }


def _find_record(company: str, year: int) -> Optional[dict]:
    comp = str(company or "").strip().lower()
    yy = int(year or 0)
    if not comp or not yy:
        return None
    candidates = []
    for rec in _load_index():
        if str(rec.get("company", "")).strip().lower() != comp:
            continue
        try:
            rec_year = int(rec.get("year", 0) or 0)
        except Exception:
            continue
        if rec_year == yy:
            candidates.append(rec)
    if not candidates:
        return None
    candidates.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return candidates[0]


def _record_summary(
    rec: dict,
    include_result: bool = False,
    ticker_lookup: Optional[tuple[Dict[str, str], Dict[str, str]]] = None,
) -> dict:
    if not isinstance(rec, dict):
        rec = {}
    ticker = _resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
    industry = str(rec.get("industry", "") or "").strip() or "Other"
    forced_industry = _FORCED_INDUSTRY_BY_TICKER.get(_normalize_ticker(ticker))
    if forced_industry:
        industry = forced_industry
    base = {
        "record_id": rec.get("record_id"),
        "company": rec.get("company"),
        "ticker": ticker,
        "industry": industry,
        "year": rec.get("year"),
        "filing_type": rec.get("filing_type"),
        "filing_quarter": rec.get("filing_quarter"),
        "file_ext": rec.get("file_ext"),
        "risk_items": rec.get("risk_items"),
        "risk_categories": rec.get("risk_categories"),
        "has_ai_summary": rec.get("has_ai_summary"),
        "created_at": rec.get("created_at"),
    }
    if include_result:
        try:
            result = _load_result(str(rec.get("record_id", "") or ""))
            if isinstance(result, dict):
                risks = _extract_sub_risks(result)
                base["risk_items"] = len(risks)
                base["risk_categories"] = len(
                    {
                        str(r.get("category", "") or "").strip()
                        for r in risks
                        if str(r.get("category", "") or "").strip()
                    }
                )
                base["has_ai_summary"] = bool(result.get("ai_summary"))
            else:
                base["risk_items"] = 0
                base["risk_categories"] = 0
                base["has_ai_summary"] = False
        except Exception:
            base["risk_items"] = 0
            base["risk_categories"] = 0
            base["has_ai_summary"] = False
    return base


def _to_int_safe(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _risk_pressure_index(
    high: int,
    medium: int,
    low: int,
    *,
    scoring_status: str = "ok",
) -> Optional[float]:
    """Three-state RPI:

      None  → scoring failed / no agent_report (frontend renders "—")
      0.0   → all-Low / no risks (legitimate low-risk record)
      >0.0  → normal weighted score in (0, 100]

    Only `scoring_status == "failed"` (or "missing") returns None; H+M+L=0
    with status="ok" still maps to 0.0 because that is a legitimate signal.
    """
    if str(scoring_status) in ("failed", "missing"):
        return None
    total = int(high or 0) + int(medium or 0) + int(low or 0)
    if total <= 0:
        return 0.0
    weighted = (3 * int(high or 0)) + (2 * int(medium or 0)) + int(low or 0)
    # Scale 1.0~3.0 to 0~100.
    return round(((weighted / total) - 1.0) / 2.0 * 100.0, 2)


def _extract_priority_counts_from_result(result: dict) -> dict:
    out = {
        "high": 0,
        "medium": 0,
        "low": 0,
        "total": 0,
        "top_high": [],
        "scoring_status": "missing",
    }
    if not isinstance(result, dict):
        return out

    agent_report = result.get("agent_report", {}) if isinstance(result.get("agent_report"), dict) else {}
    pm = agent_report.get("priority_matrix", {}) if isinstance(agent_report.get("priority_matrix"), dict) else {}
    # Read the explicit signal when present; fall back to "ok" for legacy
    # records that have a populated priority_matrix but no scoring_status.
    raw_status = str(agent_report.get("scoring_status", "") or "").strip()
    if raw_status in ("ok", "partial", "failed", "missing"):
        status = raw_status
    elif isinstance(agent_report, dict) and isinstance(agent_report.get("priority_matrix"), dict):
        status = "ok"
    else:
        status = "missing"
    out["scoring_status"] = status

    high = _to_int_safe((pm.get("high", {}) or {}).get("count", 0), 0) if isinstance(pm.get("high"), dict) else 0
    medium = _to_int_safe((pm.get("medium", {}) or {}).get("count", 0), 0) if isinstance(pm.get("medium"), dict) else 0
    low = _to_int_safe((pm.get("low", {}) or {}).get("count", 0), 0) if isinstance(pm.get("low"), dict) else 0

    top_high: List[str] = []
    if isinstance(pm.get("high"), dict):
        for item in (pm.get("high", {}) or {}).get("top", []) or []:
            if isinstance(item, dict):
                title = str(item.get("title", "") or "").strip()
                if title:
                    top_high.append(title)
            else:
                title = str(item or "").strip()
                if title:
                    top_high.append(title)
    top_high = top_high[:3]

    if high + medium + low <= 0:
        enriched_blocks = []
        if isinstance(agent_report.get("enriched_risks"), list):
            enriched_blocks = agent_report.get("enriched_risks") or []
        elif isinstance(result.get("risks"), list):
            enriched_blocks = result.get("risks") or []

        fallback_high_titles: List[str] = []
        for cat_block in enriched_blocks:
            if not isinstance(cat_block, dict):
                continue
            for sr in cat_block.get("sub_risks", []) or []:
                if not isinstance(sr, dict):
                    continue
                priority = str(sr.get("priority", "Medium") or "Medium").strip().lower()
                title = str(sr.get("title", "") or "").strip()
                if priority == "high":
                    high += 1
                    if title and len(fallback_high_titles) < 3:
                        fallback_high_titles.append(title)
                elif priority == "low":
                    low += 1
                else:
                    medium += 1
        if not top_high:
            top_high = fallback_high_titles[:3]

    out["high"] = int(high)
    out["medium"] = int(medium)
    out["low"] = int(low)
    out["total"] = int(high + medium + low)
    out["top_high"] = top_high[:3]
    return out


def _dashboard_summary() -> dict:
    index = _load_index()
    records = sorted(index, key=lambda r: str(r.get("created_at", "")), reverse=True)
    companies = sorted(
        {
            str(r.get("company", "") or "").strip()
            for r in records
            if str(r.get("company", "") or "").strip()
        }
    )

    scoped: Dict[str, dict] = {}
    ticker_lookup = _build_ticker_lookup()

    def _ensure_scope(key: str) -> dict:
        if key in scoped:
            return scoped[key]
        scoped[key] = {
            "records": 0,
            "risk_items": 0,
            "records_with_priority": 0,
            "companies_set": set(),
            "years_set": set(),
            "yearly_records_map": {},
            "priority_totals": {"high": 0, "medium": 0, "low": 0},
            "category_counts_map": {cat: 0 for cat in FIXED_RISK_CATEGORIES},
            "category_yearly_map": {},
            "heat_cells_map": {},
            "rpi_values": [],
        }
        return scoped[key]

    for rec in records:
        rid = str(rec.get("record_id", "") or "").strip()
        company = str(rec.get("company", "") or "").strip()
        industry = str(rec.get("industry", "") or "").strip() or "Other"
        year = _to_int_safe(rec.get("year"), 0)
        created_at = str(rec.get("created_at", "") or "")
        result = _load_result(rid) if rid else None
        risks = _extract_sub_risks(result) if isinstance(result, dict) else []
        risk_items = len(risks)
        priority = _extract_priority_counts_from_result(result if isinstance(result, dict) else {})
        rpi = _risk_pressure_index(
            priority["high"], priority["medium"], priority["low"],
            scoring_status=priority.get("scoring_status", "missing"),
        )

        category_counts_local: Dict[str, int] = {}
        for item in risks:
            cat = str(item.get("category", "Unknown") or "Unknown").strip() or "Unknown"
            category_counts_local[cat] = category_counts_local.get(cat, 0) + 1

        for scope_key in ("__all__", industry):
            scope = _ensure_scope(scope_key)
            scope["records"] += 1
            scope["risk_items"] += risk_items
            if company:
                scope["companies_set"].add(company)
            if year > 0:
                scope["years_set"].add(year)
                yk = str(year)
                scope["yearly_records_map"][yk] = scope["yearly_records_map"].get(yk, 0) + 1

            if priority["total"] > 0:
                scope["records_with_priority"] += 1
            scope["priority_totals"]["high"] += int(priority["high"])
            scope["priority_totals"]["medium"] += int(priority["medium"])
            scope["priority_totals"]["low"] += int(priority["low"])
            # P2/P3: include all valid RPIs (None = scoring failed/missing,
            # excluded; 0.0 = legitimate all-Low record, included).
            if rpi is not None:
                scope["rpi_values"].append(float(rpi))

            for cat, cnt in category_counts_local.items():
                normalized_cat = cat if cat in FIXED_RISK_CATEGORIES else "General & Other"
                if normalized_cat not in scope["category_counts_map"]:
                    scope["category_counts_map"][normalized_cat] = 0
                scope["category_counts_map"][normalized_cat] = scope["category_counts_map"].get(normalized_cat, 0) + int(cnt)
                by_cat = scope["category_yearly_map"].setdefault(normalized_cat, {})
                if year > 0:
                    yk = str(year)
                    by_cat[yk] = by_cat.get(yk, 0) + int(cnt)

            if company and year > 0:
                cell_key = f"{company}__{year}"
                # records are sorted newest first; keep latest for a company-year cell.
                if cell_key not in scope["heat_cells_map"]:
                    ticker = _resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
                    scope["heat_cells_map"][cell_key] = {
                        "record_id": rid,
                        "company": company,
                        "industry": industry,
                        "ticker": ticker,
                        "filing_type": str(rec.get("filing_type", "") or ""),
                        "risk_items": int(risk_items),
                        "year": year,
                        "high": int(priority["high"]),
                        "medium": int(priority["medium"]),
                        "low": int(priority["low"]),
                        "total": int(priority["total"]),
                        # Keep None as null in JSON so the frontend can render
                        # "—" for unscored vs green-0 for legitimate all-Low.
                        "rpi": (None if rpi is None else float(rpi)),
                        "scoring_status": priority.get("scoring_status", "missing"),
                        "top_high": list(priority["top_high"])[:3],
                        "created_at": created_at,
                    }

    scopes_payload: Dict[str, dict] = {}
    for scope_key, scope in scoped.items():
        heat_cells = list(scope["heat_cells_map"].values())
        years_sorted = sorted(scope["years_set"])
        max_rpi_by_company: Dict[str, float] = {}
        for cell in heat_cells:
            comp = str(cell.get("company", "") or "")
            rv = cell.get("rpi")
            if rv is None:
                continue
            max_rpi_by_company[comp] = max(max_rpi_by_company.get(comp, 0.0), float(rv))
        companies_sorted = sorted(
            list(scope["companies_set"]),
            # Companies with no scored filing fall to the bottom (-1.0 < 0.0).
            key=lambda c: (-max_rpi_by_company.get(c, -1.0), c.lower()),
        )
        heat_cells.sort(key=lambda row: (str(row.get("company", "")).lower(), int(row.get("year", 0))))

        category_counts_sorted = [(cat, int(scope["category_counts_map"].get(cat, 0))) for cat in FIXED_RISK_CATEGORIES]
        category_yearly = []
        for cat in FIXED_RISK_CATEGORIES:
            ymap = scope["category_yearly_map"].get(cat, {})
            yearly = [{"year": y, "count": int(c)} for y, c in sorted(ymap.items(), key=lambda kv: int(kv[0]))]
            category_yearly.append(
                {
                    "category": cat,
                    "total": int(scope["category_counts_map"].get(cat, 0)),
                    "yearly": yearly,
                }
            )
        category_yearly.sort(key=lambda row: (-int(row.get("total", 0)), FIXED_RISK_CATEGORIES.index(str(row.get("category", "General & Other")) if str(row.get("category", "")) in FIXED_RISK_CATEGORIES else "General & Other")))

        records_count = int(scope["records"])
        with_priority = int(scope["records_with_priority"])
        coverage_rate = round((with_priority / records_count) * 100.0, 1) if records_count > 0 else 0.0

        scopes_payload[scope_key] = {
            "metrics": {
                "records": records_count,
                "companies": len(scope["companies_set"]),
                "years_covered": len(scope["years_set"]),
                "risk_items": int(scope["risk_items"]),
                "records_with_priority": with_priority,
                "agent_coverage_rate": coverage_rate,
            },
            "yearly_records": [
                {"year": y, "count": int(c)}
                for y, c in sorted(scope["yearly_records_map"].items(), key=lambda kv: int(kv[0]))
            ],
            "priority_totals": {
                "high": int(scope["priority_totals"]["high"]),
                "medium": int(scope["priority_totals"]["medium"]),
                "low": int(scope["priority_totals"]["low"]),
            },
            "priority_heatmap": {
                "years": years_sorted,
                "companies": companies_sorted,
                "cells": heat_cells,
                "max_rpi": round(max(scope["rpi_values"]), 2) if scope["rpi_values"] else 0.0,
                "avg_rpi": round(sum(scope["rpi_values"]) / len(scope["rpi_values"]), 2) if scope["rpi_values"] else 0.0,
            },
            "top_categories": [{"category": k, "count": int(v)} for k, v in sorted(category_counts_sorted, key=lambda kv: (-kv[1], FIXED_RISK_CATEGORIES.index(kv[0])))[:9]],
            "category_counts": [{"category": k, "count": int(v)} for k, v in category_counts_sorted],
            "category_yearly": category_yearly,
        }

    recent_records = [_record_summary(r, include_result=True, ticker_lookup=ticker_lookup) for r in records[:12]]
    all_scope = scopes_payload.get("__all__", {})
    industry_options = sorted([k for k in scopes_payload.keys() if k != "__all__"], key=lambda x: x.lower())

    return {
        "metrics": all_scope.get("metrics", {
            "records": len(records),
            "companies": len(companies),
            "years_covered": 0,
            "risk_items": 0,
            "records_with_priority": 0,
            "agent_coverage_rate": 0.0,
        }),
        "top_categories": all_scope.get("top_categories", []),
        "yearly_records": all_scope.get("yearly_records", []),
        "recent_records": recent_records,
        "companies": companies,
        "industry_options": industry_options,
        "scopes": scopes_payload,
    }


def _dashboard_summary_cached(force: bool = False) -> dict:
    now = time.time()
    cached_ts = float(_DASHBOARD_SUMMARY_CACHE.get("ts", 0.0) or 0.0)
    cached_data = _DASHBOARD_SUMMARY_CACHE.get("data")
    if (not force) and isinstance(cached_data, dict) and (now - cached_ts) <= _DASHBOARD_SUMMARY_CACHE_TTL_SECONDS:
        return cached_data
    fresh = _dashboard_summary()
    _DASHBOARD_SUMMARY_CACHE["ts"] = now
    _DASHBOARD_SUMMARY_CACHE["data"] = fresh
    return fresh


def _records_list_cache_key(
    *,
    company: str,
    industry: str,
    filing_type: str,
    year: str,
    include_result: bool,
) -> str:
    return "|".join(
        [
            str(company or "").strip().lower(),
            str(industry or "").strip().lower(),
            str(filing_type or "").strip().lower(),
            str(year or "").strip(),
            "1" if include_result else "0",
        ]
    )


def _should_retry_insecure_tls(exc: Exception) -> bool:
    msg = str(exc or "").lower()
    return (
        "certificate_verify_failed" in msg
        or "self signed certificate" in msg
        or "unable to get local issuer certificate" in msg
    )


def _urlopen_with_tls_fallback(req: Request, *, timeout: int, context=None):
    try:
        if context is None:
            return urlopen(req, timeout=timeout)
        return urlopen(req, timeout=timeout, context=context)
    except URLError as exc:
        # Demo/runtime environments occasionally miss CA roots. When that
        # specific TLS verification failure happens, retry once with an
        # unverified context so market-data tools can still respond.
        if _should_retry_insecure_tls(exc):
            insecure_ctx = ssl._create_unverified_context()
            return urlopen(req, timeout=timeout, context=insecure_ctx)
        raise
    except ssl.SSLCertVerificationError:
        insecure_ctx = ssl._create_unverified_context()
        return urlopen(req, timeout=timeout, context=insecure_ctx)


def _yahoo_json(url: str) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    with _urlopen_with_tls_fallback(req, timeout=20) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="ignore"))


def _to_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, str):
            v = value.strip().replace(",", "")
            if v.endswith("%"):
                v = v[:-1]
            if not v:
                return default
            return float(v)
        return float(value)
    except Exception:
        return default


def _stock_provider_state(name: str) -> Dict[str, Any]:
    key = str(name or "").strip().lower() or "unknown"
    state = _STOCK_PROVIDER_STATE.get(key)
    if not isinstance(state, dict):
        state = {
            "disabled_until": 0.0,
            "failures": 0,
            "last_error": "",
            "last_error_at": 0.0,
        }
        _STOCK_PROVIDER_STATE[key] = state
    return state


def _provider_cooldown_left(name: str) -> int:
    state = _stock_provider_state(name)
    now = time.time()
    left = float(state.get("disabled_until", 0.0) or 0.0) - now
    return int(left) if left > 0 else 0


def _provider_available(name: str) -> bool:
    return _provider_cooldown_left(name) <= 0


def _provider_mark_success(name: str) -> None:
    state = _stock_provider_state(name)
    state["failures"] = 0
    state["disabled_until"] = 0.0


def _is_rate_limited_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        try:
            if int(exc.code) == 429:
                return True
        except Exception:
            pass
    text = str(exc or "").lower()
    return (
        "429" in text
        or "too many requests" in text
        or "run out of api credits" in text
        or "credits limit has been reached" in text
    )


def _provider_mark_failure(name: str, exc: Exception) -> None:
    state = _stock_provider_state(name)
    now = time.time()
    state["failures"] = int(state.get("failures", 0) or 0) + 1
    state["last_error"] = str(exc or "")[:320]
    state["last_error_at"] = now

    if _is_rate_limited_error(exc):
        state["disabled_until"] = now + _STOCK_PROVIDER_DEFAULT_COOLDOWN_SECONDS
        return

    fails = int(state.get("failures", 0) or 0)
    if fails >= 3:
        state["disabled_until"] = now + min(45, 8 + fails * 4)


def _provider_snapshot(names: List[str]) -> Dict[str, Dict[str, Any]]:
    snap: Dict[str, Dict[str, Any]] = {}
    for raw in names:
        name = str(raw or "").strip().lower()
        if not name:
            continue
        state = _stock_provider_state(name)
        snap[name] = {
            "available": _provider_available(name),
            "cooldown_s": _provider_cooldown_left(name),
            "failures": int(state.get("failures", 0) or 0),
        }
    return snap


def _stock_cache_get(symbol: str) -> Optional[Dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None

    cached = _STOCK_QUOTE_CACHE.get(sym)
    ts = 0.0
    payload: Optional[Dict[str, Any]] = None
    if isinstance(cached, dict):
        ts = float(cached.get("saved_at", 0.0) or 0.0)
        raw_payload = cached.get("payload")
        payload = raw_payload if isinstance(raw_payload, dict) else None

    # L1 cache miss: try persistent S3 cache.
    if not payload:
        persisted = _stock_cache_read_persistent(sym)
        if isinstance(persisted, dict):
            ts = float(persisted.get("saved_at", 0.0) or 0.0)
            raw_payload = persisted.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else None
            if payload:
                _STOCK_QUOTE_CACHE[sym] = {"saved_at": ts, "payload": dict(payload)}

    if not payload:
        return None

    age = time.time() - ts
    if age < 0 or age > _STOCK_QUOTE_CACHE_TTL_SECONDS:
        return None
    out = dict(payload)
    out["cache_hit"] = True
    out["cache_age_s"] = int(age)
    return out


def _stock_cache_get_stale(symbol: str) -> Optional[Dict[str, Any]]:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return None

    cached = _STOCK_QUOTE_CACHE.get(sym)
    payload: Optional[Dict[str, Any]] = None
    ts = 0.0
    if isinstance(cached, dict):
        ts = float(cached.get("saved_at", 0.0) or 0.0)
        raw_payload = cached.get("payload")
        payload = raw_payload if isinstance(raw_payload, dict) else None

    if not payload:
        persisted = _stock_cache_read_persistent(sym)
        if isinstance(persisted, dict):
            ts = float(persisted.get("saved_at", 0.0) or 0.0)
            raw_payload = persisted.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else None
            if payload:
                _STOCK_QUOTE_CACHE[sym] = {"saved_at": ts, "payload": dict(payload)}

    if not payload:
        return None

    age = time.time() - ts
    if age < 0:
        age = 0.0
    out = dict(payload)
    out["cache_hit"] = True
    out["cache_age_s"] = int(age)
    out["stale_cache"] = True
    return out


def _stock_cache_set(symbol: str, payload: dict) -> None:
    sym = str(symbol or "").strip().upper()
    if not sym or not isinstance(payload, dict):
        return
    saved_at = time.time()
    _STOCK_QUOTE_CACHE[sym] = {
        "saved_at": saved_at,
        "payload": dict(payload),
    }
    _stock_cache_write_persistent(sym, payload, saved_at=saved_at)


def _stock_cache_storage_key(symbol: str) -> str:
    sym = re.sub(r"[^A-Z0-9_.\-]", "_", str(symbol or "").strip().upper())
    if not sym:
        sym = "UNKNOWN"
    return f"{_STOCK_QUOTE_CACHE_PREFIX}/{sym}.json"


def _stock_cache_read_persistent(symbol: str) -> Optional[Dict[str, Any]]:
    if not _bucket():
        return None
    key = _stock_cache_storage_key(symbol)
    try:
        raw = _json_from_bytes(_read_s3_bytes(key), None)
        if not isinstance(raw, dict):
            return None
        ts = float(raw.get("saved_at", 0.0) or 0.0)
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            return None
        return {"saved_at": ts, "payload": payload}
    except Exception:
        return None


def _stock_cache_write_persistent(symbol: str, payload: dict, *, saved_at: Optional[float] = None) -> None:
    if not _bucket():
        return
    if not isinstance(payload, dict):
        return
    key = _stock_cache_storage_key(symbol)
    envelope = {
        "saved_at": float(saved_at if saved_at is not None else time.time()),
        "payload": payload,
    }
    try:
        _write_s3_bytes(key, json.dumps(envelope, ensure_ascii=False, default=str).encode("utf-8"))
    except Exception:
        # Cache write failures should never fail the stock quote response path.
        return


def _symbol_candidates(symbol: str) -> List[str]:
    base = str(symbol or "").strip().upper()
    if not base:
        return []
    variants = [base]
    if "." in base:
        variants.append(base.replace(".", "-"))
        variants.append(base.replace(".", ""))
    if "-" in base:
        variants.append(base.replace("-", "."))
        variants.append(base.replace("-", ""))
    # Prefer common US share-class form with dash for Yahoo-like providers.
    if "." in base and len(base.split(".", 1)[-1]) == 1:
        variants.insert(0, base.replace(".", "-"))
    out: List[str] = []
    for v in variants:
        cleaned = re.sub(r"[^A-Z0-9.\-]", "", str(v or "").strip().upper())
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def _try_symbol_variants(
    symbol: str,
    loader: Callable[[str], Any],
    *,
    require_truthy: bool = True,
) -> tuple[Any, str, List[str]]:
    attempts: List[str] = []
    for candidate in _symbol_candidates(symbol):
        try:
            data = loader(candidate)
            if require_truthy and not data:
                attempts.append(f"{candidate}: empty")
                continue
            return data, candidate, attempts
        except Exception as exc:
            attempts.append(f"{candidate}: {type(exc).__name__}: {exc}")
    return None, "", attempts


def _twelvedata_api_key() -> str:
    return (
        _env("TWELVEDATA_API_KEY", "").strip()
        or _env("TWELVE_DATA_API_KEY", "").strip()
        or _env("TWELVE_DATA_KEY", "").strip()
    )


def _fmp_api_key() -> str:
    return (
        _env("FMP_API_KEY", "").strip()
        or _env("FINANCIAL_MODELING_PREP_API_KEY", "").strip()
        or _env("FINANCIALMODELINGPREP_API_KEY", "").strip()
    )


def _twelvedata_json(url: str) -> dict:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    with _urlopen_with_tls_fallback(req, timeout=20) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8", errors="ignore"))
    if isinstance(payload, dict) and str(payload.get("status", "")).lower() == "error":
        code = payload.get("code")
        message = payload.get("message") or "unknown error"
        raise RuntimeError(f"{code}: {message}" if code else str(message))
    if not isinstance(payload, dict):
        raise RuntimeError("invalid response payload")
    return payload


def _twelvedata_quote(symbol: str, api_key: str) -> dict:
    sym = str(symbol or "").strip().upper()
    url = f"https://api.twelvedata.com/quote?symbol={quote(sym)}&apikey={quote(api_key)}"
    payload = _twelvedata_json(url)

    price = _to_float(payload.get("close"))
    previous_close = _to_float(payload.get("previous_close"))
    change = _to_float(payload.get("change"))
    change_percent = _to_float(payload.get("percent_change"))
    if change is None and price is not None and previous_close is not None:
        change = price - previous_close
    if change_percent is None and change is not None and previous_close not in (None, 0):
        change_percent = change / previous_close * 100.0

    fifty_two = payload.get("fifty_two_week", {}) if isinstance(payload.get("fifty_two_week"), dict) else {}

    return {
        "symbol": payload.get("symbol") or sym,
        "name": payload.get("name") or sym,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "market_cap": _to_float(payload.get("market_cap")),
        "pe_ratio": _to_float(payload.get("pe")),
        "high_52": _to_float(fifty_two.get("high"), _to_float(payload.get("fifty_two_week_high"))),
        "low_52": _to_float(fifty_two.get("low"), _to_float(payload.get("fifty_two_week_low"))),
        "exchange": payload.get("exchange") or payload.get("mic_code") or "",
    }


def _twelvedata_history(symbol: str, api_key: str) -> List[dict]:
    sym = str(symbol or "").strip().upper()
    url = (
        "https://api.twelvedata.com/time_series"
        f"?symbol={quote(sym)}&interval=1day&outputsize=260&apikey={quote(api_key)}"
    )
    payload = _twelvedata_json(url)
    rows = payload.get("values", []) if isinstance(payload, dict) else []
    out: List[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_dt = str(row.get("datetime") or row.get("date") or "").strip()
        if not raw_dt:
            continue
        dt = raw_dt[:10]
        close_val = _to_float(row.get("close"))
        if close_val is None:
            continue
        out.append({"date": dt, "close": close_val})
    out.sort(key=lambda x: x.get("date", ""))
    return out


def _twelvedata_intraday_history(symbol: str, api_key: str) -> List[dict]:
    sym = str(symbol or "").strip().upper()
    url = (
        "https://api.twelvedata.com/time_series"
        f"?symbol={quote(sym)}&interval=1h&outputsize=48&apikey={quote(api_key)}"
    )
    payload = _twelvedata_json(url)
    rows = payload.get("values", []) if isinstance(payload, dict) else []
    out: List[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        dt = str(row.get("datetime") or row.get("date") or "").strip()
        if not dt:
            continue
        close_val = _to_float(row.get("close"))
        if close_val is None:
            continue
        vol = _to_float(row.get("volume"), 0.0)
        out.append({"date": dt, "close": close_val, "volume": vol})
    out.sort(key=lambda x: str(x.get("date", "")))
    return out


def _fmp_json(url: str):
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )
    raw = b""
    status_code = 0
    try:
        with _urlopen_with_tls_fallback(
            req,
            timeout=20,
            context=ssl.create_default_context(cafile=certifi.where()),
        ) as resp:
            status_code = int(getattr(resp, "status", 200) or 200)
            raw = resp.read()
    except HTTPError as exc:
        status_code = int(getattr(exc, "code", 0) or 0)
        raw = exc.read() if hasattr(exc, "read") else b""
    except Exception:
        raise

    text = raw.decode("utf-8", errors="ignore")
    try:
        payload = json.loads(text)
    except Exception:
        payload = {"error": text or f"HTTP {status_code}"}

    if isinstance(payload, dict):
        msg = str(payload.get("Error Message") or payload.get("error") or payload.get("message") or "").strip()
        if msg and msg.lower() not in {"ok", "success"}:
            raise RuntimeError(f"HTTP {status_code}: {msg}" if status_code else msg)
    if status_code >= 400:
        # Keep the explicit code in the error text so caller can distinguish
        # quota/rate-limit style failures and immediately fall back.
        raise RuntimeError(f"HTTP {status_code}: fmp request failed")
    return payload


def _fmp_quote(symbol: str, api_key: str) -> dict:
    sym = str(symbol or "").strip().upper()
    url = f"https://financialmodelingprep.com/stable/quote?symbol={quote(sym)}&apikey={quote(api_key)}"
    payload = _fmp_json(url)
    rows = payload if isinstance(payload, list) else []
    if not rows:
        raise RuntimeError("empty quote response")
    row = rows[0] if isinstance(rows[0], dict) else {}

    return {
        "symbol": row.get("symbol") or sym,
        "name": row.get("name") or row.get("companyName") or sym,
        "price": _to_float(row.get("price")),
        "change": _to_float(row.get("change")),
        "change_percent": _to_float(row.get("changesPercentage"), _to_float(row.get("changePercentage"))),
        "market_cap": _to_float(row.get("marketCap")),
        "pe_ratio": _to_float(row.get("pe"), _to_float(row.get("priceToEarningsRatioTTM"))),
        "high_52": _to_float(row.get("yearHigh")),
        "low_52": _to_float(row.get("yearLow")),
        "exchange": row.get("exchange") or row.get("exchangeShortName") or row.get("exchangeFullName") or "",
        "previous_close": _to_float(row.get("previousClose")),
        "open": _to_float(row.get("open")),
        "day_high": _to_float(row.get("dayHigh")),
        "day_low": _to_float(row.get("dayLow")),
        "volume": _to_float(row.get("volume")),
    }


def _fmp_profile(symbol: str, api_key: str) -> dict:
    sym = str(symbol or "").strip().upper()
    url = f"https://financialmodelingprep.com/stable/profile?symbol={quote(sym)}&apikey={quote(api_key)}"
    payload = _fmp_json(url)
    rows = payload if isinstance(payload, list) else []
    if not rows:
        raise RuntimeError("empty profile response")
    row = rows[0] if isinstance(rows[0], dict) else {}

    return {
        "symbol": row.get("symbol") or sym,
        "name": row.get("companyName") or row.get("name") or sym,
        "market_cap": _to_float(row.get("marketCap"), _to_float(row.get("mktCap"))),
        "industry": row.get("industry") or "",
        "sector": row.get("sector") or "",
        "country": row.get("country") or "",
        "full_time_employees": _to_float(row.get("fullTimeEmployees")),
        "ceo": row.get("ceo") or "",
        "description": row.get("description") or "",
        "ipo_date": row.get("ipoDate") or "",
        "exchange": row.get("exchangeShortName") or row.get("exchange") or row.get("exchangeFullName") or "",
        "shares_outstanding": _to_float(row.get("sharesOutstanding")),
    }


def _fmp_ratios_ttm(symbol: str, api_key: str) -> dict:
    sym = str(symbol or "").strip().upper()
    url = f"https://financialmodelingprep.com/stable/ratios-ttm?symbol={quote(sym)}&apikey={quote(api_key)}"
    payload = _fmp_json(url)
    rows = payload if isinstance(payload, list) else []
    if not rows:
        raise RuntimeError("empty ratios-ttm response")
    row = rows[0] if isinstance(rows[0], dict) else {}
    return {
        "symbol": row.get("symbol") or sym,
        "pe_ratio": _to_float(row.get("priceToEarningsRatioTTM")),
    }


def _fmp_history(symbol: str, api_key: str) -> List[dict]:
    sym = str(symbol or "").strip().upper()
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=430)
    url = (
        "https://financialmodelingprep.com/stable/historical-price-eod/full"
        f"?symbol={quote(sym)}&from={start.isoformat()}&to={today.isoformat()}&apikey={quote(api_key)}"
    )
    payload = _fmp_json(url)
    rows = payload if isinstance(payload, list) else []
    out: List[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        dt = str(row.get("date") or row.get("datetime") or "").strip()[:10]
        close_val = _to_float(row.get("close"))
        if not dt or close_val is None:
            continue
        out.append(
            {
                "date": dt,
                "close": close_val,
                "volume": _to_float(row.get("volume"), 0.0),
            }
        )
    out.sort(key=lambda x: x.get("date", ""))
    if not out:
        raise RuntimeError("empty historical response")
    return out


def _stooq_history(symbol: str) -> List[dict]:
    sym = str(symbol or "").strip().lower()
    if not sym:
        return []

    candidates = [sym]
    if "." not in sym:
        candidates.append(f"{sym}.us")

    for candidate in candidates:
        url = f"https://stooq.com/q/d/l/?s={quote(candidate)}&i=d"
        req = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            method="GET",
        )
        try:
            with _urlopen_with_tls_fallback(
                req,
                timeout=20,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            continue

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) <= 1:
            continue

        out: List[dict] = []
        for line in lines[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            dt = parts[0].strip()
            close_raw = parts[4].strip()
            if not dt or not close_raw or close_raw.lower() == "null":
                continue
            try:
                close_val = float(close_raw)
            except Exception:
                continue
            out.append({"date": dt, "close": close_val})
        if out:
            return out

    return []


def _stooq_snapshot(symbol: str) -> dict:
    """Read latest daily snapshot (open/high/low/close/volume) from Stooq."""
    sym = str(symbol or "").strip().lower()
    if not sym:
        return {}

    candidates = [sym]
    if "." not in sym:
        candidates.append(f"{sym}.us")

    for candidate in candidates:
        url = f"https://stooq.com/q/l/?s={quote(candidate)}&i=d"
        req = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            method="GET",
        )
        try:
            with _urlopen_with_tls_fallback(
                req,
                timeout=20,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as resp:
                text = resp.read().decode("utf-8", errors="ignore").strip()
        except Exception:
            continue

        line = text.splitlines()[0].strip() if text else ""
        parts = [p.strip() for p in line.split(",")] if line else []
        if len(parts) < 8:
            continue

        open_v = _to_float(parts[3])
        high_v = _to_float(parts[4])
        low_v = _to_float(parts[5])
        close_v = _to_float(parts[6])
        vol_v = _to_float(parts[7])
        if close_v is None:
            continue
        delta = None
        pct = None
        if open_v is not None:
            delta = close_v - open_v
            if open_v not in (0, 0.0):
                pct = (delta / open_v) * 100.0
        return {
            "open": open_v,
            "day_high": high_v,
            "day_low": low_v,
            "price": close_v,
            "change": delta,
            "change_percent": pct,
            "volume": vol_v,
        }

    return {}


def _wikidata_profile(symbol: str) -> dict:
    """Free profile fallback via Wikidata SPARQL (no API key)."""
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {}

    now = time.time()
    cached = _WIKIDATA_STOCK_PROFILE_CACHE.get(sym)
    if isinstance(cached, dict) and (now - float(cached.get("ts", 0.0) or 0.0) < _WIKIDATA_STOCK_PROFILE_TTL_SECONDS):
        payload = cached.get("data")
        return payload if isinstance(payload, dict) else {}

    query = f"""
SELECT ?companyLabel ?ceoLabel ?inception ?employees ?countryLabel ?industryLabel WHERE {{
  {{ ?company wdt:P249 "{sym}". }}
  UNION
  {{ ?company p:P414 ?listing . ?listing pq:P249 "{sym}". }}
  UNION
  {{ ?company p:P249 ?st . ?st ps:P249 "{sym}". }}
  OPTIONAL {{ ?company wdt:P169 ?ceo. }}
  OPTIONAL {{ ?company wdt:P571 ?inception. }}
  OPTIONAL {{ ?company wdt:P1128 ?employees. }}
  OPTIONAL {{ ?company wdt:P17 ?country. }}
  OPTIONAL {{ ?company wdt:P452 ?industry. }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 1
""".strip()

    url = f"https://query.wikidata.org/sparql?query={quote(query)}"
    req = Request(
        url,
        headers={
            "Accept": "application/sparql-results+json",
            "User-Agent": "RiskLensAI/1.0 (stock-profile-fallback)",
        },
        method="GET",
    )
    data: dict = {}
    try:
        with _urlopen_with_tls_fallback(
            req,
            timeout=18,
            context=ssl.create_default_context(cafile=certifi.where()),
        ) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        rows = payload.get("results", {}).get("bindings", []) if isinstance(payload, dict) else []
        row = rows[0] if rows and isinstance(rows[0], dict) else {}

        def _v(key: str) -> str:
            item = row.get(key)
            return str(item.get("value", "") if isinstance(item, dict) else "").strip()

        inception = _v("inception")
        ipo_date = inception[:10] if inception else ""
        data = {
            "name": _v("companyLabel"),
            "ceo": _v("ceoLabel"),
            "country": _v("countryLabel"),
            "industry": _v("industryLabel"),
            "ipo_date": ipo_date,
            "full_time_employees": _to_float(_v("employees")),
        }
    except Exception:
        data = {}

    _WIKIDATA_STOCK_PROFILE_CACHE[sym] = {"ts": now, "data": data}
    return data


def _stock_quote(symbol: str, lite: bool = False) -> dict:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"error": "Ticker is required."}

    cache_symbol = f"{sym}__LITE" if lite else sym
    cached = _stock_cache_get(cache_symbol)
    if cached:
        cached["providers"] = _provider_snapshot(["twelvedata", "fmp", "yahoo"])
        return cached

    if lite:
        history: List[dict] = []
        errors: List[str] = []
        history_source = ""

        stooq_history = _stooq_history(sym)
        if stooq_history:
            history = stooq_history
            history_source = "stooq"

        if not history and _provider_available("yahoo"):
            def _load_yahoo_chart(candidate: str) -> List[dict]:
                chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{candidate}?range=1y&interval=1d"
                chart_payload = _yahoo_json(chart_url)
                chart = chart_payload.get("chart", {}) if isinstance(chart_payload, dict) else {}
                results = chart.get("result", []) if isinstance(chart, dict) else []
                parsed_history: List[dict] = []
                if results:
                    first = results[0] if isinstance(results[0], dict) else {}
                    ts = first.get("timestamp", []) or []
                    q = first.get("indicators", {}).get("quote", []) or []
                    closes = q[0].get("close", []) if q and isinstance(q[0], dict) else []
                    vols = q[0].get("volume", []) if q and isinstance(q[0], dict) else []
                    for i, t in enumerate(ts):
                        try:
                            c = closes[i]
                        except Exception:
                            c = None
                        if c is None:
                            continue
                        try:
                            dt = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
                        except Exception:
                            continue
                        vol = _to_float(vols[i], 0.0) if i < len(vols) else 0.0
                        parsed_history.append({"date": dt, "close": float(c), "volume": vol})
                return parsed_history

            parsed_history, _, yahoo_attempts = _try_symbol_variants(sym, _load_yahoo_chart, require_truthy=True)
            if parsed_history:
                history = parsed_history
                history_source = "yahoo"
                _provider_mark_success("yahoo")
            else:
                exc = RuntimeError("; ".join(yahoo_attempts) if yahoo_attempts else "empty history")
                _provider_mark_failure("yahoo", exc)
                errors.append(f"yahoo chart: {exc}")

        if not history:
            stale_cached = _stock_cache_get_stale(cache_symbol)
            if stale_cached:
                stale_cached["providers"] = _provider_snapshot(["twelvedata", "fmp", "yahoo"])
                stale_cached["warning"] = (
                    "Upstream providers temporarily returned no data. "
                    f"Showing stale cache ({int(stale_cached.get('cache_age_s', 0) or 0)}s old)."
                )
                return stale_cached
            detail = "; ".join(errors) if errors else "no data returned by public fallback providers"
            return {"error": f"Failed to fetch stock data: {detail}"}

        history = [h for h in history if isinstance(h, dict) and _to_float(h.get("close")) is not None]
        history.sort(key=lambda x: str(x.get("date", "")))
        if len(history) < 2:
            return {"error": "Not enough history points for this ticker."}

        last_close = float(history[-1]["close"])
        prev_close = float(history[-2]["close"])
        delta = last_close - prev_close
        pct = (delta / prev_close * 100.0) if prev_close != 0 else None
        out = {
            "symbol": sym,
            "name": sym,
            "price": last_close,
            "change": delta,
            "change_percent": pct,
            "market_cap": None,
            "pe_ratio": None,
            "high_52": max(float(h["close"]) for h in history),
            "low_52": min(float(h["close"]) for h in history),
            "exchange": "US",
            "history": history,
            "quote_source": history_source or "derived",
            "history_source": history_source or "",
            "providers": _provider_snapshot(["twelvedata", "fmp", "yahoo"]),
            "cache_hit": False,
            "cache_age_s": 0,
            "error": "",
            "lite": True,
        }
        if errors:
            out["warning"] = "Sector-lite fetch used fallback history sources."
        _stock_cache_set(cache_symbol, out)
        return out

    name = sym
    price = None
    change = None
    change_percent = None
    market_cap = None
    pe_ratio = None
    high_52 = None
    low_52 = None
    exchange = ""
    previous_close = None
    open_price = None
    day_high = None
    day_low = None
    volume = None
    eps = None
    dividend_yield = None
    sector = ""
    industry = ""
    country = ""
    full_time_employees = None
    shares_outstanding = None
    ceo = ""
    long_description = ""
    ipo_date = ""
    post_market_price = None
    post_market_change = None
    post_market_change_percent = None
    regular_market_time = None
    post_market_time = None
    history: List[dict] = []
    intraday_history: List[dict] = []
    errors: List[str] = []
    quote_source = ""
    history_source = ""
    intraday_history_source = ""

    def _apply_quote_fields(provider: str, data: dict) -> None:
        nonlocal name, price, change, change_percent, market_cap, pe_ratio, high_52, low_52, exchange, quote_source
        nonlocal previous_close, open_price, day_high, day_low, volume, eps, dividend_yield
        nonlocal sector, industry, country, full_time_employees, shares_outstanding, ceo, long_description, ipo_date
        nonlocal post_market_price, post_market_change, post_market_change_percent, regular_market_time, post_market_time
        if not isinstance(data, dict):
            return

        def _merge_numeric(current, incoming, *, prefer_positive: bool = False):
            nxt = _to_float(incoming)
            if nxt is None:
                return current
            cur = _to_float(current)
            if cur is None:
                return nxt
            if prefer_positive and cur <= 0 < nxt:
                return nxt
            return current

        if not quote_source and any(
            data.get(k) is not None for k in ("price", "change", "change_percent", "market_cap", "pe_ratio")
        ):
            quote_source = provider

        incoming_name = str(data.get("name", "") or "").strip()
        if incoming_name and (not name or name == sym):
            name = incoming_name
        price = _merge_numeric(price, data.get("price"), prefer_positive=True)
        if change is None:
            change = _to_float(data.get("change"))
        if change_percent is None:
            change_percent = _to_float(data.get("change_percent"))
        market_cap = _merge_numeric(market_cap, data.get("market_cap"), prefer_positive=True)
        pe_ratio = _merge_numeric(pe_ratio, data.get("pe_ratio"), prefer_positive=True)
        high_52 = _merge_numeric(high_52, data.get("high_52"), prefer_positive=True)
        low_52 = _merge_numeric(low_52, data.get("low_52"), prefer_positive=True)
        if not exchange:
            exchange = str(data.get("exchange", "") or "").strip()
        previous_close = _merge_numeric(previous_close, data.get("previous_close"), prefer_positive=True)
        open_price = _merge_numeric(open_price, data.get("open"), prefer_positive=True)
        day_high = _merge_numeric(day_high, data.get("day_high"), prefer_positive=True)
        day_low = _merge_numeric(day_low, data.get("day_low"), prefer_positive=True)
        volume = _merge_numeric(volume, data.get("volume"), prefer_positive=True)
        eps = _merge_numeric(eps, data.get("eps"), prefer_positive=True)
        dividend_yield = _merge_numeric(dividend_yield, data.get("dividend_yield"), prefer_positive=True)
        if not sector:
            sector = str(data.get("sector", "") or "").strip()
        if not industry:
            industry = str(data.get("industry", "") or "").strip()
        if not country:
            country = str(data.get("country", "") or "").strip()
        full_time_employees = _merge_numeric(full_time_employees, data.get("full_time_employees"), prefer_positive=True)
        shares_outstanding = _merge_numeric(shares_outstanding, data.get("shares_outstanding"), prefer_positive=True)
        if not ceo:
            ceo = str(data.get("ceo", "") or "").strip()
        if not long_description:
            long_description = str(data.get("description", "") or "").strip()
        if not ipo_date:
            ipo_date = str(data.get("ipo_date", "") or "").strip()
        post_market_price = _merge_numeric(post_market_price, data.get("post_market_price"), prefer_positive=True)
        if post_market_change is None:
            post_market_change = _to_float(data.get("post_market_change"))
        if post_market_change_percent is None:
            post_market_change_percent = _to_float(data.get("post_market_change_percent"))
        regular_market_time = _merge_numeric(regular_market_time, data.get("regular_market_time"), prefer_positive=True)
        post_market_time = _merge_numeric(post_market_time, data.get("post_market_time"), prefer_positive=True)

    def _need_quote_fields() -> bool:
        return any(v is None for v in [price, change, change_percent, market_cap, pe_ratio, high_52, low_52]) or not exchange

    def _need_profile_fields() -> bool:
        return (
            not sector
            or not industry
            or not country
            or full_time_employees in (None, 0)
            or not ceo
            or not ipo_date
            or not long_description
            or shares_outstanding in (None, 0)
        )

    twelvedata_key = _twelvedata_api_key()

    if twelvedata_key and _provider_available("twelvedata") and _need_quote_fields():
        td_quote, _, td_quote_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _twelvedata_quote(candidate, twelvedata_key),
            require_truthy=True,
        )
        if td_quote:
            _apply_quote_fields("twelvedata", td_quote)
            _provider_mark_success("twelvedata")
        else:
            exc = RuntimeError("; ".join(td_quote_attempts) if td_quote_attempts else "no quote response")
            _provider_mark_failure("twelvedata", exc)
            errors.append(f"twelvedata quote: {exc}")

    if twelvedata_key and _provider_available("twelvedata") and not history:
        td_history, _, td_history_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _twelvedata_history(candidate, twelvedata_key),
            require_truthy=True,
        )
        if td_history:
            history = td_history
            history_source = "twelvedata"
            _provider_mark_success("twelvedata")
        else:
            exc = RuntimeError("; ".join(td_history_attempts) if td_history_attempts else "no history response")
            _provider_mark_failure("twelvedata", exc)
            errors.append(f"twelvedata history: {exc}")

    if twelvedata_key and _provider_available("twelvedata") and not intraday_history:
        td_intraday, _, td_intraday_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _twelvedata_intraday_history(candidate, twelvedata_key),
            require_truthy=True,
        )
        if td_intraday:
            intraday_history = td_intraday
            intraday_history_source = "twelvedata"
            _provider_mark_success("twelvedata")
        else:
            exc = RuntimeError("; ".join(td_intraday_attempts) if td_intraday_attempts else "no intraday response")
            _provider_mark_failure("twelvedata", exc)
            errors.append(f"twelvedata intraday: {exc}")

    fmp_key = _fmp_api_key()
    if fmp_key and _provider_available("fmp") and _need_quote_fields():
        fmp_quote, _, fmp_quote_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _fmp_quote(candidate, fmp_key),
            require_truthy=True,
        )
        if fmp_quote:
            _apply_quote_fields("fmp", fmp_quote)
            _provider_mark_success("fmp")
        else:
            exc = RuntimeError("; ".join(fmp_quote_attempts) if fmp_quote_attempts else "no quote response")
            _provider_mark_failure("fmp", exc)
            errors.append(f"fmp quote: {exc}")

    if fmp_key and _provider_available("fmp") and pe_ratio is None:
        fmp_ratios, _, fmp_ratios_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _fmp_ratios_ttm(candidate, fmp_key),
            require_truthy=True,
        )
        if fmp_ratios:
            _apply_quote_fields("fmp", fmp_ratios)
            _provider_mark_success("fmp")
        else:
            exc = RuntimeError("; ".join(fmp_ratios_attempts) if fmp_ratios_attempts else "no ratios-ttm response")
            _provider_mark_failure("fmp", exc)
            errors.append(f"fmp ratios-ttm: {exc}")

    if fmp_key and _provider_available("fmp") and _need_profile_fields():
        fmp_profile, _, fmp_profile_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _fmp_profile(candidate, fmp_key),
            require_truthy=True,
        )
        if fmp_profile:
            _apply_quote_fields("fmp", fmp_profile)
            _provider_mark_success("fmp")
        else:
            exc = RuntimeError("; ".join(fmp_profile_attempts) if fmp_profile_attempts else "no profile response")
            _provider_mark_failure("fmp", exc)
            errors.append(f"fmp profile: {exc}")

    if fmp_key and _provider_available("fmp") and not history:
        fmp_hist, _, fmp_hist_attempts = _try_symbol_variants(
            sym,
            lambda candidate: _fmp_history(candidate, fmp_key),
            require_truthy=True,
        )
        if fmp_hist:
            history = fmp_hist
            history_source = "fmp"
            _provider_mark_success("fmp")
        else:
            exc = RuntimeError("; ".join(fmp_hist_attempts) if fmp_hist_attempts else "no history response")
            _provider_mark_failure("fmp", exc)
            errors.append(f"fmp history: {exc}")

    need_yahoo_quote = _need_quote_fields()
    need_yahoo_chart = not history
    need_yahoo_intraday = not intraday_history
    if (need_yahoo_quote or need_yahoo_chart or need_yahoo_intraday) and _provider_available("yahoo"):
        row: dict = {}
        yahoo_quote_symbol = sym

        if need_yahoo_quote:
            def _load_yahoo_quote(candidate: str) -> dict:
                quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={candidate}"
                quote_payload = _yahoo_json(quote_url)
                quote_result = (
                    quote_payload.get("quoteResponse", {}).get("result", [])
                    if isinstance(quote_payload, dict) else []
                )
                return quote_result[0] if quote_result and isinstance(quote_result[0], dict) else {}

            quote_row, used_quote_symbol, quote_attempts = _try_symbol_variants(
                sym,
                _load_yahoo_quote,
                require_truthy=True,
            )
            if quote_row:
                row = quote_row
                yahoo_quote_symbol = used_quote_symbol or sym
                _provider_mark_success("yahoo")
            else:
                exc = RuntimeError("; ".join(quote_attempts) if quote_attempts else "no quote response")
                _provider_mark_failure("yahoo", exc)
                errors.append(f"yahoo quote: {exc}")

            _apply_quote_fields(
                "yahoo",
                {
                    "name": row.get("longName") or row.get("shortName") or sym,
                    "price": _to_float(row.get("regularMarketPrice")),
                    "change": _to_float(row.get("regularMarketChange")),
                    "change_percent": _to_float(row.get("regularMarketChangePercent")),
                    "market_cap": _to_float(row.get("marketCap")),
                    "pe_ratio": _to_float(row.get("trailingPE")),
                    "high_52": _to_float(row.get("fiftyTwoWeekHigh")),
                    "low_52": _to_float(row.get("fiftyTwoWeekLow")),
                    "exchange": row.get("fullExchangeName") or row.get("exchange") or "",
                    "previous_close": _to_float(row.get("regularMarketPreviousClose")),
                    "open": _to_float(row.get("regularMarketOpen")),
                    "day_high": _to_float(row.get("regularMarketDayHigh")),
                    "day_low": _to_float(row.get("regularMarketDayLow")),
                    "volume": _to_float(row.get("regularMarketVolume")),
                    "eps": _to_float(row.get("epsTrailingTwelveMonths")),
                    "dividend_yield": _to_float(row.get("trailingAnnualDividendYield")),
                    "sector": row.get("sectorDisp") or "",
                    "industry": row.get("industryDisp") or "",
                    "country": row.get("region") or "",
                    "ipo_date": row.get("firstTradeDateMilliseconds") or "",
                    "post_market_price": _to_float(row.get("postMarketPrice")),
                    "post_market_change": _to_float(row.get("postMarketChange")),
                    "post_market_change_percent": _to_float(row.get("postMarketChangePercent")),
                    "regular_market_time": _to_float(row.get("regularMarketTime")),
                    "post_market_time": _to_float(row.get("postMarketTime")),
                },
            )

            if row and _provider_available("yahoo"):
                summary_url = (
                    f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{yahoo_quote_symbol}"
                    "?modules=assetProfile,summaryDetail,defaultKeyStatistics"
                )
                try:
                    summary_payload = _yahoo_json(summary_url)
                    result_items = (
                        summary_payload.get("quoteSummary", {}).get("result", [])
                        if isinstance(summary_payload, dict) else []
                    )
                    summary = result_items[0] if result_items else {}
                    asset = summary.get("assetProfile", {}) if isinstance(summary, dict) else {}
                    detail = summary.get("summaryDetail", {}) if isinstance(summary, dict) else {}
                    stats = summary.get("defaultKeyStatistics", {}) if isinstance(summary, dict) else {}

                    officers = asset.get("companyOfficers", []) if isinstance(asset, dict) else []
                    ceo_name = ""
                    if isinstance(officers, list):
                        for officer in officers:
                            if not isinstance(officer, dict):
                                continue
                            title = str(officer.get("title", "") or "").lower()
                            if "chief executive officer" in title or title.startswith("ceo"):
                                ceo_name = str(officer.get("name", "") or "").strip()
                                if ceo_name:
                                    break

                    first_trade_raw = row.get("firstTradeDateMilliseconds")
                    ipo_text = ""
                    try:
                        if first_trade_raw is not None:
                            ms = float(first_trade_raw)
                            if ms > 0:
                                ipo_text = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d")
                    except Exception:
                        ipo_text = ""

                    _apply_quote_fields(
                        "yahoo",
                        {
                            "market_cap": _to_float(detail.get("marketCap", {}).get("raw"))
                            if isinstance(detail.get("marketCap"), dict)
                            else _to_float(detail.get("marketCap")),
                            "sector": asset.get("sector") or asset.get("sectorDisp") or "",
                            "industry": asset.get("industry") or asset.get("industryDisp") or "",
                            "country": asset.get("country") or "",
                            "full_time_employees": _to_float(asset.get("fullTimeEmployees")),
                            "ceo": ceo_name,
                            "description": asset.get("longBusinessSummary") or "",
                            "dividend_yield": _to_float(detail.get("dividendYield", {}).get("raw"))
                            if isinstance(detail.get("dividendYield"), dict)
                            else _to_float(detail.get("dividendYield")),
                            "eps": _to_float(stats.get("trailingEps", {}).get("raw"))
                            if isinstance(stats.get("trailingEps"), dict)
                            else _to_float(stats.get("trailingEps")),
                            "shares_outstanding": _to_float(stats.get("sharesOutstanding", {}).get("raw"))
                            if isinstance(stats.get("sharesOutstanding"), dict)
                            else _to_float(stats.get("sharesOutstanding")),
                            "ipo_date": ipo_text,
                        },
                    )
                    _provider_mark_success("yahoo")
                except Exception as e:
                    _provider_mark_failure("yahoo", e)
                    errors.append(f"yahoo summary: {type(e).__name__}: {e}")

        if need_yahoo_chart and _provider_available("yahoo"):
            def _load_yahoo_chart(candidate: str) -> List[dict]:
                chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{candidate}?range=1y&interval=1d"
                chart_payload = _yahoo_json(chart_url)
                chart = chart_payload.get("chart", {}) if isinstance(chart_payload, dict) else {}
                results = chart.get("result", []) if isinstance(chart, dict) else []
                parsed_history: List[dict] = []
                if results:
                    first = results[0] if isinstance(results[0], dict) else {}
                    ts = first.get("timestamp", []) or []
                    q = first.get("indicators", {}).get("quote", []) or []
                    closes = q[0].get("close", []) if q and isinstance(q[0], dict) else []
                    vols = q[0].get("volume", []) if q and isinstance(q[0], dict) else []
                    for i, t in enumerate(ts):
                        try:
                            c = closes[i]
                        except Exception:
                            c = None
                        if c is None:
                            continue
                        try:
                            dt = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d")
                        except Exception:
                            continue
                        vol = _to_float(vols[i], 0.0) if i < len(vols) else 0.0
                        parsed_history.append({"date": dt, "close": float(c), "volume": vol})
                return parsed_history

            parsed_history, _, chart_attempts = _try_symbol_variants(
                sym,
                _load_yahoo_chart,
                require_truthy=True,
            )
            if parsed_history:
                history = parsed_history
                history_source = "yahoo"
                _provider_mark_success("yahoo")
            else:
                exc = RuntimeError("; ".join(chart_attempts) if chart_attempts else "no chart response")
                _provider_mark_failure("yahoo", exc)
                errors.append(f"yahoo chart: {exc}")

        if need_yahoo_intraday and _provider_available("yahoo"):
            def _load_yahoo_intraday(candidate: str) -> List[dict]:
                chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{candidate}?range=1d&interval=30m&includePrePost=true"
                chart_payload = _yahoo_json(chart_url)
                chart = chart_payload.get("chart", {}) if isinstance(chart_payload, dict) else {}
                results = chart.get("result", []) if isinstance(chart, dict) else []
                parsed_intraday: List[dict] = []
                if results:
                    first = results[0] if isinstance(results[0], dict) else {}
                    ts = first.get("timestamp", []) or []
                    q = first.get("indicators", {}).get("quote", []) or []
                    closes = q[0].get("close", []) if q and isinstance(q[0], dict) else []
                    vols = q[0].get("volume", []) if q and isinstance(q[0], dict) else []
                    for i, t in enumerate(ts):
                        try:
                            c = closes[i]
                        except Exception:
                            c = None
                        if c is None:
                            continue
                        try:
                            dt = datetime.fromtimestamp(int(t), tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                        except Exception:
                            continue
                        vol = _to_float(vols[i], 0.0) if i < len(vols) else 0.0
                        parsed_intraday.append({"date": dt, "close": float(c), "volume": vol})
                return parsed_intraday

            parsed_intraday, _, intraday_attempts = _try_symbol_variants(
                sym,
                _load_yahoo_intraday,
                require_truthy=True,
            )
            if parsed_intraday:
                intraday_history = parsed_intraday
                intraday_history_source = "yahoo"
                _provider_mark_success("yahoo")
            else:
                exc = RuntimeError("; ".join(intraday_attempts) if intraday_attempts else "no intraday chart response")
                _provider_mark_failure("yahoo", exc)
                errors.append(f"yahoo intraday: {exc}")

    # Free-source fallback: Stooq daily snapshot can reliably fill
    # open/high/low/volume when mainstream quote APIs are rate-limited.
    if any(v is None for v in (open_price, day_high, day_low, volume)) and _provider_available("stooq"):
        try:
            stooq_snap = _stooq_snapshot(sym)
            if stooq_snap:
                _apply_quote_fields("stooq", stooq_snap)
                _provider_mark_success("stooq")
        except Exception as e:
            _provider_mark_failure("stooq", e)
            errors.append(f"stooq snapshot: {type(e).__name__}: {e}")

    # Free-source fallback: populate company profile fields via Wikidata
    # when Yahoo/FMP profile calls are unavailable.
    if _need_profile_fields():
        try:
            wd_profile = _wikidata_profile(sym)
            if wd_profile:
                _apply_quote_fields("wikidata", wd_profile)
        except Exception as e:
            errors.append(f"wikidata profile: {type(e).__name__}: {e}")

    if not history:
        stooq_history = _stooq_history(sym)
        if stooq_history:
            history = stooq_history
            history_source = "stooq"

    if (price is None or change is None or change_percent is None) and len(history) >= 2:
        last_close = history[-1]["close"]
        prev_close = history[-2]["close"]
        delta = float(last_close) - float(prev_close)
        pct = (delta / float(prev_close) * 100.0) if float(prev_close) != 0 else None
        if price is None:
            price = float(last_close)
        if change is None:
            change = delta
        if change_percent is None:
            change_percent = pct
        if not quote_source:
            quote_source = history_source or "derived"

    if change_percent is None and change is not None and previous_close not in (None, 0):
        change_percent = (float(change) / float(previous_close)) * 100.0
    if change is None and price is not None and previous_close is not None:
        change = float(price) - float(previous_close)
    if previous_close is None and price is not None and change is not None:
        previous_close = float(price) - float(change)

    if (market_cap is None or float(market_cap) <= 0) and shares_outstanding not in (None, 0) and price is not None:
        market_cap = float(shares_outstanding) * float(price)

    if price is None and not history:
        stale_cached = _stock_cache_get_stale(cache_symbol)
        if stale_cached:
            stale_cached["providers"] = _provider_snapshot(["twelvedata", "fmp", "yahoo"])
            stale_cached["warning"] = (
                "Upstream providers temporarily returned no data. "
                f"Showing stale cache ({int(stale_cached.get('cache_age_s', 0) or 0)}s old)."
            )
            return stale_cached
        detail = "; ".join(errors) if errors else "no data returned by upstream providers"
        return {"error": f"Failed to fetch stock data: {detail}"}

    out = {
        "symbol": sym,
        "name": name,
        "price": price,
        "change": change,
        "change_percent": change_percent,
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "high_52": high_52,
        "low_52": low_52,
        "exchange": exchange,
        "previous_close": previous_close,
        "open": open_price,
        "day_high": day_high,
        "day_low": day_low,
        "volume": volume,
        "eps": eps,
        "dividend_yield": dividend_yield,
        "sector": sector,
        "industry": industry,
        "country": country,
        "full_time_employees": full_time_employees,
        "ceo": ceo,
        "description": long_description,
        "ipo_date": ipo_date,
        "post_market_price": post_market_price,
        "post_market_change": post_market_change,
        "post_market_change_percent": post_market_change_percent,
        "regular_market_time": regular_market_time,
        "post_market_time": post_market_time,
        "history": history,
        "intraday_history": intraday_history,
        "quote_source": quote_source or "",
        "history_source": history_source or "",
        "intraday_history_source": intraday_history_source or "",
        "providers": _provider_snapshot(["twelvedata", "fmp", "yahoo"]),
        "cache_hit": False,
        "cache_age_s": 0,
        "error": "",
        "lite": False,
    }
    if errors and (price is not None or bool(history)):
        out["warning"] = "Live refresh partially degraded; showing best available merged data."
    _stock_cache_set(cache_symbol, out)
    return out


def _normalize_image_url(raw_url: str, base_url: str = "") -> str:
    val = str(raw_url or "").strip()
    if not val:
        return ""
    if val.startswith("data:"):
        return ""
    if val.startswith("//"):
        return f"{(urlparse(base_url).scheme or 'https')}:{val}" if base_url else f"https:{val}"
    if val.startswith("http://") or val.startswith("https://"):
        return val
    if base_url:
        try:
            return urljoin(base_url, val)
        except Exception:
            return ""
    return ""


def _extract_og_image(article_url: str) -> str:
    url = str(article_url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return ""

    req = Request(
        url,
        headers={
            "User-Agent": "RiskLens/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    try:
        with urlopen(req, timeout=6) as resp:
            raw_html = resp.read(280_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    tags = re.findall(r"<meta\\s+[^>]*>", raw_html, flags=re.IGNORECASE)
    for tag in tags:
        lower = tag.lower()
        if "og:image" not in lower and "twitter:image" not in lower:
            continue
        m = re.search(r"content\\s*=\\s*(['\\\"])(.*?)\\1", tag, flags=re.IGNORECASE)
        if not m:
            continue
        candidate = _normalize_image_url(m.group(2), url)
        if candidate:
            return candidate
    return ""


def _news_image_from_row(item: dict, article_url: str, og_cache: Dict[str, str], og_state: Dict[str, int]) -> str:
    if not isinstance(item, dict):
        return ""

    candidates: List[str] = []
    for key in ("image_url", "image", "imageUrl", "thumbnail", "photo_url"):
        candidates.append(str(item.get(key) or "").strip())

    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    if isinstance(source, dict):
        for key in ("image_url", "logo_url", "icon_url"):
            candidates.append(str(source.get(key) or "").strip())

    entities = item.get("entities")
    if isinstance(entities, list):
        for entity in entities[:4]:
            if not isinstance(entity, dict):
                continue
            for key in ("image_url", "image", "logo_url"):
                candidates.append(str(entity.get(key) or "").strip())

    for raw in candidates:
        normalized = _normalize_image_url(raw, article_url)
        if normalized:
            return normalized

    article = str(article_url or "").strip()
    if not article:
        return ""
    if article in og_cache:
        return og_cache[article]
    if og_state.get("attempts", 0) >= 6:
        og_cache[article] = ""
        return ""

    og_state["attempts"] = og_state.get("attempts", 0) + 1
    found = _extract_og_image(article)
    og_cache[article] = found
    return found


def _compact_error_text(value: Any, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _env_token_pool(*names: str) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for name in names:
        raw = _env(name, "")
        if not raw:
            continue
        for part in re.split(r"[,\n; ]+", str(raw)):
            token = part.strip()
            if not token or token in seen:
                continue
            seen.add(token)
            out.append(token)
    return out


def _news_cache_key(company: str, ticker: str, days: int, limit: int) -> str:
    return "|".join(
        [
            "v2",
            str(company or "").strip().lower(),
            str(ticker or "").strip().upper(),
            str(days),
            str(limit),
        ]
    )


def _cache_news_items(key: str, items: List[Dict[str, Any]], provider: str) -> None:
    _NEWS_CACHE[key] = {
        "ts": time.time(),
        "items": list(items or []),
        "provider": provider,
    }

    # Keep cache bounded to avoid unbounded growth on long-lived workers.
    if len(_NEWS_CACHE) > 180:
        oldest_key = min(_NEWS_CACHE.items(), key=lambda kv: float(kv[1].get("ts", 0) or 0))[0]
        _NEWS_CACHE.pop(oldest_key, None)


def _cached_news_items(key: str) -> Optional[Dict[str, Any]]:
    row = _NEWS_CACHE.get(key)
    if not row:
        return None
    ts = float(row.get("ts", 0) or 0)
    if time.time() - ts > _NEWS_CACHE_TTL_SECONDS:
        _NEWS_CACHE.pop(key, None)
        return None
    return row


def _provider_error(provider: str, message: str) -> str:
    msg = _compact_error_text(message)
    return f"{provider}: {msg}" if msg else f"{provider}: request failed"


def _fetch_marketaux_rows(company: str, ticker: str, day_window: int, limit_value: int) -> Dict[str, Any]:
    tokens = _env_token_pool(
        "MARKETAUX_API_TOKEN",
        "MARKETAUX_API_TOKENS",
        "MARKETAUX_API_TOKEN_2",
        "MARKETAUX_API_TOKEN_3",
    )
    if not tokens:
        return {"ok": False, "rows": [], "error": "MARKETAUX_API_TOKEN is not configured."}

    params_base = {
        "language": "en",
        "sort": "published_desc",
        "limit": limit_value,
        "published_after": (datetime.utcnow() - timedelta(days=day_window)).strftime("%Y-%m-%d"),
    }
    if ticker:
        params_base["symbols"] = str(ticker).strip().upper()
    elif company:
        params_base["search"] = str(company).strip()

    last_error = ""
    for token in tokens:
        params = dict(params_base)
        params["api_token"] = token
        url = f"https://api.marketaux.com/v1/news/all?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": "RiskLens/1.0"}, method="GET")

        try:
            with urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []
            return {"ok": True, "rows": rows, "error": ""}
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                detail = str(e)
            last_error = _provider_error("marketaux", f"HTTP {e.code}: {detail}")
            continue
        except URLError as e:
            last_error = _provider_error("marketaux", f"network error: {e}")
            continue
        except Exception as e:
            last_error = _provider_error("marketaux", f"{type(e).__name__}: {e}")
            continue

    return {"ok": False, "rows": [], "error": last_error or _provider_error("marketaux", "all keys failed")}


def _fetch_thenewsapi_rows(company: str, ticker: str, day_window: int, limit_value: int) -> Dict[str, Any]:
    tokens = _env_token_pool(
        "THENEWSAPI_TOKEN",
        "THENEWSAPI_API_TOKEN",
        "THENEWSAPI_KEY",
        "TheNewsAPI_KEY",
    )
    if not tokens:
        return {"ok": False, "rows": [], "error": "THENEWSAPI_TOKEN is not configured."}

    search_terms: List[str] = []
    if ticker:
        search_terms.append(str(ticker).strip().upper())
    if company:
        search_terms.append(str(company).strip())
    search_query = " OR ".join([t for t in search_terms if t])

    params_base = {
        "language": "en",
        "sort": "published_at",
        "limit": limit_value,
        "published_after": (datetime.utcnow() - timedelta(days=day_window)).strftime("%Y-%m-%d"),
    }
    if search_query:
        params_base["search"] = search_query

    last_error = ""
    for token in tokens:
        params = dict(params_base)
        params["api_token"] = token
        url = f"https://api.thenewsapi.com/v1/news/all?{urlencode(params)}"
        req = Request(url, headers={"User-Agent": "RiskLens/1.0"}, method="GET")

        try:
            with urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            rows = []
            if isinstance(payload, dict):
                rows = payload.get("data", payload.get("articles", []))
            if not isinstance(rows, list):
                rows = []
            return {"ok": True, "rows": rows, "error": ""}
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                detail = str(e)
            last_error = _provider_error("thenewsapi", f"HTTP {e.code}: {detail}")
            continue
        except URLError as e:
            last_error = _provider_error("thenewsapi", f"network error: {e}")
            continue
        except Exception as e:
            last_error = _provider_error("thenewsapi", f"{type(e).__name__}: {e}")
            continue

    return {"ok": False, "rows": [], "error": last_error or _provider_error("thenewsapi", "all keys failed")}


def _fetch_currents_rows(company: str, ticker: str, limit_value: int) -> Dict[str, Any]:
    tokens = _env_token_pool(
        "CURRENTS_API_KEY",
        "CURRENTS_TOKEN",
        "Currents_API_KEY",
    )
    if not tokens:
        return {"ok": False, "rows": [], "error": "CURRENTS_API_KEY is not configured."}

    keywords = str(ticker or company or "").strip()
    if keywords:
        base_url = "https://api.currentsapi.services/v1/search"
        params_base = {"language": "en", "keywords": keywords, "page_size": limit_value}
    else:
        base_url = "https://api.currentsapi.services/v1/latest-news"
        params_base = {"language": "en"}

    last_error = ""
    for token in tokens:
        url = f"{base_url}?{urlencode(params_base)}"
        headers = {"User-Agent": "RiskLens/1.0", "Authorization": f"Bearer {token}"}
        req = Request(url, headers=headers, method="GET")

        try:
            with urlopen(req, timeout=25) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
            rows = payload.get("news", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []
            return {"ok": True, "rows": rows, "error": ""}
        except HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="ignore")
            except Exception:
                detail = str(e)
            last_error = _provider_error("currents", f"HTTP {e.code}: {detail}")
            continue
        except URLError as e:
            last_error = _provider_error("currents", f"network error: {e}")
            continue
        except Exception as e:
            last_error = _provider_error("currents", f"{type(e).__name__}: {e}")
            continue

    return {"ok": False, "rows": [], "error": last_error or _provider_error("currents", "all keys failed")}


def _normalize_news_row(item: dict, provider: str, og_cache: Dict[str, str], og_state: Dict[str, int]) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    title = ""
    summary = ""
    description = ""
    snippet = ""
    published_at = ""
    article_url = ""
    source_name = ""

    if provider == "marketaux":
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        summary = description or snippet
        published_at = str(item.get("published_at") or item.get("publishedAt") or "").strip()
        article_url = str(item.get("url") or item.get("link") or "").strip()
    elif provider == "thenewsapi":
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        summary = description or snippet
        published_at = str(item.get("published_at") or item.get("publishedAt") or "").strip()
        article_url = str(item.get("url") or item.get("link") or "").strip()
    elif provider == "currents":
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        if not source_name:
            source_name = item.get("author") or ""
        title = str(item.get("title") or "").strip()
        description = str(item.get("description") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        summary = description or snippet
        published_at = str(item.get("published") or item.get("published_at") or "").strip()
        article_url = str(item.get("url") or item.get("link") or "").strip()
    else:
        return None

    # Upstream providers often truncate `description`; merge with `snippet`
    # when they contain different fragments so Market Summary reads complete.
    desc = str(description or "").strip()
    snip = str(snippet or "").strip()
    if desc and snip:
        if snip not in desc and desc not in snip:
            summary = f"{desc} {snip}".strip()
        else:
            summary = desc if len(desc) >= len(snip) else snip
    else:
        summary = desc or snip or summary

    if not title and not summary:
        return None

    image_url = _news_image_from_row(item, article_url, og_cache, og_state)

    return {
        "title": title,
        "summary": summary,
        "published_at": published_at,
        "url": article_url,
        "source": str(source_name or "Unknown"),
        "image_url": image_url or "",
    }


def _parse_news_timestamp(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        # Typical API shape: 2026-05-16T14:33:10.000000Z
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _news_relevance_score(item: dict, company: str, ticker: str) -> int:
    if not isinstance(item, dict):
        return 0
    hay = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("summary") or ""),
            str(item.get("source") or ""),
        ]
    ).lower()
    score = 0
    tk = str(ticker or "").strip().upper()
    if tk and tk.lower() in hay:
        score += 3
    comp = str(company or "").strip().lower()
    if comp:
        if comp in hay:
            score += 3
        tokens = [w for w in re.split(r"[^a-z0-9]+", comp) if len(w) >= 3]
        score += sum(1 for w in tokens[:4] if w in hay)
    return score


def _fetch_news(company: str, ticker: str, days: int, limit: int):
    company_norm = str(company or "").strip()
    ticker_norm = str(ticker or "").strip().upper()
    day_window = max(1, min(int(days or 30), 365))
    limit_value = max(1, min(int(limit or 20), 50))

    cache_key = _news_cache_key(company_norm, ticker_norm, day_window, limit_value)
    cached = _cached_news_items(cache_key)
    if cached:
        return {
            "error": "",
            "items": list(cached.get("items", []) or []),
            "provider": str(cached.get("provider") or "cache"),
            "cached": True,
        }

    providers = [
        ("marketaux", lambda: _fetch_marketaux_rows(company_norm, ticker_norm, day_window, limit_value)),
        ("thenewsapi", lambda: _fetch_thenewsapi_rows(company_norm, ticker_norm, day_window, limit_value)),
        ("currents", lambda: _fetch_currents_rows(company_norm, ticker_norm, limit_value)),
    ]

    provider_errors: List[str] = []
    had_successful_response = False

    for provider_name, fetcher in providers:
        result = fetcher()
        rows = result.get("rows", []) if isinstance(result, dict) else []
        ok = bool(result.get("ok")) if isinstance(result, dict) else False
        err = str(result.get("error") or "").strip() if isinstance(result, dict) else ""

        if ok:
            had_successful_response = True

        if not rows:
            if err:
                provider_errors.append(err)
            continue

        og_cache: Dict[str, str] = {}
        og_state = {"attempts": 0}
        out: List[Dict[str, Any]] = []
        for item in rows:
            normalized = _normalize_news_row(item, provider_name, og_cache, og_state)
            if normalized:
                out.append(normalized)

        if out:
            now_utc = datetime.now(timezone.utc)
            floor_dt = now_utc - timedelta(days=day_window + 1)
            ceil_dt = now_utc + timedelta(days=1)

            # 1) Hard time-window sanity filtering.
            out = [
                row
                for row in out
                if (
                    (lambda dt: bool(dt and floor_dt <= dt <= ceil_dt))(
                        _parse_news_timestamp(row.get("published_at"))
                    )
                )
            ]

            # 2) Relevance filtering when company/ticker is specified.
            if (company_norm or ticker_norm) and out:
                scored = [(row, _news_relevance_score(row, company_norm, ticker_norm)) for row in out]
                out = [row for row, s in scored if s >= 2]

            if not out:
                continue

            # 3) Keep newest first and enforce requested cap.
            out.sort(
                key=lambda row: (
                    _parse_news_timestamp(row.get("published_at")) or datetime.min.replace(tzinfo=timezone.utc)
                ),
                reverse=True,
            )
            out = out[:limit_value]
            _cache_news_items(cache_key, out, provider_name)
            return {"error": "", "items": out, "provider": provider_name, "cached": False}

    if had_successful_response:
        _cache_news_items(cache_key, [], "empty")
        return {"error": "", "items": [], "provider": "empty", "cached": False}

    if provider_errors:
        return {"error": " | ".join(provider_errors[:3]), "items": []}
    return {"error": "No news provider is configured.", "items": []}


def _allowed_origins() -> Set[str]:
    raw = _env("CORS_ALLOW_ORIGINS", "")
    if not raw.strip():
        # Safe default for early integration stage; tighten later in production.
        return {"*"}
    origins = set()
    for part in raw.split(","):
        v = part.strip()
        if v:
            origins.add(v)
    return origins


def _cors_origin_for_request(request_headers) -> Optional[str]:
    origin = request_headers.get("Origin")
    if not origin:
        return None

    allowed = _allowed_origins()
    if "*" in allowed:
        return "*"
    if origin in allowed:
        return origin
    return None


def _get_run_agent():
    global _RUN_AGENT
    if _RUN_AGENT is None:
        from agent import run_agent as _imported_run_agent

        _RUN_AGENT = _imported_run_agent
    return _RUN_AGENT


def _get_run_chat_agent():
    global _RUN_CHAT_AGENT
    if _RUN_CHAT_AGENT is None:
        from chat_agent import run_chat_agent as _imported_run_chat_agent

        _RUN_CHAT_AGENT = _imported_run_chat_agent
    return _RUN_CHAT_AGENT


def _get_llm_invoke():
    """Chat-agent LLM invoker (DeepSeek by default). Used by chat / Q&A /
    polishing paths."""
    global _LLM_INVOKE
    if _LLM_INVOKE is None:
        from agent import invoke_llm_text as _imported_invoke

        _LLM_INVOKE = _imported_invoke
    return _LLM_INVOKE


def _get_extraction_llm_invoke():
    """Extraction-side LLM invoker (Nova Pro by default). Used by the
    9-bucket classification fallback. Falls back to the chat invoker if
    the agent module is too old to expose ``invoke_llm_extraction``."""
    global _LLM_EXTRACTION_INVOKE
    if _LLM_EXTRACTION_INVOKE is None:
        try:
            from agent import invoke_llm_extraction as _imported_extraction_invoke

            _LLM_EXTRACTION_INVOKE = _imported_extraction_invoke
        except Exception:
            _LLM_EXTRACTION_INVOKE = _get_llm_invoke()
    return _LLM_EXTRACTION_INVOKE


def _get_llm_invoke_with_tools():
    """ReAct-orchestrator LLM invoker — wraps Bedrock Converse with
    ``toolConfig`` for the chat agent's multi-step loop. Returns the
    callable from ``agent.invoke_llm_with_tools`` so chat_agent can
    consume it without importing agent directly."""
    global _LLM_INVOKE_WITH_TOOLS
    if _LLM_INVOKE_WITH_TOOLS is None:
        from agent import invoke_llm_with_tools as _imported_with_tools

        _LLM_INVOKE_WITH_TOOLS = _imported_with_tools
    return _LLM_INVOKE_WITH_TOOLS


def _get_model_id() -> str:
    """Chat-agent model id (DeepSeek by default). Surfaced in chat_context."""
    global _MODEL_ID
    if _MODEL_ID is None:
        try:
            from agent import get_model_id as _imported_get_model_id

            _MODEL_ID = str(_imported_get_model_id() or "").strip() or "deepseek.v3-v1:0"
        except Exception:
            _MODEL_ID = "deepseek.v3-v1:0"
    return _MODEL_ID


def _get_extraction_model_id() -> str:
    """Extraction-side model id (Nova Pro by default). Surfaced in
    chat_context so identity replies can mention both."""
    global _EXTRACTION_MODEL_ID
    if _EXTRACTION_MODEL_ID is None:
        try:
            from agent import get_extraction_model_id as _imported_get_extraction_model_id

            _EXTRACTION_MODEL_ID = str(_imported_get_extraction_model_id() or "").strip() or "us.amazon.nova-pro-v1:0"
        except Exception:
            _EXTRACTION_MODEL_ID = "us.amazon.nova-pro-v1:0"
    return _EXTRACTION_MODEL_ID


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _coerce_payload(payload):
    if payload is None:
        return {}

    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = json.loads(payload.decode("utf-8", errors="ignore"))
        except Exception:
            return {}

    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"prompt": payload}
        except Exception:
            payload = {"prompt": payload}

    if not isinstance(payload, dict):
        return {}

    if "body" in payload:
        body = payload.get("body")
        if payload.get("isBase64Encoded") and isinstance(body, str):
            try:
                body = base64.b64decode(body).decode("utf-8", errors="ignore")
            except Exception:
                body = ""

        if isinstance(body, str):
            try:
                decoded = json.loads(body)
                if isinstance(decoded, dict):
                    payload = decoded
                else:
                    payload = {"prompt": body}
            except Exception:
                payload = {"prompt": body}
        elif isinstance(body, dict):
            payload = body

    candidate = payload.get("input", payload)
    if isinstance(candidate, dict):
        return candidate

    if isinstance(candidate, str):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"prompt": candidate}

    return {}


def _invoke_logic(raw_payload):
    req = _coerce_payload(raw_payload)
    aws_ctx = req.get("_aws", {}) if isinstance(req, dict) else {}
    if isinstance(aws_ctx, dict):
        access_key = str(aws_ctx.get("aws_access_key_id", "")).strip()
        secret_key = str(aws_ctx.get("aws_secret_access_key", "")).strip()
        session_token = str(aws_ctx.get("aws_session_token", "")).strip()
        bedrock_region = str(aws_ctx.get("bedrock_region", "")).strip()
        if access_key and secret_key:
            os.environ["AWS_ACCESS_KEY_ID"] = access_key
            os.environ["AWS_SECRET_ACCESS_KEY"] = secret_key
            if session_token:
                os.environ["AWS_SESSION_TOKEN"] = session_token
            else:
                os.environ.pop("AWS_SESSION_TOKEN", None)
        if bedrock_region:
            os.environ["BEDROCK_REGION"] = bedrock_region

    user_query = req.get("user_query") or req.get("prompt") or ""
    company = req.get("company", "")
    year = _to_int(req.get("year", 0), default=0)
    risks = req.get("risks", [])
    compare_data = req.get("compare_data")

    print(
        "[runtime] parsed request meta:",
        json.dumps(
            {
                "has_company": bool(company),
                "year": year,
                "has_user_query": bool(user_query),
                "risk_count": len(risks) if isinstance(risks, list) else -1,
                "raw_keys": list(raw_payload.keys()) if isinstance(raw_payload, dict) else str(type(raw_payload)),
                "parsed_keys": list(req.keys()) if isinstance(req, dict) else [],
            },
            ensure_ascii=False,
        ),
    )

    run_agent = _get_run_agent()
    return run_agent(
        user_query=user_query,
        company=company,
        year=year,
        risks=risks,
        compare_data=compare_data,
    )


def _compare_payload(
    latest_record_id: str,
    prior_record_id: str,
    *,
    mode: str = "yoy",
    threshold_low: Optional[float] = None,
    threshold_high: Optional[float] = None,
) -> dict:
    latest = _load_result(latest_record_id)
    prior = _load_result(prior_record_id)
    if not isinstance(latest, dict) or not isinstance(prior, dict):
        return {"error": "Invalid record ids for compare."}

    latest = _result_with_dashboard_categories(latest)
    prior = _result_with_dashboard_categories(prior)

    # Same-record edge case: short-circuit so the assignment solver
    # doesn't waste cycles matching every item against its twin.
    if latest_record_id == prior_record_id:
        items = _extract_sub_risks(latest)
        return {
            "latest_record_id": latest_record_id,
            "prior_record_id": prior_record_id,
            "mode": mode,
            "scoring": {"threshold_low": 1.0, "threshold_high": 1.0, "method": "identity"},
            "pairs": {
                "retained": [
                    {"prior": x, "latest": x, "score": 1.0, "bucket": x.get("dashboard_category", ""),
                     "title_changed": False, "diff": {"added": [], "removed": []}, "components": {}}
                    for x in items
                ],
                "modified": [], "added": [], "removed": [], "candidates": [],
            },
            "category_matrix": [],
            "summary": {
                "retained": len(items), "modified": 0, "added": 0, "removed": 0,
                "prior_total": len(items), "latest_total": len(items),
                "churn_rate": 0.0, "avg_match_score": 1.0,
                "new_count": 0, "removed_count": 0,
            },
            "new_risks": [],
            "removed_risks": [],
        }

    # Try to use the embedding service. If anything is misconfigured
    # `compare_embedding.build_lookup()` returns a callable that yields
    # None for every title, which makes `compare_risks` fall back to
    # the lexical-only formula transparently.
    embed_lookup = None
    try:
        from core.compare_embedding import build_lookup as _build_embed_lookup, is_enabled as _embed_enabled, warm as _embed_warm
        if _embed_enabled():
            titles = []
            for src in (prior, latest):
                for block in src.get("risks", []) or []:
                    if not isinstance(block, dict):
                        continue
                    for sr in block.get("sub_risks", []) or []:
                        t = sr.get("title") if isinstance(sr, dict) else sr
                        t = str(t or "").strip()
                        if t:
                            titles.append(t)
            _embed_warm(titles)
            embed_lookup = _build_embed_lookup()
    except Exception as exc:
        print(f"[compare] embedding lookup unavailable: {type(exc).__name__}: {exc}")
        embed_lookup = None

    if compare_risks is None:
        return {"error": "Compare module unavailable in this runtime."}

    diff = compare_risks(
        prior,
        latest,
        mode=mode,
        threshold_low=threshold_low,
        threshold_high=threshold_high,
        embed_lookup=embed_lookup,
    )

    diff["latest_record_id"] = latest_record_id
    diff["prior_record_id"] = prior_record_id
    return diff


def _coerce_chat_history(raw_history: Any) -> List[dict]:
    out: List[dict] = []
    if not isinstance(raw_history, list):
        return out
    for row in raw_history:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "") or "").strip().lower()
        text = str(row.get("text", "") or row.get("content", "") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        out.append({"role": role, "text": text[:1200]})
    return out[-16:]


def _extract_ticker_candidate(text: str) -> str:
    q = str(text or "")
    if not q:
        return ""
    tokens = re.findall(r"\$?([A-Za-z]{1,5})\b", q)
    if not tokens:
        return ""
    stop = {
        "the", "and", "for", "with", "from", "this", "that", "what", "when", "where", "which",
        "will", "would", "could", "should", "stock", "stocks", "risk", "news", "query", "page",
        "about", "today", "price", "chart", "market",
    }
    for tok in tokens:
        norm = tok.upper()
        if tok.lower() in stop:
            continue
        if norm.isalpha():
            return norm
    return ""


def _resolve_agent_ticker(
    *,
    user_query: str,
    company: str,
    context_ticker: str,
) -> str:
    from_query = _normalize_ticker(_extract_ticker_candidate(user_query))
    if from_query:
        return from_query

    from_context = _normalize_ticker(context_ticker)
    if from_context:
        return from_context

    if company:
        try:
            resolved = _resolve_ticker_for_company(company=company, ticker_hint="")
            if resolved.get("ok"):
                return _normalize_ticker(resolved.get("ticker"))
        except Exception:
            pass
    return ""


def _strip_markdown_artifacts(text: str) -> str:
    s = str(text or "")
    s = s.replace("**", "")
    s = s.replace("__", "")
    s = s.replace("`", "")
    s = s.replace("### ", "")
    s = s.replace("## ", "")
    s = s.replace("# ", "")
    return s.strip()


def _is_chinese_text(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(text or "")))


def _detect_target_lang(user_query: str, history: List[dict]) -> str:
    q = str(user_query or "").strip()
    if _is_chinese_text(q):
        return "zh"
    if q:
        return "en"
    for row in reversed(history or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("role", "") or "").strip().lower() != "user":
            continue
        text = str(row.get("text", "") or "").strip()
        if not text:
            continue
        return "zh" if _is_chinese_text(text) else "en"
    return "en"


def _is_spanish_like(text: str) -> bool:
    t = str(text or "").strip().lower()
    if not t:
        return False
    if len(re.findall(r"[áéíóúñ¿¡]", t)) >= 2:
        return True
    tokens = [x.lower() for x in re.findall(r"[A-Za-zÀ-ÿ']+", t)]
    if len(tokens) < 6:
        return False
    hints = {
        "el", "la", "los", "las", "de", "del", "que", "por", "para", "con", "sin", "una", "uno",
        "como", "pero", "muy", "más", "sus", "sobre", "entre", "cuando", "donde", "porque", "hola",
        "gracias", "buenos", "buenas", "usted", "ustedes", "hoy", "mañana", "riesgo", "noticias",
    }
    hit = sum(1 for tok in tokens if tok in hints)
    return hit >= 3 and (hit / max(1, len(tokens))) >= 0.18


def _looks_like_target_lang(text: str, target_lang: str) -> bool:
    t = str(text or "").strip()
    if not t:
        return True
    if target_lang == "zh":
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", t))
        latin_count = len(re.findall(r"[A-Za-z]", t))
        if cjk_count >= 1:
            return True
        if latin_count <= 4 and len(t) <= 8:
            return True
        return False
    if target_lang == "en":
        if _is_chinese_text(t):
            return False
        if _is_spanish_like(t):
            return False
        return True
    return True


def _chatbot_help_query(payload: dict) -> dict:
    user_query = str(payload.get("user_query", "") or "").strip()
    history = _coerce_chat_history(payload.get("history", []))
    target_lang = _detect_target_lang(user_query, history)
    lang_label = "Simplified Chinese" if target_lang == "zh" else "English"

    if not user_query:
        empty_reply = (
            "你可以问我如何使用 RiskLens 的页面和功能，比如：上传 10-K、做风险对比、看 Dashboard。"
            if target_lang == "zh"
            else "You can ask me how to use RiskLens pages and workflows, such as upload, compare, and dashboard."
        )
        return {"ok": True, "mode": "product_help", "answer": empty_reply, "target_lang": target_lang}

    history_text = "\n".join(
        f"{str(row.get('role', '')).strip()}: {str(row.get('text', '')).strip()}"
        for row in history[-10:]
        if isinstance(row, dict)
    ) or "(none)"

    prompt = f"""You are the RiskLens Product Assistant.
Primary purpose: help users understand how to use this app.

Product modules you can explain:
- Upload & Records
- Stock
- News
- Dashboard
- Compare
- Tables
- Agent (main analysis chat)

Rules:
- Answer in {lang_label} only.
- Be concise, practical, and friendly.
- Focus on product usage guidance and workflows (what to click, where to go next, typical sequence).
- Do not claim that you already ran analysis or fetched live market/news data in this chat.
- If user asks for actual risk/stock/news analysis, redirect them to the main Agent chat or the relevant page with one clear next step.
- Avoid mentioning internal implementation details unless user asks directly.

Recent conversation:
{history_text}

User question:
{user_query}

Return plain text only."""

    try:
        llm_invoke = _get_llm_invoke()
        answer = str(llm_invoke(prompt, 700) or "").strip()
    except Exception as exc:
        fallback = (
            f"我暂时无法回答这个使用问题：{exc}。请稍后重试，或直接告诉我你当前页面和目标，我给你步骤。"
            if target_lang == "zh"
            else f"I could not answer this product-help question right now: {exc}. Please retry, or tell me your current page and goal for step-by-step guidance."
        )
        return {"ok": True, "mode": "product_help", "answer": fallback, "target_lang": target_lang}

    cleaned = _strip_markdown_artifacts(answer)
    if not cleaned:
        cleaned = (
            "你可以告诉我你的目标（例如：上传 10-K 并对比两年风险），我会按页面给你最短操作路径。"
            if target_lang == "zh"
            else "Tell me your goal (for example: upload a 10-K and compare risk across years), and I will give you the shortest page-by-page path."
        )

    return {
        "ok": True,
        "mode": "product_help",
        "answer": cleaned,
        "target_lang": target_lang,
    }


def _agent_query(payload: dict) -> dict:
    user_query = str(payload.get("user_query", "") or "").strip()
    company = str(payload.get("company", "") or "").strip()
    year = _to_int(payload.get("year", 0), 0)
    record_id = str(payload.get("record_id", "") or "").strip()
    compare_record_id = str(payload.get("compare_record_id", "") or "").strip()
    history = _coerce_chat_history(payload.get("history", []))

    selected_record = None
    selected_result = None

    if record_id:
        selected_result = _load_result(record_id)
        selected_record = next((r for r in _load_index() if str(r.get("record_id", "")) == record_id), None)
        if selected_record:
            company = company or str(selected_record.get("company", "") or "")
            year = year or _to_int(selected_record.get("year", 0), 0)

    if (not selected_result) and company and year:
        rec = _find_record(company, year)
        if rec:
            selected_record = rec
            record_id = str(rec.get("record_id", "") or "")
            selected_result = _load_result(record_id)

    ticker_lookup = _build_ticker_lookup()
    context_ticker = ""
    if isinstance(selected_record, dict):
        context_ticker = _resolve_record_ticker(selected_record, ticker_lookup=ticker_lookup)
    context_ticker = _normalize_ticker(context_ticker)
    context_ticker = context_ticker or _normalize_ticker(str(payload.get("ticker", "") or "").strip().upper())

    risks = []
    if isinstance(selected_result, dict):
        risks = selected_result.get("risks", []) if isinstance(selected_result.get("risks"), list) else []

    compare_data = None
    if compare_record_id and record_id:
        cmp_payload = _compare_payload(record_id, compare_record_id)
        if "error" not in cmp_payload:
            compare_data = cmp_payload

    llm_invoke = _get_llm_invoke()

    # ── ReAct wiring (entry 43, AGENT_UPGRADE_PLAN.md Step 4) ────────────
    # The router_v2 closure tools are gone; chat_agent now runs a Bedrock
    # Converse `toolUse` loop over six stateless handlers from agent_tools.
    # The previous `_polish_business_answer` is no longer applied (the LLM
    # produces the final natural-language answer directly inside the loop;
    # an extra polish pass would risk drifting the cited risk titles).

    chat_context = {
        "company": company,
        "year": year,
        "record_id": record_id,
        "compare_record_id": compare_record_id,
        "ticker": context_ticker,
        "model_id": _get_model_id(),
        "extraction_model_id": _get_extraction_model_id(),
        "has_risks": bool(risks),
        "risk_count": sum(len(c.get("sub_risks", [])) for c in risks if isinstance(c, dict)),
        "has_compare_data": isinstance(compare_data, dict),
        "source_page": str(payload.get("source_page", "") or "").strip(),
    }

    # Build agent tools registry + pre-compute available-data summary so the
    # system prompt can name what's in the index (saves the LLM one extra
    # tool call on every cold conversation).
    from agent_tools import build_tool_handlers, get_tool_specs

    tool_handlers = build_tool_handlers(backend_module=sys.modules[__name__])
    tool_specs = get_tool_specs()
    try:
        list_companies_handler = tool_handlers.get("list_available_companies")
        if callable(list_companies_handler):
            # Use a wider preload window so the chat model doesn't
            # incorrectly infer "company not in system" from a tiny sample.
            companies_blob = list_companies_handler(limit=200) or {}
            company_rows = companies_blob.get("companies", []) if isinstance(companies_blob, dict) else []
            summary_lines = []
            for row in company_rows:
                if not isinstance(row, dict):
                    continue
                comp = str(row.get("company", "") or "").strip()
                tk = str(row.get("ticker", "") or "").strip()
                yrs = row.get("years") or []
                if comp and yrs:
                    yr_label = f"{min(yrs)}-{max(yrs)}" if len(yrs) > 1 else str(yrs[0])
                    summary_lines.append(f"  - {comp}{f' ({tk})' if tk else ''}: {yr_label}")
            total = int(companies_blob.get("total", 0) or 0) if isinstance(companies_blob, dict) else 0
            returned = int(companies_blob.get("returned", 0) or 0) if isinstance(companies_blob, dict) else len(summary_lines)
            if summary_lines:
                trunc_note = ""
                if total > returned > 0:
                    trunc_note = (
                        f"(index shows {total} companies; preloaded {returned}. "
                        "If target company not listed here, call list_available_companies explicitly.)"
                    )
                available_companies_summary = "\n".join([trunc_note] + summary_lines if trunc_note else summary_lines)
            else:
                available_companies_summary = "(no filings yet)"
        else:
            available_companies_summary = "(no list_available_companies handler)"
    except Exception as exc:
        available_companies_summary = f"(failed to read index: {type(exc).__name__})"

    llm_invoke_with_tools = _get_llm_invoke_with_tools()
    run_chat_agent = _get_run_chat_agent()
    report = run_chat_agent(
        user_query=user_query,
        history=history,
        context=chat_context,
        llm_invoke=llm_invoke,
        llm_invoke_with_tools=llm_invoke_with_tools,
        tools=tool_handlers,
        tool_specs=tool_specs,
        available_companies_summary=available_companies_summary,
    )

    return {
        "ok": True,
        "query": user_query,
        "context": {
            "company": company,
            "year": year,
            "record_id": record_id,
            "compare_record_id": compare_record_id,
            "ticker": context_ticker,
            "has_risks": bool(risks),
        },
        "report": report,
    }


def handler(event, context=None):
    try:
        return _invoke_logic(event)
    except Exception as exc:
        err = {
            "error": str(exc),
            "type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }
        print("[handler] failed", json.dumps(err, ensure_ascii=False))
        raise


class _RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _set_cors_headers(self):
        allow_origin = _cors_origin_for_request(self.headers)
        if allow_origin:
            self.send_header("Access-Control-Allow-Origin", allow_origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
            self.send_header("Access-Control-Max-Age", "86400")

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except Exception:
            length = 0
        raw_body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw_body.decode("utf-8", errors="ignore"))
            if isinstance(body, dict):
                return body
            return {"payload": body}
        except Exception:
            return {"payload": raw_body.decode("utf-8", errors="ignore")}

    def do_OPTIONS(self):
        allow_origin = _cors_origin_for_request(self.headers)
        if not allow_origin:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query or "")

        try:
            if path in {"/", "/health", "/ping"}:
                self._send_json(
                    200,
                    {
                        "status": "Healthy",
                        "service": "risklens-runtime",
                        "time_of_last_update": int(time.time()),
                    },
                )
                return

            if path == "/api/meta":
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "service": "risklens-runtime",
                        "version": "v1",
                        "endpoints": [
                            "/api/meta",
                            "/api/records",
                            "/api/records/{record_id}",
                            "/api/dashboard/summary",
                            "/api/dashboard/ensure-priority (POST)",
                            "/api/stock/quote?ticker=AAPL",
                            "/api/stock/resolve-ticker?company=Apple&ticker=AAPL",
                            "/api/news?company=Apple&ticker=AAPL",
                            "/api/upload/manual (POST)",
                            "/api/upload/auto-fetch (POST)",
                            "/api/tables/result?company=Apple&year=2024&filing_type=10-K",
                            "/api/tables/extract/manual (POST)",
                            "/api/tables/extract/auto-fetch (POST)",
                            "/api/chatbot/help (POST)",
                            "/api/agent/query (POST)",
                            "/api/compare (POST)",
                            "/invocations (POST)",
                        ],
                    },
                )
                return

            if path == "/api/records":
                company = str((query.get("company", [""]) or [""])[0]).strip().lower()
                industry = str((query.get("industry", [""]) or [""])[0]).strip().lower()
                filing_type = str((query.get("filing_type", [""]) or [""])[0]).strip().lower()
                year = str((query.get("year", [""]) or [""])[0]).strip()
                include_result = str((query.get("include_result", ["0"]) or ["0"])[0]).strip() == "1"

                cache_key = _records_list_cache_key(
                    company=company,
                    industry=industry,
                    filing_type=filing_type,
                    year=year,
                    include_result=include_result,
                )
                cached = _RECORDS_LIST_CACHE.get(cache_key)
                now = time.time()
                if isinstance(cached, dict):
                    ts = float(cached.get("ts", 0.0) or 0.0)
                    payload = cached.get("payload")
                    if (now - ts) <= _RECORDS_LIST_CACHE_TTL_SECONDS and isinstance(payload, dict):
                        self._send_json(200, payload)
                        return

                recs = _load_index()
                out = []
                for r in recs:
                    if company and company not in str(r.get("company", "")).strip().lower():
                        continue
                    if industry and industry != str(r.get("industry", "")).strip().lower():
                        continue
                    if filing_type and filing_type != str(r.get("filing_type", "")).strip().lower():
                        continue
                    if year and str(r.get("year", "")) != year:
                        continue
                    out.append(r)

                out.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
                ticker_lookup = _build_ticker_lookup()
                items = [_record_summary(r, include_result=include_result, ticker_lookup=ticker_lookup) for r in out]
                payload = {"ok": True, "count": len(items), "items": items}
                _RECORDS_LIST_CACHE[cache_key] = {"ts": now, "payload": payload}
                if len(_RECORDS_LIST_CACHE) > 120:
                    oldest_key = min(_RECORDS_LIST_CACHE.items(), key=lambda kv: float(kv[1].get("ts", 0.0) or 0.0))[0]
                    _RECORDS_LIST_CACHE.pop(oldest_key, None)
                self._send_json(200, payload)
                return

            if path.startswith("/api/records/"):
                record_id = path.split("/api/records/", 1)[-1].strip()
                if not record_id:
                    self._send_json(400, {"ok": False, "error": "record_id is required."})
                    return
                rec = next((r for r in _load_index() if str(r.get("record_id", "")) == record_id), None)
                if isinstance(rec, dict):
                    rec = {
                        **rec,
                        "ticker": _resolve_record_ticker(rec, ticker_lookup=_build_ticker_lookup()),
                    }
                result = _load_result(record_id)
                if not rec and not result:
                    self._send_json(404, {"ok": False, "error": "Record not found."})
                    return
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "record": rec,
                        "result": result,
                    },
                )
                return

            if path == "/api/dashboard/summary":
                force = str((query.get("force", ["0"]) or ["0"])[0]).strip() == "1"
                self._send_json(200, {"ok": True, "data": _dashboard_summary_cached(force=force)})
                return

            if path == "/api/stock/quote":
                ticker = str((query.get("ticker", [""]) or [""])[0]).strip().upper()
                lite = _to_int((query.get("lite", ["0"]) or ["0"])[0], 0)
                if not ticker:
                    self._send_json(400, {"ok": False, "error": "ticker is required."})
                    return
                payload = _stock_quote(ticker, lite=bool(lite))
                if payload.get("error"):
                    self._send_json(400, {"ok": False, **payload})
                    return
                self._send_json(200, {"ok": True, "data": payload})
                return

            if path == "/api/stock/resolve-ticker":
                company = str((query.get("company", [""]) or [""])[0]).strip()
                ticker = str((query.get("ticker", [""]) or [""])[0]).strip().upper()
                if not company:
                    self._send_json(400, {"ok": False, "error": "company is required."})
                    return

                payload = _resolve_ticker_for_company(company=company, ticker_hint=ticker)
                if not payload.get("ok"):
                    self._send_json(404, {"ok": False, **payload})
                    return

                resolved = _normalize_ticker(payload.get("ticker"))
                if resolved:
                    try:
                        _upsert_company_ticker(company, resolved)
                    except Exception:
                        pass
                self._send_json(200, {"ok": True, **payload})
                return

            if path == "/api/news":
                company = str((query.get("company", [""]) or [""])[0]).strip()
                ticker = str((query.get("ticker", [""]) or [""])[0]).strip().upper()
                days = _to_int((query.get("days", ["30"]) or ["30"])[0], 30)
                limit = _to_int((query.get("limit", ["20"]) or ["20"])[0], 20)
                payload = _fetch_news(company, ticker, days, limit)
                if payload.get("error"):
                    self._send_json(400, {"ok": False, **payload})
                    return
                self._send_json(200, {"ok": True, **payload})
                return

            if path == "/api/tables/result":
                company = str((query.get("company", [""]) or [""])[0]).strip()
                year = _to_int((query.get("year", ["0"]) or ["0"])[0], 0)
                filing_type = str((query.get("filing_type", ["10-K"]) or ["10-K"])[0]).strip() or "10-K"
                if not company or year <= 0:
                    self._send_json(400, {"ok": False, "error": "company and year are required."})
                    return
                payload = _load_table_result(company, year, filing_type)
                self._send_json(200, {"ok": True, "result": payload})
                return

            self._send_json(404, {"ok": False, "error": "Not Found"})
        except Exception as exc:
            self._send_json(
                500,
                {
                    "ok": False,
                    "error": str(exc),
                    "type": type(exc).__name__,
                    "traceback": traceback.format_exc(),
                },
            )

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/invocations":
                body = self._read_json_body()
                result = _invoke_logic(body)
                self._send_json(200, result if isinstance(result, dict) else {"result": result})
                return

            if path == "/api/upload/manual":
                body = self._read_json_body()
                company = str(body.get("company", "") or "").strip()
                ticker = str(body.get("ticker", "") or "").strip().upper()
                industry = str(body.get("industry", "Other") or "Other").strip() or "Other"
                filing_type = _canonical_filing_type(body.get("filing_type", "10-K"))
                filing_quarter = _coerce_filing_quarter(body.get("filing_quarter", 0), filing_type)
                year = _to_int(body.get("year", 0), 0)
                file_name = str(body.get("file_name", "") or "").strip() or "filing.html"
                file_b64 = str(body.get("file_b64", "") or body.get("file_content_base64", "") or "").strip()

                if not company:
                    self._send_json(400, {"ok": False, "error": "company is required."})
                    return
                if year <= 0:
                    self._send_json(400, {"ok": False, "error": "year is required."})
                    return
                if not file_b64:
                    self._send_json(400, {"ok": False, "error": "file payload is required."})
                    return

                if "," in file_b64 and "base64" in file_b64[:80]:
                    file_b64 = file_b64.split(",", 1)[-1]
                try:
                    file_bytes = base64.b64decode(file_b64)
                except Exception:
                    self._send_json(400, {"ok": False, "error": "Invalid base64 file payload."})
                    return

                result, err = _manual_extract_result(
                    file_bytes=file_bytes,
                    file_name=file_name,
                    company=company,
                    industry=industry,
                    year=year,
                    filing_type=filing_type,
                    ticker=ticker,
                )
                if not result:
                    self._send_json(400, {"ok": False, "error": err or "Extraction failed."})
                    return

                risks_for_agent = result.get("risks", []) if isinstance(result.get("risks"), list) else []
                if risks_for_agent:
                    agent_report, agent_err = _generate_agent_priority_report(company=company, year=year, risks=risks_for_agent)
                    if isinstance(agent_report, dict):
                        result["agent_report"] = agent_report
                    elif agent_err:
                        result["agent_report_error"] = agent_err

                ext = "pdf" if file_name.lower().endswith(".pdf") else "html"
                record = _add_record(
                    company=company,
                    industry=industry,
                    year=year,
                    filing_type=filing_type,
                    ticker=ticker,
                    file_bytes=file_bytes,
                    file_ext=ext,
                    result_json=result,
                    filing_quarter=filing_quarter,
                )
                if ticker:
                    _upsert_company_ticker(company, ticker)
                if isinstance(result.get("agent_report"), dict):
                    try:
                        _append_agent_report_file(record, result.get("agent_report"))
                    except Exception:
                        pass
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "record": _record_summary(record, include_result=True),
                        "result": result,
                    },
                )
                return

            if path == "/api/upload/auto-fetch":
                body = self._read_json_body()
                company = str(body.get("company", "") or "").strip()
                ticker = str(body.get("ticker", "") or "").strip().upper()
                industry = str(body.get("industry", "Other") or "Other").strip() or "Other"
                filing_type = _canonical_filing_type(body.get("filing_type", "10-K"))
                start_year = _to_int(body.get("start_year", 0), 0)
                end_year = _to_int(body.get("end_year", 0), 0)
                payload = _auto_fetch_and_extract(
                    company=company,
                    ticker=ticker,
                    industry=industry,
                    filing_type=filing_type,
                    start_year=start_year,
                    end_year=end_year,
                )
                if not payload.get("ok"):
                    self._send_json(400, payload)
                    return
                self._send_json(200, payload)
                return

            if path == "/api/dashboard/ensure-priority":
                body = self._read_json_body()
                force = bool(body.get("force", False))
                limit = _to_int(body.get("limit", 0), 0)
                payload = _ensure_priority_for_all_records(force=force, limit=limit)
                self._send_json(200, payload)
                return

            if path == "/api/tables/extract/manual":
                body = self._read_json_body()
                company = str(body.get("company", "") or "").strip()
                ticker = str(body.get("ticker", "") or "").strip().upper()
                industry = str(body.get("industry", "Other") or "Other").strip() or "Other"
                filing_type = str(body.get("filing_type", "10-K") or "10-K").strip() or "10-K"
                year = _to_int(body.get("year", 0), 0)
                file_name = str(body.get("file_name", "") or "").strip() or "filing.pdf"
                file_b64 = str(body.get("file_b64", "") or body.get("file_content_base64", "") or "").strip()

                if not company:
                    self._send_json(400, {"ok": False, "error": "company is required."})
                    return
                if year <= 0:
                    self._send_json(400, {"ok": False, "error": "year is required."})
                    return
                if not file_b64:
                    self._send_json(400, {"ok": False, "error": "file payload is required."})
                    return
                if not file_name.lower().endswith(".pdf"):
                    self._send_json(400, {"ok": False, "error": "Tables extraction only supports PDF files."})
                    return

                if "," in file_b64 and "base64" in file_b64[:80]:
                    file_b64 = file_b64.split(",", 1)[-1]
                try:
                    file_bytes = base64.b64decode(file_b64)
                except Exception:
                    self._send_json(400, {"ok": False, "error": "Invalid base64 file payload."})
                    return

                result, table_key, err = _extract_tables_for_pdf(
                    pdf_bytes=file_bytes,
                    company=company,
                    industry=industry,
                    year=year,
                    filing_type=filing_type,
                    source="tables_manual_pdf",
                )
                if not result:
                    self._send_json(400, {"ok": False, "error": err or "Tables extraction failed."})
                    return

                if ticker:
                    _upsert_company_ticker(company, ticker)

                self._send_json(
                    200,
                    {
                        "ok": True,
                        "result": result,
                        "table_key": table_key,
                    },
                )
                return

            if path == "/api/tables/extract/auto-fetch":
                body = self._read_json_body()
                company = str(body.get("company", "") or "").strip()
                ticker = str(body.get("ticker", "") or "").strip().upper()
                industry = str(body.get("industry", "Other") or "Other").strip() or "Other"
                filing_type = str(body.get("filing_type", "10-K") or "10-K").strip() or "10-K"
                start_year = _to_int(body.get("start_year", 0), 0)
                end_year = _to_int(body.get("end_year", 0), 0)
                if not company:
                    self._send_json(400, {"ok": False, "error": "company is required."})
                    return
                if start_year <= 0 or end_year <= 0 or start_year > end_year:
                    self._send_json(400, {"ok": False, "error": "Invalid year range."})
                    return
                if download_10k_pdf_for_company_year is None:
                    self._send_json(400, {"ok": False, "error": "SEC PDF auto-fetch is unavailable in runtime."})
                    return

                successes: List[dict] = []
                skipped: List[dict] = []

                for yy in range(start_year, end_year + 1):
                    try:
                        pdf_bytes, meta, sec_err = download_10k_pdf_for_company_year(
                            company_name=company,
                            year=int(yy),
                            ticker=ticker,
                        )
                    except Exception as exc:
                        skipped.append({"year": yy, "reason": f"SEC request failed: {type(exc).__name__}: {exc}"})
                        continue

                    if not pdf_bytes:
                        filing_url = build_filing_html_url(meta) if build_filing_html_url and isinstance(meta, dict) else ""
                        skipped.append(
                            {
                                "year": yy,
                                "reason": sec_err or "Could not auto-download 10-K PDF from SEC EDGAR.",
                                "filing_url": filing_url,
                            }
                        )
                        continue

                    result, table_key, err = _extract_tables_for_pdf(
                        pdf_bytes=pdf_bytes,
                        company=company,
                        industry=industry,
                        year=int(yy),
                        filing_type=filing_type,
                        source="tables_auto_sec_pdf",
                    )
                    if not result:
                        skipped.append({"year": yy, "reason": err or "Tables extraction failed."})
                        continue

                    if ticker:
                        _upsert_company_ticker(company, ticker)
                    successes.append(
                        {
                            "year": yy,
                            "result": result,
                            "table_key": table_key,
                        }
                    )

                latest_result = successes[-1].get("result") if successes else None
                self._send_json(
                    200,
                    {
                        "ok": True,
                        "count": len(successes),
                        "successes": successes,
                        "skipped": skipped,
                        "latest_result": latest_result,
                    },
                )
                return

            if path == "/api/agent/query":
                body = self._read_json_body()
                payload = _agent_query(body)
                self._send_json(200, payload)
                return

            if path == "/api/chatbot/help":
                body = self._read_json_body()
                payload = _chatbot_help_query(body)
                self._send_json(200, payload)
                return

            if path == "/api/compare":
                body = self._read_json_body()
                latest_record_id = str(body.get("latest_record_id", "") or "").strip()
                prior_record_id = str(body.get("prior_record_id", "") or "").strip()
                if not latest_record_id or not prior_record_id:
                    self._send_json(400, {"ok": False, "error": "latest_record_id and prior_record_id are required."})
                    return
                mode = str(body.get("mode", "") or "").strip().lower() or "yoy"
                t_low = body.get("threshold_low")
                t_high = body.get("threshold_high")
                payload = _compare_payload(
                    latest_record_id,
                    prior_record_id,
                    mode=mode,
                    threshold_low=t_low,
                    threshold_high=t_high,
                )
                if payload.get("error"):
                    self._send_json(400, {"ok": False, **payload})
                    return
                self._send_json(200, {"ok": True, "data": payload})
                return

            self._send_json(404, {"ok": False, "error": "Not Found"})
        except Exception as exc:
            err = {
                "ok": False,
                "error": str(exc),
                "type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
            print("[runtime] invocation failed", json.dumps(err, ensure_ascii=False))
            self._send_json(500, err)

    def log_message(self, format, *args):
        return


invoke = handler
handle_request = handler


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8080"))
    print(f"[runtime] starting threaded HTTP server on {host}:{port}")
    server = ThreadingHTTPServer((host, port), _RequestHandler)
    server.serve_forever()
