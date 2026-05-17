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
import re
from typing import Any, Callable, Dict, List, Optional


DEFAULT_TOP_RISKS_CAP = 20
DEFAULT_NEWS_LIMIT = 6
DEFAULT_NEWS_DAYS = 30
DEFAULT_LIST_LIMIT = 80
DEFAULT_SEARCH_LIMIT = 12

APPLE_CONTAMINATION_TERMS = (
    "hotel",
    "hospitality",
    "reit",
    "real estate",
    "lodging",
    "property lease",
    "room revenue",
    "franchise",
)

FORCED_INDUSTRY_BY_TICKER = {
    "AAPL": "Technology",
}


# Chinese → canonical English company name aliases. Bedrock's LLM occasionally
# passes Chinese names verbatim from a Chinese-language user query into tool
# inputs (instead of translating internally). The values must match the
# `name` field in scripts/industry_mapping.py exactly (case-insensitive),
# since `_find_record` does an equality match on company name.
#
# Coverage is the 80-company global-brand subset that has Chinese names a
# native speaker would actually type — niche tickers (AES / Exelon / O /
# Equinix etc.) where English is the only common form are skipped to keep
# this list maintainable.
CHINESE_COMPANY_ALIASES: Dict[str, str] = {
    # Technology
    "苹果": "Apple",
    "苹果公司": "Apple",
    "微软": "Microsoft",
    "微软公司": "Microsoft",
    "谷歌": "Alphabet",
    "字母": "Alphabet",
    "字母表": "Alphabet",
    "英伟达": "NVIDIA",
    "辉达": "NVIDIA",
    "奥多比": "Adobe",
    "阿多比": "Adobe",
    "甲骨文": "Oracle",
    "思科": "Cisco",
    "英特尔": "Intel",
    "赛富时": "Salesforce",
    # Consumer cyclical
    "亚马逊": "Amazon",
    "特斯拉": "Tesla",
    "家得宝": "Home Depot",
    "麦当劳": "McDonalds",
    "耐克": "Nike",
    "星巴克": "Starbucks",
    "缤客": "Booking Holdings",
    "缤客控股": "Booking Holdings",
    "劳氏": "Lowes",
    "优步": "Uber",
    # Consumer defensive
    "宝洁": "Procter & Gamble",
    "可口可乐": "Coca-Cola",
    "百事": "PepsiCo",
    "百事可乐": "PepsiCo",
    "沃尔玛": "Walmart",
    "好市多": "Costco",
    "开市客": "Costco",
    "菲利普莫里斯": "Philip Morris",
    "高露洁": "Colgate-Palmolive",
    "高露洁棕榄": "Colgate-Palmolive",
    "亿滋": "Mondelez",
    "克罗格": "Kroger",
    "塔吉特": "Target",
    # Communication services
    "元": "Meta",
    "脸书": "Meta",
    "脸谱": "Meta",
    "网飞": "Netflix",
    "奈飞": "Netflix",
    "迪士尼": "Disney",
    "迪斯尼": "Disney",
    "康卡斯特": "Comcast",
    "美国电话电报": "AT&T",
    # Industrials
    "波音": "Boeing",
    "卡特彼勒": "Caterpillar",
    "霍尼韦尔": "Honeywell",
    "联合太平洋": "Union Pacific",
    "通用电气": "General Electric",
    "洛克希德马丁": "Lockheed Martin",
    "洛克希德": "Lockheed Martin",
    "雷神": "RTX",
    "雷神技术": "RTX",
    "迪尔": "Deere",
    "约翰迪尔": "Deere",
    "摩托罗拉": "Motorola Solutions",
    # Financial services
    "摩根大通": "JPMorgan",
    "高盛": "Goldman Sachs",
    "摩根士丹利": "Morgan Stanley",
    "美国银行": "Bank of America",
    "维萨": "Visa",
    "万事达": "Mastercard",
    "万事达卡": "Mastercard",
    "贝莱德": "BlackRock",
    "伯克希尔": "Berkshire Hathaway",
    "伯克希尔哈撒韦": "Berkshire Hathaway",
    # Energy
    "埃克森美孚": "ExxonMobil",
    "埃克森": "ExxonMobil",
    "雪佛龙": "Chevron",
    "康菲石油": "ConocoPhillips",
    "斯伦贝谢": "Schlumberger",
    "马拉松石油": "Marathon Petroleum",
    "瓦莱罗": "Valero Energy",
    # Utilities
    "杜克能源": "Duke Energy",
    "南方电力": "Southern Company",
    "下一时代能源": "NextEra Energy",
    "新世纪能源": "NextEra Energy",
    "道明尼能源": "Dominion Energy",
    # Basic materials
    "林德": "Linde",
    "空气化工": "Air Products",
    "自由港": "Freeport-McMoRan",
    "自由港麦克莫兰": "Freeport-McMoRan",
    "纽蒙特": "Newmont",
    "陶氏": "Dow",
    "杜邦": "DuPont",
    # Real estate
    "普洛斯": "Prologis",
    "美国电塔": "American Tower",
    "皇冠城堡": "Crown Castle",
    "西蒙地产": "Simon Property",
    # Healthcare
    "联合健康": "UnitedHealth",
    "强生": "Johnson & Johnson",
    "辉瑞": "Pfizer",
    "礼来": "Eli Lilly",
    "礼来公司": "Eli Lilly",
    "艾伯维": "AbbVie",
    "默克": "Merck",
    "默沙东": "Merck",
    "赛默飞": "Thermo Fisher",
    "赛默飞世尔": "Thermo Fisher",
    "雅培": "Abbott",
}

