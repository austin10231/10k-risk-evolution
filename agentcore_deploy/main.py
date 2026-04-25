"""Minimal AgentCore HTTP runtime + product REST API."""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Set
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

import boto3

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    from core.comparator import compare_risks
except Exception:
    compare_risks = None

_RUN_AGENT = None

INDEX_KEY = "filing_records_index.json"
RESULTS_PREFIX = "risk_analysis_results"
AGENT_PREFIX = "agent_reports"
TICKER_MAP_KEY = "company_ticker_map.json"


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
            out.append({"category": category, "title": title, "labels": labels})
    return out


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


def _record_summary(rec: dict, include_result: bool = False) -> dict:
    if not isinstance(rec, dict):
        rec = {}
    base = {
        "record_id": rec.get("record_id"),
        "company": rec.get("company"),
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
                base["risk_categories"] = len(result.get("risks", [])) if isinstance(result.get("risks"), list) else 0
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


def _dashboard_summary() -> dict:
    index = _load_index()
    records = sorted(index, key=lambda r: str(r.get("created_at", "")), reverse=True)
    companies = sorted({str(r.get("company", "") or "").strip() for r in records if str(r.get("company", "") or "").strip()})

    category_counts: Dict[str, int] = {}
    total_risk_items = 0
    yearly_counts: Dict[str, int] = {}
    for rec in records:
        year_key = str(rec.get("year", ""))
        if year_key:
            yearly_counts[year_key] = yearly_counts.get(year_key, 0) + 1

        result = _load_result(str(rec.get("record_id", "") or ""))
        if not isinstance(result, dict):
            continue
        risks = _extract_sub_risks(result)
        total_risk_items += len(risks)
        for item in risks:
            c = str(item.get("category", "Unknown") or "Unknown")
            category_counts[c] = category_counts.get(c, 0) + 1

    reports = _load_agent_reports()
    latest_rating_by_company_year: Dict[str, str] = {}
    rating_counts: Dict[str, int] = {"High": 0, "Medium-High": 0, "Medium": 0, "Medium-Low": 0, "Low": 0, "Unknown": 0}
    for rp in reports:
        company = str(rp.get("company", "") or "").strip()
        year = str(rp.get("year", "") or "").strip()
        rating = str(rp.get("overall_risk_rating", "Unknown") or "Unknown").strip()
        if not company or not year:
            continue
        key = f"{company}__{year}"
        latest_rating_by_company_year[key] = rating

    for rating in latest_rating_by_company_year.values():
        if rating not in rating_counts:
            rating = "Unknown"
        rating_counts[rating] += 1

    top_categories = sorted(category_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]
    recent_records = [_record_summary(r, include_result=True) for r in records[:12]]

    return {
        "metrics": {
            "records": len(records),
            "companies": len(companies),
            "years_covered": len(yearly_counts),
            "risk_items": total_risk_items,
            "agent_reports": len(reports),
        },
        "rating_breakdown": rating_counts,
        "top_categories": [{"category": k, "count": v} for k, v in top_categories],
        "yearly_records": [{"year": y, "count": c} for y, c in sorted(yearly_counts.items())],
        "recent_records": recent_records,
        "companies": companies,
    }


def _yahoo_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "RiskLens/1.0"}, method="GET")
    with urlopen(req, timeout=20) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8", errors="ignore"))


def _stock_quote(symbol: str) -> dict:
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"error": "Ticker is required."}

    quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={sym}"
    chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1y&interval=1d"

    try:
        quote_payload = _yahoo_json(quote_url)
        chart_payload = _yahoo_json(chart_url)
    except Exception as e:
        return {"error": f"Failed to fetch stock data: {type(e).__name__}: {e}"}

    quote_result = (
        quote_payload.get("quoteResponse", {}).get("result", [])
        if isinstance(quote_payload, dict) else []
    )
    row = quote_result[0] if quote_result else {}

    chart = chart_payload.get("chart", {}) if isinstance(chart_payload, dict) else {}
    results = chart.get("result", []) if isinstance(chart, dict) else []
    history: List[dict] = []
    if results:
        first = results[0] if isinstance(results[0], dict) else {}
        ts = first.get("timestamp", []) or []
        q = first.get("indicators", {}).get("quote", []) or []
        closes = q[0].get("close", []) if q and isinstance(q[0], dict) else []
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
            history.append({"date": dt, "close": float(c)})

    return {
        "symbol": sym,
        "name": row.get("longName") or row.get("shortName") or sym,
        "price": row.get("regularMarketPrice"),
        "change": row.get("regularMarketChange"),
        "change_percent": row.get("regularMarketChangePercent"),
        "market_cap": row.get("marketCap"),
        "pe_ratio": row.get("trailingPE"),
        "high_52": row.get("fiftyTwoWeekHigh"),
        "low_52": row.get("fiftyTwoWeekLow"),
        "exchange": row.get("fullExchangeName") or row.get("exchange"),
        "history": history,
        "error": "",
    }


