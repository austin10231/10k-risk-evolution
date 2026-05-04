"""ReAct tool registry for the chat agent.

Six tools exposed to the LLM via Bedrock Converse ``toolConfig`` (see
AGENT_UPGRADE_PLAN.md §2 for the full schema rationale):

    - load_company_risks       — fetch one filing's top risk factors
    - compare_risks            — diff two filings' risk factor sets
    - stock_quote              — latest price/change/volume for a ticker
    - fetch_news               — recent headlines for a company/ticker
    - list_available_companies — enumerate filings in the system
    - search_risks_by_keyword  — cross-filing keyword search over titles

Backend dependencies (``_load_index`` / ``_load_result`` / ``_stock_quote``
etc.) are resolved through a lazy module reference so this file is
import-safe even when ``agentcore_deploy.main`` hasn't fully loaded yet —
``main.py`` imports ``chat_agent`` which imports ``agent_tools``; the
backend handle is captured by ``build_tool_handlers`` at runtime, not at
module load.

The handlers themselves are kept stateless: every tool call resolves
data fresh from the backend (which has its own per-record cache). This
matches the ReAct contract — the LLM passes JSON args, gets JSON back —
and intentionally does NOT inherit user selection from the chat context.
The system prompt tells the LLM about the user's currently-selected
filing separately; if the LLM wants those risks it must call
``load_company_risks`` explicitly.

Output schemas are intentionally compact (we cap the deepest array at
``DEFAULT_TOP_RISKS_CAP`` etc.) so the ReAct loop's per-tool 4000-token
truncation rarely chops mid-record.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional


DEFAULT_TOP_RISKS_CAP = 20
DEFAULT_NEWS_LIMIT = 6
DEFAULT_NEWS_DAYS = 30
DEFAULT_LIST_LIMIT = 80
DEFAULT_SEARCH_LIMIT = 12


# ──────────────────────────────────────────────────────────────────────────────
# Tool specs (Bedrock Converse `toolConfig.tools` items)
# ──────────────────────────────────────────────────────────────────────────────

TOOL_SPECS: Dict[str, dict] = {
    "load_company_risks": {
        "toolSpec": {
            "name": "load_company_risks",
            "description": (
                "Load extracted Item 1A risk factors for one company-year filing. "
                "Returns the top risk factors ranked by priority bucket then RPI score, "
                "each with its category, title, priority, score, and the three scoring "
                "dimensions (financial_impact, likelihood, urgency). "
                "Use this whenever the user asks about a specific company's 10-K risks. "
                "If the company or year is not in the system, the response carries an "
                "`error` field — do not fabricate; tell the user what is available."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "company": {
                            "type": "string",
                            "description": "Company display name (e.g. 'Apple', 'Walmart') or ticker (e.g. 'AAPL', 'WMT'). Case-insensitive.",
                        },
                        "year": {
                            "type": "integer",
                            "minimum": 1995,
                            "maximum": 2030,
                            "description": "Filing year (the calendar year the 10-K covers).",
                        },
                        "max_risks": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": DEFAULT_TOP_RISKS_CAP,
                            "description": "Cap on returned sub-risks. Higher costs more tokens; default 20 is usually enough.",
                        },
                    },
                    "required": ["company", "year"],
                }
            },
        }
    },
    "compare_risks": {
        "toolSpec": {
            "name": "compare_risks",
            "description": (
                "Compare risk factors between two filings (same company across years OR "
                "different companies). Returns three groupings — new risks (only in B), "
                "removed risks (only in A), and common risks — plus high-level deltas in "
                "category coverage. Prefer this over two separate load_company_risks "
                "calls when both filings are known."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "company_a": {"type": "string"},
                        "year_a": {"type": "integer", "minimum": 1995, "maximum": 2030},
                        "company_b": {"type": "string"},
                        "year_b": {"type": "integer", "minimum": 1995, "maximum": 2030},
                    },
                    "required": ["company_a", "year_a", "company_b", "year_b"],
                }
            },
        }
    },
    "stock_quote": {
        "toolSpec": {
            "name": "stock_quote",
            "description": (
                "Fetch the latest stock quote (price, daily change, volume) for a ticker. "
                "Use when the user asks about current market price, today's move, or "
                "trading activity. Returns `error` if the ticker is unrecognized or the "
                "data provider is unreachable."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "description": "Stock ticker symbol (e.g. 'AAPL', 'TSLA'). Case-insensitive.",
                        }
                    },
                    "required": ["ticker"],
                }
            },
        }
    },
    "fetch_news": {
        "toolSpec": {
            "name": "fetch_news",
            "description": (
                "Fetch recent news headlines for a company or ticker. Returns top items "
                "with title, source, and published_at timestamp. Provide either `company` "
                "or `ticker` (or both — the more specific the better)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "company": {"type": "string"},
                        "ticker": {"type": "string"},
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 90,
                            "default": DEFAULT_NEWS_DAYS,
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 12,
                            "default": DEFAULT_NEWS_LIMIT,
                        },
                    },
                    "anyOf": [
                        {"required": ["company"]},
                        {"required": ["ticker"]},
                    ],
                }
            },
        }
    },
    "list_available_companies": {
        "toolSpec": {
            "name": "list_available_companies",
            "description": (
                "List companies that have at least one 10-K filing with extracted risks "
                "in the system. Returns ticker, industry, and the years available per "
                "company. Use this to validate a company name before calling "
                "load_company_risks, or when the user asks 'what companies do you have "
                "data for'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "industry": {
                            "type": "string",
                            "description": "Optional filter (e.g. 'Technology'). Omit to list all industries.",
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 200,
                            "default": DEFAULT_LIST_LIMIT,
                        },
                    },
                }
            },
        }
    },
    "search_risks_by_keyword": {
        "toolSpec": {
            "name": "search_risks_by_keyword",
            "description": (
                "Search across ALL filings for risk factor sub-risks whose title or "
                "category contains a keyword (case-insensitive substring match). Returns "
                "matches grouped by company-year, ranked by RPI score. Use this for "
                "cross-cutting questions like 'which companies mention AI risk' or "
                "'who flagged supply chain disruptions'."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "minLength": 2,
                            "description": "Search term, case-insensitive. Multi-word phrases are matched as substrings.",
                        },
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 30,
                            "default": DEFAULT_SEARCH_LIMIT,
                        },
                        "company_filter": {
                            "type": "string",
                            "description": "Optional: restrict to one company name or ticker.",
                        },
                    },
                    "required": ["keyword"],
                }
            },
        }
    },
}


def get_tool_specs() -> List[dict]:
    """Return the Converse-shaped tool list for ``invoke_llm_with_tools``."""
    return [TOOL_SPECS[name] for name in TOOL_SPECS]


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers (resolution + formatting)
# ──────────────────────────────────────────────────────────────────────────────


def _coerce_str(v: Any) -> str:
    return str(v or "").strip()


def _coerce_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _resolve_record(backend, company_or_ticker: str, year: int) -> Optional[dict]:
    """Match a record by either company name or ticker (case-insensitive)
    plus exact filing year. Returns the index entry (with ``record_id``) or
    ``None`` when no match. We intentionally do not LLM-fuzz-match — the
    LLM should call ``list_available_companies`` first if it is unsure."""
    needle = _coerce_str(company_or_ticker)
    yy = _coerce_int(year, 0)
    if not needle or yy <= 0:
        return None

    # Direct exact match by company name (case-insensitive).
    direct = backend._find_record(needle, yy)
    if direct:
        return direct

    # Ticker-style fallback: scan the index, compare ticker.
    ticker_needle = needle.upper().strip()
    if not ticker_needle:
        return None
    try:
        ticker_lookup = backend._build_ticker_lookup()
    except Exception:
        ticker_lookup = (None, None)
    for rec in backend._load_index():
        try:
            if _coerce_int(rec.get("year"), 0) != yy:
                continue
            t = backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
            if isinstance(t, str) and t.upper() == ticker_needle:
                return rec
        except Exception:
            continue
    return None


def _years_for_company(backend, company_or_ticker: str) -> List[int]:
    needle = _coerce_str(company_or_ticker).lower()
    ticker_needle = needle.upper()
    out: List[int] = []
    try:
        ticker_lookup = backend._build_ticker_lookup()
    except Exception:
        ticker_lookup = (None, None)
    for rec in backend._load_index():
        try:
            if str(rec.get("company", "") or "").strip().lower() == needle:
                out.append(_coerce_int(rec.get("year"), 0))
                continue
            t = backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
            if isinstance(t, str) and t.upper() == ticker_needle:
                out.append(_coerce_int(rec.get("year"), 0))
        except Exception:
            continue
    return sorted({y for y in out if y > 0})


def _flatten_risks_for_listing(risks_blocks: list, cap: int) -> List[dict]:
    """Walk ``result["risks"]`` and pull a flat list of sub-risks ranked by
    priority bucket (High>Medium>Low>None) then by score desc. Each item
    keeps the parent category, title, priority, score, and the three
    scoring dimensions. Capped to ``cap`` entries."""
    bucket_rank = {"High": 0, "Medium": 1, "Low": 2}
    flat: List[dict] = []
    for cat_block in risks_blocks if isinstance(risks_blocks, list) else []:
        if not isinstance(cat_block, dict):
            continue
        category = _coerce_str(cat_block.get("category"))
        for sr in cat_block.get("sub_risks", []) or []:
            if not isinstance(sr, dict):
                continue
            title = _coerce_str(sr.get("title"))
            if not title:
                continue
            flat.append({
                "category": category,
                "title": title,
                "priority": sr.get("priority"),
                "score": sr.get("score"),
                "financial_impact": sr.get("financial_impact"),
                "likelihood": sr.get("likelihood"),
                "urgency": sr.get("urgency"),
            })

    def _sort_key(item: dict) -> tuple:
        prio = bucket_rank.get(item.get("priority"), 3)
        score = item.get("score")
        try:
            score_v = -float(score) if score is not None else 1.0
        except Exception:
            score_v = 1.0
        return (prio, score_v)

    flat.sort(key=_sort_key)
    return flat[: max(1, int(cap or DEFAULT_TOP_RISKS_CAP))]


# ──────────────────────────────────────────────────────────────────────────────
# Handler factories — each returns ``(**kwargs) -> dict``
# ──────────────────────────────────────────────────────────────────────────────


def _make_load_company_risks(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        company = _coerce_str(kwargs.get("company"))
        year = _coerce_int(kwargs.get("year"), 0)
        max_risks = _coerce_int(kwargs.get("max_risks"), DEFAULT_TOP_RISKS_CAP)
        if not company or year <= 0:
            return {"error": "missing_params: company and year are required"}

        rec = _resolve_record(backend, company, year)
        if not rec:
            return {
                "error": "no_matching_filing",
                "requested": {"company": company, "year": year},
                "available_years_for_company": _years_for_company(backend, company),
            }

        record_id = _coerce_str(rec.get("record_id"))
        result = backend._load_result(record_id) if record_id else None
        if not isinstance(result, dict):
            return {"error": "result_not_loadable", "record_id": record_id}

        risks_blocks = result.get("risks", []) if isinstance(result.get("risks"), list) else []
        top_risks = _flatten_risks_for_listing(risks_blocks, max_risks)
        agent_report = result.get("agent_report") if isinstance(result.get("agent_report"), dict) else {}
        priority_matrix = agent_report.get("priority_matrix") if isinstance(agent_report.get("priority_matrix"), dict) else {}

        return {
            "record_id": record_id,
            "company": _coerce_str(rec.get("company")),
            "year": _coerce_int(rec.get("year"), year),
            "industry": _coerce_str(rec.get("industry")),
            "ticker": _coerce_str(rec.get("ticker")),
            "risk_block_count": len(risks_blocks),
            "sub_risk_total": sum(len(b.get("sub_risks", []) or []) for b in risks_blocks if isinstance(b, dict)),
            "scoring_status": _coerce_str(agent_report.get("scoring_status")) or "missing",
            "priority_counts": {
                bucket: _coerce_int((priority_matrix.get(bucket) or {}).get("count"), 0)
                for bucket in ("high", "medium", "low", "unscored")
                if isinstance(priority_matrix.get(bucket), dict)
            },
            "top_risks": top_risks,
        }

    return _handler


def _make_compare_risks(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        company_a = _coerce_str(kwargs.get("company_a"))
        company_b = _coerce_str(kwargs.get("company_b"))
        year_a = _coerce_int(kwargs.get("year_a"), 0)
        year_b = _coerce_int(kwargs.get("year_b"), 0)
        if not company_a or not company_b or year_a <= 0 or year_b <= 0:
            return {"error": "missing_params: company_a/year_a and company_b/year_b are required"}

        rec_a = _resolve_record(backend, company_a, year_a)
        rec_b = _resolve_record(backend, company_b, year_b)
        missing = []
        if not rec_a:
            missing.append({"company": company_a, "year": year_a})
        if not rec_b:
            missing.append({"company": company_b, "year": year_b})
        if missing:
            return {"error": "no_matching_filing", "missing": missing}

        rid_a = _coerce_str(rec_a.get("record_id"))
        rid_b = _coerce_str(rec_b.get("record_id"))
        try:
            payload = backend._compare_payload(rid_a, rid_b)
        except Exception as exc:
            return {"error": f"compare_payload_failed: {type(exc).__name__}: {exc}"}
        if isinstance(payload, dict) and payload.get("error"):
            return {"error": _coerce_str(payload.get("error"))}

        def _trim(items, cap=10):
            out = []
            for item in (items or [])[:cap]:
                if isinstance(item, dict):
                    out.append({
                        "category": _coerce_str(item.get("category")),
                        "title": _coerce_str(item.get("title")),
                        "score": item.get("score"),
                        "priority": item.get("priority"),
                    })
                elif isinstance(item, str):
                    out.append({"title": item})
            return out

        return {
            "filing_a": {
                "company": _coerce_str(rec_a.get("company")),
                "year": _coerce_int(rec_a.get("year"), year_a),
                "record_id": rid_a,
            },
            "filing_b": {
                "company": _coerce_str(rec_b.get("company")),
                "year": _coerce_int(rec_b.get("year"), year_b),
                "record_id": rid_b,
            },
            "new_risks": _trim(payload.get("new_risks")),
            "removed_risks": _trim(payload.get("removed_risks")),
            "common_risks_sample": _trim(payload.get("common_risks"), cap=5),
            "summary_stats": {
                "new_count": len(payload.get("new_risks") or []),
                "removed_count": len(payload.get("removed_risks") or []),
                "common_count": len(payload.get("common_risks") or []),
            },
        }

    return _handler


def _make_stock_quote(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        ticker = _coerce_str(kwargs.get("ticker")).upper()
        if not ticker:
            return {"error": "missing_params: ticker is required"}
        try:
            payload = backend._stock_quote(ticker, lite=True)
        except Exception as exc:
            return {"error": f"stock_quote_failed: {type(exc).__name__}: {exc}"}
        if isinstance(payload, dict) and payload.get("error"):
            return {"ticker": ticker, "error": _coerce_str(payload.get("error"))}
        if not isinstance(payload, dict):
            return {"ticker": ticker, "error": "stock_quote_returned_non_dict"}
        return {
            "ticker": ticker,
            "price": payload.get("price"),
            "change": payload.get("change"),
            "change_percent": payload.get("change_percent"),
            "volume": payload.get("volume"),
            "source": _coerce_str(payload.get("source")),
        }

    return _handler


def _make_fetch_news(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        company = _coerce_str(kwargs.get("company"))
        ticker = _coerce_str(kwargs.get("ticker")).upper()
        days = _coerce_int(kwargs.get("days"), DEFAULT_NEWS_DAYS)
        limit = _coerce_int(kwargs.get("limit"), DEFAULT_NEWS_LIMIT)
        if not company and not ticker:
            return {"error": "missing_params: company or ticker is required"}
        try:
            payload = backend._fetch_news(company, ticker, days, limit)
        except Exception as exc:
            return {"error": f"fetch_news_failed: {type(exc).__name__}: {exc}"}
        if isinstance(payload, dict) and payload.get("error"):
            return {"company": company, "ticker": ticker, "error": _coerce_str(payload.get("error"))}
        items_raw = payload.get("items", []) if isinstance(payload, dict) else []
        items: List[dict] = []
        for row in items_raw if isinstance(items_raw, list) else []:
            if not isinstance(row, dict):
                continue
            title = _coerce_str(row.get("title"))
            if not title:
                continue
            items.append({
                "title": title,
                "source": _coerce_str(row.get("source")),
                "published_at": _coerce_str(row.get("published_at")),
                "url": _coerce_str(row.get("url")),
            })
        return {
            "company": company,
            "ticker": ticker,
            "days": days,
            "items_count": len(items),
            "provider": _coerce_str((payload or {}).get("provider")) if isinstance(payload, dict) else "",
            "items": items[: max(1, limit)],
        }

    return _handler


def _make_list_available_companies(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        industry_filter = _coerce_str(kwargs.get("industry"))
        limit = _coerce_int(kwargs.get("limit"), DEFAULT_LIST_LIMIT)

        # Aggregate from the flat record list — works for both new and legacy layouts.
        try:
            records = backend._load_index()
        except Exception as exc:
            return {"error": f"load_index_failed: {type(exc).__name__}: {exc}"}
        try:
            ticker_lookup = backend._build_ticker_lookup()
        except Exception:
            ticker_lookup = (None, None)

        agg: Dict[str, dict] = {}
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            company = _coerce_str(rec.get("company"))
            if not company:
                continue
            industry = _coerce_str(rec.get("industry")) or "Other"
            if industry_filter and industry.lower() != industry_filter.lower():
                continue
            year = _coerce_int(rec.get("year"), 0)
            ticker = ""
            try:
                ticker = backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup) or ""
            except Exception:
                ticker = ""
            key = company.lower()
            block = agg.setdefault(key, {
                "company": company,
                "ticker": ticker.upper() if ticker else "",
                "industry": industry,
                "years": set(),
            })
            if year > 0:
                block["years"].add(year)
            if not block["ticker"] and ticker:
                block["ticker"] = ticker.upper()

        companies = []
        for block in agg.values():
            companies.append({
                "company": block["company"],
                "ticker": block["ticker"],
                "industry": block["industry"],
                "years": sorted(block["years"]),
            })
        # Sort: more years first, then alpha by company.
        companies.sort(key=lambda b: (-len(b["years"]), b["company"].lower()))
        capped = companies[: max(1, limit)]
        return {
            "industry_filter": industry_filter,
            "total": len(companies),
            "returned": len(capped),
            "companies": capped,
        }

    return _handler


def _make_search_risks_by_keyword(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        keyword = _coerce_str(kwargs.get("keyword"))
        max_results = _coerce_int(kwargs.get("max_results"), DEFAULT_SEARCH_LIMIT)
        company_filter = _coerce_str(kwargs.get("company_filter")).lower()
        if len(keyword) < 2:
            return {"error": "keyword_too_short"}
        needle = keyword.lower()

        try:
            records = backend._load_index()
        except Exception as exc:
            return {"error": f"load_index_failed: {type(exc).__name__}: {exc}"}

        hits: List[dict] = []
        for rec in records or []:
            if not isinstance(rec, dict):
                continue
            company = _coerce_str(rec.get("company"))
            if company_filter and company.lower() != company_filter and _coerce_str(rec.get("ticker")).lower() != company_filter:
                continue
            rid = _coerce_str(rec.get("record_id"))
            if not rid:
                continue
            try:
                result = backend._load_result(rid)
            except Exception:
                continue
            if not isinstance(result, dict):
                continue
            for cat_block in result.get("risks", []) or []:
                if not isinstance(cat_block, dict):
                    continue
                category = _coerce_str(cat_block.get("category"))
                for sr in cat_block.get("sub_risks", []) or []:
                    if not isinstance(sr, dict):
                        continue
                    title = _coerce_str(sr.get("title"))
                    if not title:
                        continue
                    if needle in title.lower() or needle in category.lower():
                        hits.append({
                            "company": company,
                            "year": _coerce_int(rec.get("year"), 0),
                            "record_id": rid,
                            "category": category,
                            "title": title,
                            "score": sr.get("score"),
                            "priority": sr.get("priority"),
                        })

        def _hit_sort(h: dict):
            score = h.get("score")
            try:
                return -float(score) if score is not None else 1.0
            except Exception:
                return 1.0

        hits.sort(key=_hit_sort)
        capped = hits[: max(1, max_results)]
        return {
            "keyword": keyword,
            "company_filter": company_filter,
            "hits_count": len(hits),
            "returned": len(capped),
            "hits": capped,
        }

    return _handler


# ──────────────────────────────────────────────────────────────────────────────
# Public entrypoint
# ──────────────────────────────────────────────────────────────────────────────


def build_tool_handlers(*, backend_module=None) -> Dict[str, Callable[..., dict]]:
    """Return a name → callable mapping suitable for the ReAct loop in
    ``chat_agent.run_chat_agent``. Each handler accepts ``**kwargs``
    (the LLM's ``toolUse.input`` dict, unpacked) and returns a JSON-
    serializable dict. Backend functions are resolved lazily so this
    file stays import-safe inside circular-ish import graphs."""
    backend = backend_module
    if backend is None:
        from agentcore_deploy import main as backend_resolved
        backend = backend_resolved

    return {
        "load_company_risks":       _make_load_company_risks(backend),
        "compare_risks":            _make_compare_risks(backend),
        "stock_quote":              _make_stock_quote(backend),
        "fetch_news":               _make_fetch_news(backend),
        "list_available_companies": _make_list_available_companies(backend),
        "search_risks_by_keyword":  _make_search_risks_by_keyword(backend),
    }


def serialize_tool_result(payload: Any, max_chars: int = 16000) -> dict:
    """Convert a handler's dict return into a Bedrock Converse
    ``toolResult.content`` block, with size-cap enforcement.

    Returns ``{"type": "json"|"text", "block": <converse content>, "status": "success"|"error"}``
    for the caller to wrap into ``{"toolResult": {"toolUseId": ..., "content": [block], "status": ...}}``.
    """
    is_error = isinstance(payload, dict) and "error" in payload
    try:
        as_json = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        as_json = json.dumps({"error": "serialize_failed"})

    if len(as_json) <= max_chars:
        return {
            "type": "json",
            "block": {"json": payload if isinstance(payload, (dict, list)) else {"value": payload}},
            "status": "error" if is_error else "success",
        }

    truncated = as_json[:max_chars] + '..."(truncated)"'
    return {
        "type": "text",
        "block": {"text": truncated},
        "status": "error" if is_error else "success",
    }