# Market-chat fallback mapping used when backend resolve-ticker is unavailable
# or lacks a company index (e.g. cold/demo deployments). Keys are normalized
# company aliases in uppercase.
COMPANY_TICKER_HINTS: Dict[str, str] = {
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "NVIDIA": "NVDA",
    "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL",
    "AMAZON": "AMZN",
    "META": "META",
    "TESLA": "TSLA",
    "NETFLIX": "NFLX",
    "ORACLE": "ORCL",
    "INTEL": "INTC",
    "AMD": "AMD",
    "QUALCOMM": "QCOM",
    "JPMORGAN": "JPM",
    "BERKSHIRE HATHAWAY": "BRK.B",
    "JOHNSON & JOHNSON": "JNJ",
    "ELI LILLY": "LLY",
    "PFIZER": "PFE",
    "ABBVIE": "ABBV",
    "ABBOTT": "ABT",
    "THERMO FISHER": "TMO",
    "MERCK": "MRK",
    "EXXONMOBIL": "XOM",
    "CHEVRON": "CVX",
    "WALMART": "WMT",
    "COSTCO": "COST",
}


def _resolve_company_alias(raw: Any) -> str:
    """Translate a known Chinese company-name alias to its canonical English
    form (matches ``industry_mapping.COMPANIES[*].name``). Pass-through
    when the input is already English or not in the table.
    """
    s = _coerce_str(raw)
    if not s:
        return s
    return CHINESE_COMPANY_ALIASES.get(s, s)


def _ticker_hint_from_company(raw: Any) -> str:
    s = _resolve_company_alias(raw)
    key = _coerce_str(s).upper()
    if not key:
        return ""
    return _coerce_str(COMPANY_TICKER_HINTS.get(key)).upper()