def _fetch_news(company: str, ticker: str, days: int, limit: int):
    from datetime import timedelta

    token = _env("MARKETAUX_API_TOKEN", "").strip()
    if not token:
        return {"error": "MARKETAUX_API_TOKEN is not configured.", "items": []}

    params = {
        "api_token": token,
        "language": "en",
        "sort": "published_desc",
        "limit": max(1, min(int(limit or 20), 50)),
        "published_after": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    day_window = max(1, min(int(days or 30), 365))
    params["published_after"] = (datetime.utcnow() - timedelta(days=day_window)).strftime("%Y-%m-%d")

    if ticker:
        params["symbols"] = str(ticker).strip().upper()
    elif company:
        params["search"] = str(company).strip()

    url = f"https://api.marketaux.com/v1/news/all?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "RiskLens/1.0"}, method="GET")

    try:
        with urlopen(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="ignore")
        except Exception:
            detail = str(e)
        return {"error": f"News API HTTP {e.code}: {detail}", "items": []}
    except URLError as e:
        return {"error": f"News API network error: {e}", "items": []}
    except Exception as e:
        return {"error": f"News API failed: {type(e).__name__}: {e}", "items": []}

    rows = payload.get("data", []) if isinstance(payload, dict) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        source_name = source.get("name") if isinstance(source, dict) else source
        out.append(
            {
                "title": item.get("title") or "",
                "summary": item.get("description") or item.get("snippet") or "",
                "published_at": item.get("published_at") or item.get("publishedAt") or "",
                "url": item.get("url") or item.get("link") or "",
                "source": source_name or "Unknown",
            }
        )
    return {"error": "", "items": out}


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


def _agent_query(payload: dict) -> dict:
    user_query = str(payload.get("user_query", "") or "").strip()
    company = str(payload.get("company", "") or "").strip()
    year = _to_int(payload.get("year", 0), 0)
    record_id = str(payload.get("record_id", "") or "").strip()
    compare_record_id = str(payload.get("compare_record_id", "") or "").strip()

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

    risks = []
    if isinstance(selected_result, dict):
        risks = selected_result.get("risks", []) if isinstance(selected_result.get("risks"), list) else []

    compare_data = None
    if compare_record_id and record_id:
        cmp_payload = _compare_payload(record_id, compare_record_id)
        if "error" not in cmp_payload:
            compare_data = cmp_payload

    raw = {
        "user_query": user_query,
        "company": company,
        "year": year,
        "risks": risks,
        "compare_data": compare_data,
    }
    report = _invoke_logic(raw)

    return {
        "ok": True,
        "query": user_query,
        "context": {
            "company": company,
            "year": year,
            "record_id": record_id,
            "compare_record_id": compare_record_id,
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
                            "/api/stock/quote?ticker=AAPL",
                            "/api/news?company=Apple&ticker=AAPL",
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
                items = [_record_summary(r, include_result=include_result) for r in out]
                self._send_json(200, {"ok": True, "count": len(items), "items": items})
                return

            if path.startswith("/api/records/"):
                record_id = path.split("/api/records/", 1)[-1].strip()
                if not record_id:
                    self._send_json(400, {"ok": False, "error": "record_id is required."})
                    return
                rec = next((r for r in _load_index() if str(r.get("record_id", "")) == record_id), None)
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
                if not ticker:
                    self._send_json(400, {"ok": False, "error": "ticker is required."})
                    return
                payload = _stock_quote(ticker)
                if payload.get("error"):
                    self._send_json(400, {"ok": False, **payload})
                    return
                self._send_json(200, {"ok": True, "data": payload})
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
