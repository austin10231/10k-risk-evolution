"""Minimal AgentCore HTTP runtime + product REST API."""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import boto3

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
    )
except Exception:
    extract_item1_overview_bedrock = None
    extract_item1a_risks_bedrock = None
    extract_item1_overview_from_text = None
    extract_item1a_risks_from_text = None
    extract_text_from_pdf = None

try:
    from core.sec_edgar import download_10k_html_for_company_year, build_filing_html_url
except Exception:
    download_10k_html_for_company_year = None
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
_MODEL_ID = None

INDEX_KEY = "filing_records_index.json"
RESULTS_PREFIX = "risk_analysis_results"
AGENT_PREFIX = "agent_reports"
TICKER_MAP_KEY = "company_ticker_map.json"
HTML_PREFIX = "10k_html_datasets"
PDF_PREFIX = "10k_pdf_datasets"
TABLES_PREFIX = "tables_extraction"
_NEWS_CACHE: Dict[str, Dict[str, Any]] = {}
_NEWS_CACHE_TTL_SECONDS = 120
_STOCK_PROVIDER_STATE: Dict[str, Dict[str, Any]] = {}
_STOCK_PROVIDER_DEFAULT_COOLDOWN_SECONDS = 70
_STOCK_QUOTE_CACHE: Dict[str, Dict[str, Any]] = {}
_STOCK_QUOTE_CACHE_TTL_SECONDS = 600
_STOCK_QUOTE_CACHE_PREFIX = "stock_quote_cache_v1"


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or default)


def _bucket() -> str:
    return _env("S3_BUCKET", "").strip()


def _aws_region() -> str:
    return _env("AWS_REGION", "us-west-1").strip() or "us-west-1"


def _s3_client():
    kwargs = {"region_name": _aws_region()}
    access_key = _env("AWS_ACCESS_KEY_ID", "").strip()
    secret_key = _env("AWS_SECRET_ACCESS_KEY", "").strip()
    session_token = _env("AWS_SESSION_TOKEN", "").strip()
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return boto3.client("s3", **kwargs)


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


def _delete_s3_key(key: str) -> None:
    bucket = _bucket()
    if not bucket:
        return
    try:
        _s3_client().delete_object(Bucket=bucket, Key=key)
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


def _load_index() -> List[dict]:
    raw = _json_from_bytes(_read_s3_bytes(INDEX_KEY), [])
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        candidates = raw.get("items")
        if isinstance(candidates, list):
            return [r for r in candidates if isinstance(r, dict)]
    return []


def _load_result(record_id: str) -> Optional[dict]:
    rid = str(record_id or "").strip()
    if not rid:
        return None
    return _json_from_bytes(_read_s3_bytes(f"{RESULTS_PREFIX}/{rid}.json"), None)