def _is_ticker_like(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", value or ""))


def _resolve_ticker_from_company_backend(backend, raw_value: Any) -> str:
    hinted = _ticker_hint_from_company(raw_value)
    if hinted:
        return hinted
    company_hint = _resolve_company_alias(raw_value)
    if not company_hint:
        return ""
    resolver = getattr(backend, "_resolve_ticker_for_company", None)
    if not callable(resolver):
        return ""
    try:
        resolved = resolver(company=company_hint, ticker_hint="")
    except Exception:
        return ""
    if not isinstance(resolved, dict) or not resolved.get("ok"):
        return ""
    ticker = _coerce_str(resolved.get("ticker")).upper()
    return ticker if _is_ticker_like(ticker) else ""


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
                "Use this whenever the user asks about a specific company's 10-K/10-Q risks. "
                "If the company/year is missing from local index, backend will attempt "
                "a one-shot SEC EDGAR auto-fetch for that year first. "
                "If still unavailable, the response carries an `error` field. "
                "Use returned `retrieval_mode` to tell user whether data came from "
                "existing index or live auto-fetch."
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
                            "description": "Filing year (the calendar year the filing covers).",
                        },
                        "filing_type": {
                            "type": "string",
                            "enum": ["10-K", "10-Q"],
                            "description": "Optional filing type selector. Defaults to 10-K.",
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
                "List companies that have at least one filing (10-K or 10-Q) with extracted risks "
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


def _coerce_filing_type(value: Any) -> str:
    txt = _coerce_str(value).upper()
    if txt in {"10Q", "10-Q"}:
        return "10-Q"
    return "10-K"


def _resolve_record(backend, company_or_ticker: str, year: int, filing_type: str = "") -> Optional[dict]:
    """Match a record by either company name or ticker (case-insensitive)
    plus exact filing year. Returns the index entry (with ``record_id``) or
    ``None`` when no match. We intentionally do not LLM-fuzz-match — the
    LLM should call ``list_available_companies`` first if it is unsure.

    Order: (1) direct English company-name match → (2) Chinese alias →
    English match → (3) ticker match. Step 2 catches the "苹果" / "微软"
    style of LLM tool input that comes through verbatim from a Chinese
    user query without internal translation.
    """
    raw = _coerce_str(company_or_ticker)
    yy = _coerce_int(year, 0)
    ft = _coerce_filing_type(filing_type) if _coerce_str(filing_type) else ""
    if not raw or yy <= 0:
        return None

    aliased = _resolve_company_alias(raw)
    ticker_hint = _resolve_ticker_from_company_backend(backend, raw)
    raw_lower = raw.lower()
    aliased_lower = aliased.lower()

    # First pass: strict company-name match in the requested year.
    # If duplicates exist (dirty historical data), prefer ticker match.
    name_candidates: List[dict] = []
    for rec in backend._load_index():
        if not isinstance(rec, dict):
            continue
        try:
            if _coerce_int(rec.get("year"), 0) != yy:
                continue
            if ft and _coerce_filing_type(rec.get("filing_type")) != ft:
                continue
            rec_name = _coerce_str(rec.get("company")).lower()
            if rec_name in {raw_lower, aliased_lower}:
                name_candidates.append(rec)
        except Exception:
            continue
    if name_candidates:
        if ticker_hint:
            try:
                ticker_lookup = backend._build_ticker_lookup()
            except Exception:
                ticker_lookup = (None, None)
            ticker_matched = []
            for rec in name_candidates:
                try:
                    t = _coerce_str(
                        backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
                    ).upper()
                except Exception:
                    t = ""
                if t == ticker_hint:
                    ticker_matched.append(rec)
            if ticker_matched:
                ticker_matched.sort(key=lambda r: _coerce_str(r.get("created_at")), reverse=True)
                return ticker_matched[0]
        name_candidates.sort(key=lambda r: _coerce_str(r.get("created_at")), reverse=True)
        return name_candidates[0]

    ticker_needle = raw.upper().strip()
    if not _is_ticker_like(ticker_needle):
        ticker_needle = ticker_hint
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
            if ft and _coerce_filing_type(rec.get("filing_type")) != ft:
                continue
            t = backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup)
            if isinstance(t, str) and t.upper() == ticker_needle:
                return rec
        except Exception:
            continue
    return None


def _years_for_company(backend, company_or_ticker: str) -> List[int]:
    raw = _coerce_str(company_or_ticker).strip()
    canonical = _resolve_company_alias(raw)        # 苹果 → Apple before scanning
    company_needle = canonical.lower()
    ticker_needle = raw.upper()
    out: List[int] = []
    try:
        ticker_lookup = backend._build_ticker_lookup()
    except Exception:
        ticker_lookup = (None, None)
    for rec in backend._load_index():
        try:
            if str(rec.get("company", "") or "").strip().lower() == company_needle:
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


def _canonical_industry(company: str, ticker: str, fallback: str) -> str:
    tk = _coerce_str(ticker).upper()
    if tk in FORCED_INDUSTRY_BY_TICKER:
        return FORCED_INDUSTRY_BY_TICKER[tk]
    if "apple" in _coerce_str(company).lower():
        return "Technology"
    out = _coerce_str(fallback) or "Other"
    return out


def _is_probable_apple_contamination(result_payload: dict) -> bool:
    if not isinstance(result_payload, dict):
        return False
    risks_blocks = result_payload.get("risks", []) if isinstance(result_payload.get("risks"), list) else []
    if not risks_blocks:
        return False
    sample_text: List[str] = []
    for cat_block in risks_blocks[:6]:
        if not isinstance(cat_block, dict):
            continue
        sample_text.append(_coerce_str(cat_block.get("category")))
        for sr in (cat_block.get("sub_risks", []) or [])[:8]:
            if not isinstance(sr, dict):
                continue
            sample_text.append(_coerce_str(sr.get("title")))
    blob = " ".join(x.lower() for x in sample_text if x).strip()
    if not blob:
        return False
    contamination_hits = sum(1 for term in APPLE_CONTAMINATION_TERMS if term in blob)
    return contamination_hits >= 2


def _ensure_record_integrity(backend, rec: dict, requested_company: str, requested_year: int) -> tuple[dict, dict]:
    """Best-effort filing integrity guard.

    For Apple/AAPL, detect known legacy contamination patterns (hotel/REIT
    vocabulary mixed into Apple risk payload) and force one SEC re-fetch for
    that year. Returns (record, note_dict)."""
    note: dict = {}
    if not isinstance(rec, dict):
        return rec, note
    company_text = _coerce_str(rec.get("company") or requested_company).lower()
    ticker = _coerce_str(rec.get("ticker")).upper()
    if not ticker:
        try:
            ticker_lookup = backend._build_ticker_lookup()
            ticker = _coerce_str(backend._resolve_record_ticker(rec, ticker_lookup=ticker_lookup)).upper()
        except Exception:
            ticker = ""
    is_apple_target = ("apple" in company_text) or (ticker == "AAPL")
    if not is_apple_target:
        return rec, note

    rid = _coerce_str(rec.get("record_id"))
    payload = backend._load_result(rid) if rid else None
    if not _is_probable_apple_contamination(payload if isinstance(payload, dict) else {}):
        return rec, note

    auto_fetch = getattr(backend, "_auto_fetch_and_extract", None)
    if not callable(auto_fetch):
        return rec, {"integrity_warning": "apple_contamination_detected_but_no_autofetch"}

    year = _coerce_int(rec.get("year"), requested_year)
    if year <= 0:
        return rec, {"integrity_warning": "apple_contamination_detected_but_invalid_year"}

    try:
        fetched = auto_fetch(
            company="Apple",
            ticker="AAPL",
            industry="Technology",
            filing_type="10-K",
            start_year=year,
            end_year=year,
        )
    except Exception as exc:
        return rec, {"integrity_warning": f"apple_refetch_failed:{type(exc).__name__}:{exc}"}

    note = {
        "integrity_repair": "apple_refetch_attempted",
        "integrity_refetch_count": _coerce_int((fetched or {}).get("count"), 0) if isinstance(fetched, dict) else 0,
    }
    repaired = _resolve_record(backend, "Apple", year)
    return (repaired if repaired else rec), note