def _load_company_ticker_map() -> Dict[str, str]:
    raw = _json_from_bytes(_read_s3_bytes(TICKER_MAP_KEY), {})
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for company, ticker in raw.items():
        c = str(company or "").strip()
        t = str(ticker or "").strip().upper()
        if c and t:
            out[c] = t
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
) -> dict:
    company = str(company or "").strip()
    industry = str(industry or "Other").strip() or "Other"
    filing_type = str(filing_type or "10-K").strip() or "10-K"
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
    ]
    for d in dupes:
        old_id = str(d.get("record_id", "") or "")
        if not old_id:
            continue
        old_ext = "pdf" if str(d.get("file_ext", "html")).lower() == "pdf" else "html"
        old_prefix = PDF_PREFIX if old_ext == "pdf" else HTML_PREFIX
        _delete_s3_key(f"{old_prefix}/{old_id}.{old_ext}")
        _delete_s3_key(f"{RESULTS_PREFIX}/{old_id}.json")

    index = [
        r
        for r in index
        if not (
            str(r.get("company", "")) == company
            and int(r.get("year", 0) or 0) == year
            and str(r.get("filing_type", "")) == filing_type
        )
    ]

    safe = _sanitize_company(company)
    sid = uuid.uuid4().hex[:4]
    rid = f"{safe}_{year}_{_sanitize_filing_type(filing_type)}_{sid}"
    data_prefix = PDF_PREFIX if ext == "pdf" else HTML_PREFIX

    _write_s3_bytes(f"{data_prefix}/{rid}.{ext}", file_bytes)
    _write_s3_bytes(
        f"{RESULTS_PREFIX}/{rid}.json",
        json.dumps(result_json, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    record = {
        "record_id": rid,
        "company": company,
        "ticker": ticker,
        "industry": industry,
        "year": year,
        "filing_type": filing_type,
        "file_ext": ext,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    index.append(record)
    _save_index(index)
    return record


def _load_agent_reports() -> List[dict]:
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

_RISK_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "Capital Markets": [
        "common stock",
        "stockholder",
        "shareholder",
        "market price",
        "securities",
        "dividend",
        "equity offering",
        "dilution",
        "ownership of our stock",
        "capital market",
    ],
    "Financial & Liquidity": [
        "financial risk",
        "financial condition",
        "financial statements",
        "liquidity",
        "cash flow",
        "debt",
        "credit",
        "interest rate",
        "refinancing",
        "impairment",
        "profitability",
        "revenue",
        "inflation",
        "foreign exchange",
        "currency",
        "solvency",
        "capital resources",
    ],
    "Legal & Regulatory": [
        "legal",
        "regulatory",
        "regulation",
        "compliance",
        "litigation",
        "laws",
        "government",
        "policy",
        "policies",
        "antitrust",
        "sanction",
        "fines",
        "bribery",
        "corruption",
        "intellectual property",
        "tax-related",
        "reit",
        "status as a reit",
    ],
    "Technology & Cybersecurity": [
        "technology",
        "cyber",
        "cybersecurity",
        "information security",
        "data breach",
        "data privacy",
        "privacy",
        "it system",
        "system outage",
        "software",
        "cloud",
        "artificial intelligence",
        "machine learning",
        "generative ai",
        "digital",
        "ransomware",
    ],
    "Operations & Supply Chain": [
        "operations",
        "operational",
        "business operations",
        "supply chain",
        "supplier",
        "procurement",
        "manufacturing",
        "production",
        "logistics",
        "distribution",
        "inventory",
        "quality",
        "safety",
        "business continuity",
        "disruption",
    ],
    "People & Governance": [
        "employment",
        "workforce",
        "labor",
        "union",
        "human capital",
        "talent",
        "hiring",
        "retention",
        "management",
        "leadership",
        "executive",
        "board",
        "governance",
        "internal control",
        "culture",
    ],
    "ESG & Sustainability": [
        "esg",
        "environment",
        "environmental",
        "sustainability",
        "climate",
        "climate change",
        "carbon",
        "emissions",
        "greenhouse gas",
        "social responsibility",
    ],
    "Strategy & Market": [
        "strategy",
        "strategic",
        "market",
        "industry",
        "competition",
        "competitive",
        "customer",
        "demand",
        "pricing",
        "growth",
        "reputation",
        "brand",
        "macro",
        "geopolitical",
        "business risk",
        "general risk",
        "risk factors",
        "risks specific to our company",
    ],
}


def _normalize_risk_category(category: Any, title: Any = "", labels: Optional[List[Any]] = None) -> str:
    cat_text = str(category or "").strip()
    title_text = str(title or "").strip()
    label_text = " ".join([str(x or "").strip() for x in (labels or []) if str(x or "").strip()])
    full_text = " ".join([cat_text, title_text, label_text]).strip().lower()
    if not full_text:
        return "General & Other"

    scores: Dict[str, int] = {k: 0 for k in FIXED_RISK_CATEGORIES}

    def _add_match_points(target: str, phrase: str) -> None:
        if phrase in full_text:
            scores[target] = scores.get(target, 0) + 1
        if phrase in cat_text.lower():
            scores[target] = scores.get(target, 0) + 2

    for target, phrases in _RISK_CATEGORY_KEYWORDS.items():
        for phrase in phrases:
            _add_match_points(target, phrase)

    # Prefer non-"General & Other" when any specific signal exists.
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    best_cat, best_score = ranked[0]
    if best_score > 0:
        return best_cat

    if cat_text or title_text:
        return "Strategy & Market"
    return "General & Other"


def _extract_sub_risks(result: dict) -> List[dict]:
    out: List[dict] = []
    for cat_block in result.get("risks", []) if isinstance(result, dict) else []:
        category = str(cat_block.get("category", "Unknown") or "Unknown")
        for sr in cat_block.get("sub_risks", []) or []:
            if isinstance(sr, dict):
                title = str(sr.get("title", "") or "").strip()
                labels = sr.get("labels", [])
            else:
                title = str(sr or "").strip()
                labels = []
            if not title:
                continue
            mapped_category = _normalize_risk_category(category, title, labels if isinstance(labels, list) else [])
            out.append({"category": mapped_category, "title": title, "labels": labels})
    return out


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
    ft = str(filing_type or "10-K").strip() or "10-K"
    yy = int(year or 0)

    try:
        if is_pdf:
            pdf_text = extract_text_from_pdf(file_bytes)
            if not pdf_text:
                return None, "Textract could not extract text from this PDF."
            overview = extract_item1_overview_from_text(pdf_text, company_name, industry_name)
            risks = extract_item1a_risks_from_text(pdf_text)
        else:
            # Keep both pipelines while removing user-facing mode choice:
            # HTML defaults to AI-enhanced with internal fallback to standard.
            overview = extract_item1_overview_bedrock(file_bytes, company_name, industry_name)
            risks = extract_item1a_risks_bedrock(file_bytes, company_name)
    except Exception as exc:
        return None, f"Extraction failed: {type(exc).__name__}: {exc}"

    if not risks:
        return None, "Could not extract risks from Item 1A."

    overview = dict(overview or {})
    overview["year"] = yy
    overview["filing_type"] = ft
    overview["company"] = overview.get("company") or company_name
    overview["industry"] = overview.get("industry") or industry_name

    return {"company_overview": overview, "risks": risks}, ""


def _auto_fetch_and_extract(
    *,
    company: str,
    ticker: str,
    industry: str,
    start_year: int,
    end_year: int,
) -> dict:
    if download_10k_html_for_company_year is None:
        return {"ok": False, "error": "SEC auto-fetch is unavailable in runtime."}

    comp = str(company or "").strip()
    tk = str(ticker or "").strip().upper()
    ind = str(industry or "Other").strip() or "Other"
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
            html_bytes, sec_meta, sec_err = download_10k_html_for_company_year(comp, yy, tk)
        except Exception as exc:
            skipped.append({"year": yy, "reason": f"SEC request failed: {type(exc).__name__}: {exc}"})
            continue

        if not html_bytes:
            skipped.append({"year": yy, "reason": sec_err or "Could not fetch 10-K HTML from SEC EDGAR."})
            continue

        result, extract_err = _manual_extract_result(
            file_bytes=html_bytes,
            file_name=f"{comp}_{yy}.html",
            company=comp,
            industry=ind,
            year=yy,
            filing_type="10-K",
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
        result["sec_meta"] = {
            **(sec_meta if isinstance(sec_meta, dict) else {}),
            "auto_fetch": True,
            "ticker": tk,
            "filing_url": build_filing_html_url(sec_meta) if build_filing_html_url and isinstance(sec_meta, dict) else "",
        }

        try:
            rec = _add_record(
                company=comp,
                industry=ind,
                year=yy,
                filing_type="10-K",
                ticker=tk,
                file_bytes=html_bytes,
                file_ext="html",
                result_json=result,
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
    base = {
        "record_id": rec.get("record_id"),
        "company": rec.get("company"),
        "ticker": ticker,
        "industry": rec.get("industry"),
        "year": rec.get("year"),
        "filing_type": rec.get("filing_type"),
        "file_ext": rec.get("file_ext"),
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


def _risk_pressure_index(high: int, medium: int, low: int) -> float:
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
    }
    if not isinstance(result, dict):
        return out

    agent_report = result.get("agent_report", {}) if isinstance(result.get("agent_report"), dict) else {}
    pm = agent_report.get("priority_matrix", {}) if isinstance(agent_report.get("priority_matrix"), dict) else {}
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
        rpi = _risk_pressure_index(priority["high"], priority["medium"], priority["low"])

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
            if rpi > 0:
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
                        "rpi": float(rpi),
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
            rpi = float(cell.get("rpi", 0.0) or 0.0)
            max_rpi_by_company[comp] = max(max_rpi_by_company.get(comp, 0.0), rpi)
        companies_sorted = sorted(
            list(scope["companies_set"]),
            key=lambda c: (-max_rpi_by_company.get(c, 0.0), c.lower()),
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
    with urlopen(req, timeout=20) as resp:
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
    with urlopen(req, timeout=20) as resp:
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
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
    payload = json.loads(raw.decode("utf-8", errors="ignore"))
    if isinstance(payload, dict):
        msg = str(payload.get("Error Message") or payload.get("error") or payload.get("message") or "").strip()
        if msg and msg.lower() not in {"ok", "success"}:
            raise RuntimeError(msg)
    return payload


def _fmp_quote(symbol: str, api_key: str) -> dict:
    sym = str(symbol or "").strip().upper()
    url = f"https://financialmodelingprep.com/api/v3/quote/{quote(sym)}?apikey={quote(api_key)}"
    payload = _fmp_json(url)
    rows = payload if isinstance(payload, list) else []
    if not rows:
        raise RuntimeError("empty quote response")
    row = rows[0] if isinstance(rows[0], dict) else {}

    return {
        "symbol": row.get("symbol") or sym,
        "name": row.get("name") or sym,
        "price": _to_float(row.get("price")),
        "change": _to_float(row.get("change")),
        "change_percent": _to_float(row.get("changesPercentage")),
        "market_cap": _to_float(row.get("marketCap")),
        "pe_ratio": _to_float(row.get("pe")),
        "high_52": _to_float(row.get("yearHigh")),
        "low_52": _to_float(row.get("yearLow")),
        "exchange": row.get("exchange") or row.get("exchangeShortName") or "",
    }


def _fmp_history(symbol: str, api_key: str) -> List[dict]:
    sym = str(symbol or "").strip().upper()
    url = (
        "https://financialmodelingprep.com/api/v3/historical-price-full/"
        f"{quote(sym)}?timeseries=260&apikey={quote(api_key)}"
    )
    payload = _fmp_json(url)
    rows = payload.get("historical", []) if isinstance(payload, dict) else []
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
            with urlopen(req, timeout=20) as resp:
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

        if not quote_source and any(
            data.get(k) is not None for k in ("price", "change", "change_percent", "market_cap", "pe_ratio")
        ):
            quote_source = provider

        incoming_name = str(data.get("name", "") or "").strip()
        if incoming_name and (not name or name == sym):
            name = incoming_name
        if price is None:
            price = _to_float(data.get("price"))
        if change is None:
            change = _to_float(data.get("change"))
        if change_percent is None:
            change_percent = _to_float(data.get("change_percent"))
        if market_cap is None:
            market_cap = _to_float(data.get("market_cap"))
        if pe_ratio is None:
            pe_ratio = _to_float(data.get("pe_ratio"))
        if high_52 is None:
            high_52 = _to_float(data.get("high_52"))
        if low_52 is None:
            low_52 = _to_float(data.get("low_52"))
        if not exchange:
            exchange = str(data.get("exchange", "") or "").strip()
        if previous_close is None:
            previous_close = _to_float(data.get("previous_close"))
        if open_price is None:
            open_price = _to_float(data.get("open"))
        if day_high is None:
            day_high = _to_float(data.get("day_high"))
        if day_low is None:
            day_low = _to_float(data.get("day_low"))
        if volume is None:
            volume = _to_float(data.get("volume"))
        if eps is None:
            eps = _to_float(data.get("eps"))
        if dividend_yield is None:
            dividend_yield = _to_float(data.get("dividend_yield"))
        if not sector:
            sector = str(data.get("sector", "") or "").strip()
        if not industry:
            industry = str(data.get("industry", "") or "").strip()
        if not country:
            country = str(data.get("country", "") or "").strip()
        if full_time_employees is None:
            full_time_employees = _to_float(data.get("full_time_employees"))
        if shares_outstanding is None:
            shares_outstanding = _to_float(data.get("shares_outstanding"))
        if not ceo:
            ceo = str(data.get("ceo", "") or "").strip()
        if not long_description:
            long_description = str(data.get("description", "") or "").strip()
        if not ipo_date:
            ipo_date = str(data.get("ipo_date", "") or "").strip()
        if post_market_price is None:
            post_market_price = _to_float(data.get("post_market_price"))
        if post_market_change is None:
            post_market_change = _to_float(data.get("post_market_change"))
        if post_market_change_percent is None:
            post_market_change_percent = _to_float(data.get("post_market_change_percent"))
        if regular_market_time is None:
            regular_market_time = _to_float(data.get("regular_market_time"))
        if post_market_time is None:
            post_market_time = _to_float(data.get("post_market_time"))

    def _need_quote_fields() -> bool:
        return any(v is None for v in [price, change, change_percent, market_cap, pe_ratio, high_52, low_52]) or not exchange

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
    global _LLM_INVOKE
    if _LLM_INVOKE is None:
        from agent import invoke_llm_text as _imported_invoke

        _LLM_INVOKE = _imported_invoke
    return _LLM_INVOKE


def _get_model_id() -> str:
    global _MODEL_ID
    if _MODEL_ID is None:
        try:
            from agent import get_model_id as _imported_get_model_id

            _MODEL_ID = str(_imported_get_model_id() or "").strip() or "us.amazon.nova-pro-v1:0"
        except Exception:
            _MODEL_ID = "us.amazon.nova-pro-v1:0"
    return _MODEL_ID


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


def _compare_payload(latest_record_id: str, prior_record_id: str) -> dict:
    latest = _load_result(latest_record_id)
    prior = _load_result(prior_record_id)
    if not isinstance(latest, dict) or not isinstance(prior, dict):
        return {"error": "Invalid record ids for compare."}

    if compare_risks:
        diff = compare_risks(prior, latest)
    else:
        prior_titles = {_normalize_title(x.get("title")) for x in _extract_sub_risks(prior)}
        latest_items = _extract_sub_risks(latest)
        latest_titles = {_normalize_title(x.get("title")) for x in latest_items}
        diff = {
            "new_risks": [x for x in latest_items if _normalize_title(x.get("title")) not in prior_titles],
            "removed_risks": [x for x in _extract_sub_risks(prior) if _normalize_title(x.get("title")) not in latest_titles],
        }

    return {
        "latest_record_id": latest_record_id,
        "prior_record_id": prior_record_id,
        "new_risks": diff.get("new_risks", []),
        "removed_risks": diff.get("removed_risks", []),
        "summary": {
            "new_count": len(diff.get("new_risks", [])),
            "removed_count": len(diff.get("removed_risks", [])),
        },
    }


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

    run_agent = _get_run_agent()
    llm_invoke = _get_llm_invoke()

    def _polish_business_answer(raw_text: str, query: str, mode: str) -> str:
        text = str(raw_text or "").strip()
        if not text:
            return text
        prompt = f"""You are a professional 10-K risk analyst assistant.

User question:
{str(query or '').strip()}

Draft answer:
{text}

Rewrite the draft answer to be:
- more natural and human,
- concise but professional,
- grounded in the same facts (do not add unsupported claims),
- in the same language as the user.

Context mode: {mode}

Return plain text only."""
        try:
            polished = str(llm_invoke(prompt, 700) or "").strip()
            if polished:
                return _strip_markdown_artifacts(polished)
        except Exception:
            pass
        return _strip_markdown_artifacts(text)

    def tool_risk_analysis(*, query: str, history: List[dict], context: dict) -> dict:
        if not risks:
            msg = (
                "I cannot find extracted risk data yet. Please upload or select a filing first, "
                "then I can run risk analysis."
            )
            return {
                "response": {
                    "type": "action",
                    "action": "navigate",
                    "target": "upload_page",
                    "params": {"company": company, "year": year},
                    "message": msg,
                },
                "tool_payload": {"has_risks": False},
            }

        report = run_agent(
            user_query=query or "Summarize the most important risks.",
            company=company,
            year=year,
            risks=risks,
            compare_data=None,
        )
        message = str(report.get("direct_answer", "") or report.get("executive_summary", "") or "").strip()
        if not message:
            message = "Risk analysis completed."
        message = _polish_business_answer(message, query, "risk_analysis")
        return {
            "response": {"type": "text", "content": message},
            "tool_payload": {
                "has_risks": True,
                "risk_count": sum(len(c.get("sub_risks", [])) for c in risks if isinstance(c, dict)),
            },
            "risk_report": report,
        }

    def tool_compare_risk(*, query: str, history: List[dict], context: dict) -> dict:
        if not compare_data:
            msg = (
                "I need two filings to compare. Please choose a baseline filing in Compare, "
                "then ask me again for deltas."
            )
            return {
                "response": {
                    "type": "action",
                    "action": "navigate",
                    "target": "compare_page",
                    "params": {"record_id": record_id, "company": company, "year": year},
                    "message": msg,
                },
                "tool_payload": {"has_compare_data": False},
            }

        report = run_agent(
            user_query=query or "Compare risk deltas and summarize key changes.",
            company=company,
            year=year,
            risks=risks,
            compare_data=compare_data,
        )
        message = str(report.get("direct_answer", "") or report.get("compare_insights", "") or report.get("executive_summary", "")).strip()
        if not message:
            message = "Risk comparison completed."
        message = _polish_business_answer(message, query, "compare_risk")
        return {
            "response": {
                "type": "action",
                "action": "navigate",
                "target": "compare_page",
                "params": {
                    "record_id": record_id,
                    "compare_record_id": compare_record_id,
                    "company": company,
                    "year": year,
                },
                "message": message,
            },
            "tool_payload": {
                "has_compare_data": True,
                "new_count": len(compare_data.get("new_risks", [])) if isinstance(compare_data, dict) else 0,
                "removed_count": len(compare_data.get("removed_risks", [])) if isinstance(compare_data, dict) else 0,
            },
            "risk_report": report,
        }

    def tool_stock_query(*, query: str, history: List[dict], context: dict) -> dict:
        ticker = _resolve_agent_ticker(user_query=query, company=company, context_ticker=context_ticker)
        if not ticker:
            return {
                "response": {
                    "type": "text",
                    "content": "Please provide a ticker (for example AAPL) so I can fetch stock data here in chat.",
                },
                "tool_payload": {"ticker": ""},
            }

        quote_payload = _stock_quote(ticker, lite=True)
        if quote_payload.get("error"):
            return {
                "response": {
                    "type": "text",
                    "content": f"I could not fetch stock data for {ticker}: {quote_payload.get('error')}",
                },
                "tool_payload": {"ticker": ticker, "error": quote_payload.get("error")},
            }

        price = quote_payload.get("price")
        pct = quote_payload.get("change_percent")
        chg = quote_payload.get("change")
        volume = quote_payload.get("volume")
        source = str(quote_payload.get("source", "") or "").strip()
        if isinstance(price, (int, float)) and isinstance(pct, (int, float)):
            summary = f"{ticker} is trading at {price:.2f}, with a daily move of {pct:+.2f}% ({chg:+.2f})."
            if isinstance(volume, (int, float)) and volume > 0:
                summary += f" Volume: {int(volume):,}."
            if source:
                summary += f" Source: {source}."
        else:
            summary = f"I fetched the latest stock snapshot for {ticker}."
            if source:
                summary += f" Source: {source}."

        summary = _polish_business_answer(summary, query, "stock_query")

        return {
            "response": {
                "type": "text",
                "content": summary,
            },
            "tool_payload": {"ticker": ticker, "quote": quote_payload},
        }

    def tool_news_query(*, query: str, history: List[dict], context: dict) -> dict:
        ticker = _resolve_agent_ticker(user_query=query, company=company, context_ticker=context_ticker)
        company_for_news = company
        if not company_for_news and ticker:
            company_for_news = ticker

        if not company_for_news and not ticker:
            return {
                "response": {
                    "type": "text",
                    "content": "Please provide a company name or ticker so I can fetch relevant news here in chat.",
                },
                "tool_payload": {"company": "", "ticker": ""},
            }

        news_payload = _fetch_news(company_for_news, ticker, 30, 8)
        if news_payload.get("error"):
            return {
                "response": {
                    "type": "text",
                    "content": f"I could not fetch news right now: {news_payload.get('error')}",
                },
                "tool_payload": {"company": company_for_news, "ticker": ticker, "error": news_payload.get("error")},
            }

        items = news_payload.get("items", []) if isinstance(news_payload.get("items"), list) else []
        top_rows = []
        for row in items[:3]:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title", "") or "").strip()
            if not title:
                continue
            source = str(row.get("source", "") or "").strip()
            published_at = str(row.get("published_at", "") or "").strip()
            extra_bits = [x for x in [source, published_at] if x]
            if extra_bits:
                top_rows.append(f"{title} ({' · '.join(extra_bits)})")
            else:
                top_rows.append(title)

        if top_rows:
            summary = f"I found {len(items)} recent headlines for {ticker or company_for_news}. Top headlines: " + " | ".join(top_rows)
        else:
            summary = f"I found no major recent headlines for {ticker or company_for_news}."

        summary = _polish_business_answer(summary, query, "news_query")

        return {
            "response": {
                "type": "text",
                "content": summary,
            },
            "tool_payload": {
                "company": company_for_news,
                "ticker": ticker,
                "items_count": len(items),
                "provider": news_payload.get("provider", ""),
            },
        }

    chat_context = {
        "company": company,
        "year": year,
        "record_id": record_id,
        "compare_record_id": compare_record_id,
        "ticker": context_ticker,
        "model_id": _get_model_id(),
        "has_risks": bool(risks),
        "risk_count": sum(len(c.get("sub_risks", [])) for c in risks if isinstance(c, dict)),
        "has_compare_data": isinstance(compare_data, dict),
        "source_page": str(payload.get("source_page", "") or "").strip(),
    }

    run_chat_agent = _get_run_chat_agent()
    report = run_chat_agent(
        user_query=user_query,
        history=history,
        context=chat_context,
        llm_invoke=llm_invoke,
        tools={
            "risk_analysis": tool_risk_analysis,
            "compare_risk": tool_compare_risk,
            "stock_query": tool_stock_query,
            "news_query": tool_news_query,
        },
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
                self._send_json(200, {"ok": True, "count": len(items), "items": items})
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
                self._send_json(200, {"ok": True, "data": _dashboard_summary()})
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
                filing_type = str(body.get("filing_type", "10-K") or "10-K").strip() or "10-K"
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
                start_year = _to_int(body.get("start_year", 0), 0)
                end_year = _to_int(body.get("end_year", 0), 0)
                payload = _auto_fetch_and_extract(
                    company=company,
                    ticker=ticker,
                    industry=industry,
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

            if path == "/api/compare":
                body = self._read_json_body()
                latest_record_id = str(body.get("latest_record_id", "") or "").strip()
                prior_record_id = str(body.get("prior_record_id", "") or "").strip()
                if not latest_record_id or not prior_record_id:
                    self._send_json(400, {"ok": False, "error": "latest_record_id and prior_record_id are required."})
                    return
                payload = _compare_payload(latest_record_id, prior_record_id)
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
    print(f"[runtime] starting HTTP server on {host}:{port}")
    server = HTTPServer((host, port), _RequestHandler)
    server.serve_forever()