# ──────────────────────────────────────────────────────────────────────────────
# Handler factories — each returns ``(**kwargs) -> dict``
# ──────────────────────────────────────────────────────────────────────────────


def _make_load_company_risks(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        company = _coerce_str(kwargs.get("company"))
        year = _coerce_int(kwargs.get("year"), 0)
        filing_type = _coerce_filing_type(kwargs.get("filing_type", "10-K"))
        max_risks = _coerce_int(kwargs.get("max_risks"), DEFAULT_TOP_RISKS_CAP)
        if not company or year <= 0:
            return {"error": "missing_params: company and year are required"}

        company_aliased = _resolve_company_alias(company)
        rec = _resolve_record(backend, company_aliased or company, year, filing_type)
        auto_fetch_attempt = {}
        retrieval_mode = "existing_index"
        if not rec:
            auto_fetch = getattr(backend, "_auto_fetch_and_extract", None)
            if callable(auto_fetch):
                ticker_hint = _resolve_ticker_from_company_backend(backend, company_aliased or company)
                try:
                    fetched = auto_fetch(
                        company=company_aliased or company,
                        ticker=ticker_hint,
                        industry="Other",
                        filing_type=filing_type,
                        start_year=year,
                        end_year=year,
                    )
                except Exception as exc:
                    fetched = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                if isinstance(fetched, dict):
                    auto_fetch_attempt = {
                        "ok": bool(fetched.get("ok")),
                        "count": _coerce_int(fetched.get("count"), 0),
                        "error": _coerce_str(fetched.get("error")),
                        "skipped": fetched.get("skipped", [])[:2] if isinstance(fetched.get("skipped"), list) else [],
                    }
                if isinstance(fetched, dict) and _coerce_int(fetched.get("count"), 0) > 0:
                    rec = _resolve_record(backend, company_aliased or company, year, filing_type)
                    retrieval_mode = "sec_auto_fetch"

        if not rec:
            return {
                "error": "no_matching_filing",
                "requested": {"company": company_aliased or company, "year": year},
                "available_years_for_company": _years_for_company(backend, company_aliased or company),
                "filing_type": filing_type,
                "auto_fetch_attempt": auto_fetch_attempt,
                "retrieval_mode": "missing_after_autofetch",
            }

        rec, integrity_note = _ensure_record_integrity(
            backend,
            rec,
            requested_company=company_aliased or company,
            requested_year=year,
        )
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
            "filing_type": _coerce_str(rec.get("filing_type")) or filing_type,
            "industry": _canonical_industry(
                _coerce_str(rec.get("company")),
                _coerce_str(rec.get("ticker")),
                _coerce_str(rec.get("industry")),
            ),
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
            "auto_fetch_attempt": auto_fetch_attempt,
            "retrieval_mode": retrieval_mode,
            **(integrity_note if isinstance(integrity_note, dict) else {}),
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

        rec_a, integrity_note_a = _ensure_record_integrity(
            backend,
            rec_a,
            requested_company=company_a,
            requested_year=year_a,
        )
        rec_b, integrity_note_b = _ensure_record_integrity(
            backend,
            rec_b,
            requested_company=company_b,
            requested_year=year_b,
        )

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
            "integrity_notes": {
                "filing_a": integrity_note_a if isinstance(integrity_note_a, dict) else {},
                "filing_b": integrity_note_b if isinstance(integrity_note_b, dict) else {},
            },
        }

    return _handler


def _make_stock_quote(backend) -> Callable[..., dict]:
    def _resolve_ticker_from_company(raw_value: str) -> str:
        return _resolve_ticker_from_company_backend(backend, raw_value)

    def _handler(**kwargs) -> dict:
        ticker_raw = _coerce_str(kwargs.get("ticker"))
        if not ticker_raw:
            return {"error": "missing_params: ticker is required"}

        requested = ticker_raw.upper()
        ticker = requested if _is_ticker_like(requested) else ""
        resolved_from_company = ""
        if not ticker:
            resolved_from_company = _resolve_ticker_from_company(ticker_raw)
            ticker = resolved_from_company

        try:
            payload = backend._stock_quote(ticker, lite=False) if ticker else {"error": "unresolved_ticker"}
        except Exception as exc:
            return {"error": f"stock_quote_failed: {type(exc).__name__}: {exc}"}

        if isinstance(payload, dict) and payload.get("error") and not resolved_from_company:
            fallback_ticker = _resolve_ticker_from_company(ticker_raw)
            if fallback_ticker and fallback_ticker != ticker:
                resolved_from_company = fallback_ticker
                ticker = fallback_ticker
                try:
                    payload = backend._stock_quote(ticker, lite=False)
                except Exception as exc:
                    return {"error": f"stock_quote_failed: {type(exc).__name__}: {exc}"}

        if isinstance(payload, dict) and payload.get("error"):
            return {"ticker": ticker, "error": _coerce_str(payload.get("error"))}
        if not isinstance(payload, dict):
            return {"ticker": ticker, "error": "stock_quote_returned_non_dict"}
        return {
            "ticker": ticker,
            "requested": ticker_raw,
            "resolved_from_company": resolved_from_company or "",
            "price": payload.get("price"),
            "change": payload.get("change"),
            "change_percent": payload.get("change_percent"),
            "volume": payload.get("volume"),
            "source": _coerce_str(payload.get("quote_source") or payload.get("history_source") or payload.get("source")),
            "exchange": payload.get("exchange"),
        }

    return _handler


def _make_fetch_news(backend) -> Callable[..., dict]:
    def _handler(**kwargs) -> dict:
        company = _resolve_company_alias(_coerce_str(kwargs.get("company")))
        ticker = _coerce_str(kwargs.get("ticker")).upper()
        days = _coerce_int(kwargs.get("days"), DEFAULT_NEWS_DAYS)
        limit = _coerce_int(kwargs.get("limit"), DEFAULT_NEWS_LIMIT)
        if not company and not ticker:
            return {"error": "missing_params: company or ticker is required"}

        resolved_from_company = ""
        if not ticker and company:
            resolved_from_company = _resolve_ticker_from_company_backend(backend, company)
            ticker = resolved_from_company or ticker

        try:
            payload = backend._fetch_news(company, ticker, days, limit)
        except Exception as exc:
            return {"error": f"fetch_news_failed: {type(exc).__name__}: {exc}"}

        if isinstance(payload, dict):
            items_raw0 = payload.get("items", []) if isinstance(payload.get("items"), list) else []
            should_retry = bool(payload.get("error")) or (not items_raw0 and company and not resolved_from_company)
        else:
            should_retry = False
        if should_retry:
            fallback_ticker = _resolve_ticker_from_company_backend(backend, company)
            if fallback_ticker and fallback_ticker != ticker:
                resolved_from_company = fallback_ticker
                ticker = fallback_ticker
                try:
                    payload = backend._fetch_news(company, ticker, days, limit)
                except Exception as exc:
                    return {"error": f"fetch_news_failed: {type(exc).__name__}: {exc}"}

        if isinstance(payload, dict) and payload.get("error"):
            return {
                "company": company,
                "ticker": ticker,
                "resolved_from_company": resolved_from_company or "",
                "error": _coerce_str(payload.get("error")),
            }
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
            "resolved_from_company": resolved_from_company or "",
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
                "industry": _canonical_industry(company, ticker, industry),
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
        # Resolve Chinese alias on company_filter before lowercasing so
        # `company_filter="苹果"` correctly narrows to Apple.
        company_filter_raw = _coerce_str(kwargs.get("company_filter"))
        company_filter = _resolve_company_alias(company_filter_raw).lower()
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
