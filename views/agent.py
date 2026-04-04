"""Agent page — Risk Intelligence Agent dashboard."""

import streamlit as st
import json
import re
import uuid
import copy
import hashlib
import traceback
import statistics
import boto3
from botocore.config import Config
import yfinance as yf

from storage.store import (
    load_index,
    get_result,
    save_agent_report,
    get_company_ticker,
    upsert_company_ticker,
)
from core.agent import run_agent
from core.comparator import compare_risks


SUGGESTED_QUERIES = [
    "Prioritize all risks and identify the top 5 most critical threats",
    "Which risks pose the greatest financial impact?",
    "Summarize the emerging risks and recommend monitoring actions",
    "Compare risks year-over-year and highlight what changed most",
    "What are the most urgent risks requiring immediate attention?",
]

PRIORITY_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
RATING_COLORS = {
    "High": "#ef4444", "Medium-High": "#f97316",
    "Medium": "#f59e0b", "Medium-Low": "#84cc16", "Low": "#22c55e",
}


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_stock_history_1y(ticker: str):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return []
    hist = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return []
    df = hist.reset_index()
    if "Date" not in df.columns:
        return []
    rows = []
    for _, row in df.iterrows():
        dt = row.get("Date")
        close = row.get("Close")
        if dt is None or close is None or close != close:
            continue
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "close": float(close),
        })
    return rows


def _trailing_return(history, days: int):
    if not history or len(history) < 2:
        return None
    closes = [float(p["close"]) for p in history]
    if len(closes) <= days:
        base = closes[0]
    else:
        base = closes[-(days + 1)]
    latest = closes[-1]
    if base == 0:
        return None
    return ((latest - base) / base) * 100.0


def _annualized_volatility(history):
    if not history or len(history) < 3:
        return None
    closes = [float(p["close"]) for p in history]
    daily_returns = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        curr = closes[i]
        if prev > 0:
            daily_returns.append((curr / prev) - 1.0)
    if len(daily_returns) < 2:
        return None
    return statistics.stdev(daily_returns) * (252 ** 0.5) * 100.0


def _max_drawdown(history):
    if not history:
        return None
    closes = [float(p["close"]) for p in history]
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = ((c - peak) / peak) * 100.0
            if dd < max_dd:
                max_dd = dd
    return max_dd


def _alignment_sentence(overall_risk_rating: str, ret_90: float | None, max_dd: float | None, excess_vs_spy: float | None):
    high_risk = str(overall_risk_rating) in {"High", "Medium-High"}
    pressure_signals = 0
    if ret_90 is not None and ret_90 < -5:
        pressure_signals += 1
    if max_dd is not None and max_dd < -20:
        pressure_signals += 1
    if excess_vs_spy is not None and excess_vs_spy < -5:
        pressure_signals += 1
    under_pressure = pressure_signals >= 1

    if high_risk and under_pressure:
        return "Risk-Market Alignment: High risk and market performance are directionally aligned (both indicate pressure)."
    if high_risk and not under_pressure:
        return "Risk-Market Alignment: Risk is elevated, but market pressure is not obvious yet (early-warning mismatch)."
    if (not high_risk) and under_pressure:
        return "Risk-Market Alignment: Market is under pressure while risk rating is lower (divergence to monitor)."
    return "Risk-Market Alignment: Risk and market signals are broadly aligned on the stable side."


def _build_stock_context_summary(ticker: str):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return "", "", {}

    try:
        points = _fetch_stock_history_1y(symbol)
    except Exception as exc:
        return "", f"Failed to load market data for `{symbol}`: {exc}", {}

    if len(points) < 2:
        return "", f"Could not fetch enough market data for `{symbol}`. Please verify the ticker.", {}

    closes = [p["close"] for p in points]
    first_close = closes[0]
    latest_close = closes[-1]
    if first_close == 0:
        return "", f"Market data for `{symbol}` is invalid (first close is zero).", {}

    one_year_change = ((latest_close - first_close) / first_close) * 100
    year_high = max(closes)
    year_low = min(closes)

    ret_30 = _trailing_return(points, 30)
    ret_90 = _trailing_return(points, 90)
    ann_vol = _annualized_volatility(points)
    max_dd = _max_drawdown(points)

    spy_ret_90 = None
    try:
        spy_points = _fetch_stock_history_1y("SPY")
        spy_ret_90 = _trailing_return(spy_points, 90)
    except Exception:
        spy_ret_90 = None
    excess_vs_spy_90 = None
    if ret_90 is not None and spy_ret_90 is not None:
        excess_vs_spy_90 = ret_90 - spy_ret_90

    recent_window = 21 if len(closes) >= 21 else len(closes)
    recent_base = closes[-recent_window]
    recent_change = 0.0 if recent_base == 0 else ((latest_close - recent_base) / recent_base) * 100
    if recent_change > 2:
        recent_trend = "uptrend"
    elif recent_change < -2:
        recent_trend = "downtrend"
    else:
        recent_trend = "sideways"

    def _fmt_pct(v):
        if v is None:
            return "N/A"
        return f"{v:+.2f}%"

    summary = (
        f"Ticker: {symbol}. "
        f"1Y change: {one_year_change:+.2f}%. "
        f"52-week high: {year_high:.2f}. "
        f"52-week low: {year_low:.2f}. "
        f"Latest close: {latest_close:.2f}. "
        f"Recent 1-month trend: {recent_trend} ({recent_change:+.2f}%). "
        f"30D return: {_fmt_pct(ret_30)}. "
        f"90D return: {_fmt_pct(ret_90)}. "
        f"Annualized volatility: {_fmt_pct(ann_vol)}. "
        f"Max drawdown (1Y): {_fmt_pct(max_dd)}. "
        f"Excess return vs SPY (90D): {_fmt_pct(excess_vs_spy_90)}."
    )
    metrics = {
        "ticker": symbol,
        "return_30d_pct": ret_30,
        "return_90d_pct": ret_90,
        "annualized_volatility_pct": ann_vol,
        "max_drawdown_pct": max_dd,
        "excess_return_vs_spy_90d_pct": excess_vs_spy_90,
    }
    return summary, "", metrics


def _badge(text, color):
    return (
        f'<span style="background:{color}20; color:{color}; border:1px solid {color}40;'
        f'padding:2px 9px; border-radius:12px; font-size:0.75rem; font-weight:600;">{text}</span>'
    )


def _stable_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _build_agent_cache_key(
    mode: str,
    company: str,
    year: int,
    user_query: str,
    risks: list,
    compare_data: dict | None,
    runtime_arn: str = "",
    runtime_qualifier: str = "",
    runtime_session_id: str = "",
) -> str:
    payload = {
        "mode": mode,
        "company": company,
        "year": year,
        "user_query": user_query,
        "risks": risks,
        "compare_data": compare_data,
        "runtime_arn": runtime_arn,
        "runtime_qualifier": runtime_qualifier,
        "runtime_session_id": runtime_session_id,
    }
    raw = _stable_json(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _agent_cache():
    if "agent_report_cache" not in st.session_state:
        st.session_state["agent_report_cache"] = {}
    return st.session_state["agent_report_cache"]


def _cache_get(cache_key: str):
    cache = _agent_cache()
    val = cache.get(cache_key)
    return copy.deepcopy(val) if val is not None else None


def _cache_set(cache_key: str, report: dict, max_size: int = 30):
    cache = _agent_cache()
    cache[cache_key] = copy.deepcopy(report)
    # Keep cache bounded to avoid unbounded session growth.
    if len(cache) > max_size:
        oldest_key = next(iter(cache))
        if oldest_key != cache_key:
            cache.pop(oldest_key, None)


def _is_error_report(report: dict) -> bool:
    summary = str((report or {}).get("executive_summary", "") or "")
    return "Report generation encountered an error:" in summary


def _secret_get(key, default=""):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default


def _extract_json_obj(text: str):
    s = re.sub(r"```json|```", "", str(text or "")).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    left = s.find("{")
    right = s.rfind("}")
    if left >= 0 and right > left:
        try:
            return json.loads(s[left:right + 1])
        except Exception:
            return None
    return None


def _normalize_report_payload(report: dict, company: str, year: int, user_query: str, mode_label: str) -> dict:
    def _looks_like_report(d: dict) -> bool:
        return isinstance(d, dict) and (
            "priority_matrix" in d or
            "executive_summary" in d or
            "overall_risk_rating" in d or
            "enriched_risks" in d
        )

    def _coerce_to_dict(obj):
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            parsed = _extract_json_obj(obj)
            if isinstance(parsed, dict):
                return parsed
        return None

    root = _coerce_to_dict(report) or {}
    out = dict(root)

    # Handle common wrapper shapes: {"report": {...}} or {"result": "...json..."}
    if not _looks_like_report(out):
        for wrapper_key in (
            "report", "result", "data", "output", "response", "body", "payload", "message", "text"
        ):
            wrapped = _coerce_to_dict(out.get(wrapper_key))
            if _looks_like_report(wrapped):
                out = dict(wrapped)
                break

    out.setdefault("company", company)
    out.setdefault("year", year)
    out.setdefault("user_query", user_query)
    out.setdefault("priority_matrix", {
        "high": {"count": 0, "top": []},
        "medium": {"count": 0, "top": []},
        "low": {"count": 0, "top": []},
    })
    out.setdefault("executive_summary", "")
    out.setdefault("key_findings", [])
    out.setdefault("recommendations", [])
    out.setdefault("risk_themes", [])
    out.setdefault("overall_risk_rating", "Unknown")
    out.setdefault("compare_insights", "")
    out.setdefault("enriched_risks", [])
    steps = out.get("agent_steps", [])
    if not isinstance(steps, list):
        steps = [str(steps)]
    out["agent_steps"] = [f"🚦 Execution mode: {mode_label}", *steps]
    return out


def _get_agentcore_client(read_timeout: int = 60):
    region = _secret_get("AGENTCORE_REGION", _secret_get("BEDROCK_REGION", "us-west-2"))
    client_config = Config(
        connect_timeout=10,
        read_timeout=read_timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return boto3.client(
        "bedrock-agentcore",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=region,
        config=client_config,
    )


def _read_agentcore_response_text(resp: dict) -> str:
    body = resp.get("response")
    if body is None:
        return ""

    ctype = str(resp.get("contentType", "")).lower()
    if "text/event-stream" in ctype:
        chunks = []
        for raw_line in body.iter_lines(chunk_size=1024):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            if line.startswith("data:"):
                payload = line[5:].strip()
                if payload and payload != "[DONE]":
                    chunks.append(payload)
            else:
                chunks.append(line)
        return "\n".join(chunks)

    payload = body.read()
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="ignore")
    return str(payload)


def _ensure_runtime_session_id(value) -> str:
    sid = str(value or "").strip()
    # AgentCore requires runtimeSessionId min length 33.
    if len(sid) < 33:
        sid = str(uuid.uuid4())
    return sid


def _invoke_agentcore_runtime(
    agent_runtime_arn: str,
    qualifier: str,
    runtime_session_id: str,
    company: str,
    year: int,
    user_query: str,
    risks: list,
    compare_data: dict | None,
) -> dict:
    runtime_session_id = _ensure_runtime_session_id(runtime_session_id)
    client = _get_agentcore_client(read_timeout=300)
    safe_company = str(company or "")
    safe_user_query = str(user_query or "")
    try:
        safe_year = int(year)
    except Exception:
        safe_year = 0
    safe_risks = risks if isinstance(risks, list) else []
    safe_compare_data = compare_data if isinstance(compare_data, dict) else None
    aws_ctx = {
        "aws_access_key_id": _secret_get("AWS_ACCESS_KEY_ID", ""),
        "aws_secret_access_key": _secret_get("AWS_SECRET_ACCESS_KEY", ""),
        "aws_session_token": _secret_get("AWS_SESSION_TOKEN", ""),
        "bedrock_region": _secret_get("BEDROCK_REGION", _secret_get("AGENTCORE_REGION", "us-west-2")),
    }
    if not aws_ctx["aws_access_key_id"] or not aws_ctx["aws_secret_access_key"]:
        aws_ctx = {}

    input_payload = {
        "user_query": safe_user_query,
        "company": safe_company,
        "year": safe_year,
        "risks": safe_risks,
        "compare_data": safe_compare_data,
        "_aws": aws_ctx,
    }
    request_payload = {
        # Keep required fields directly on top-level.
        "company": safe_company,
        "year": safe_year,
        "user_query": safe_user_query,
        "risks": safe_risks,
        "compare_data": safe_compare_data,
        "_aws": aws_ctx,
        # Compatibility keys for runtimes parsing alternate contracts.
        "prompt": safe_user_query,
        "input": input_payload,
        "body": json.dumps(input_payload, ensure_ascii=False, default=str),
    }

    kwargs = {
        "agentRuntimeArn": agent_runtime_arn,
        "runtimeSessionId": runtime_session_id,
        "contentType": "application/json",
        "accept": "application/json",
        "payload": json.dumps(request_payload, ensure_ascii=False, default=str).encode("utf-8"),
    }
    if qualifier.strip():
        kwargs["qualifier"] = qualifier.strip()

    resp = client.invoke_agent_runtime(**kwargs)
    text = _read_agentcore_response_text(resp)
    parsed = _extract_json_obj(text)
    if not isinstance(parsed, dict):
        parsed = {"executive_summary": text}

    report = _normalize_report_payload(
        parsed,
        company=company,
        year=year,
        user_query=user_query,
        mode_label="AgentCore Runtime",
    )

    status_code = resp.get("statusCode")
    runtime_sid = resp.get("runtimeSessionId", runtime_session_id)
    report["agent_steps"].append(f"🌐 AgentCore status: {status_code}")
    report["agent_steps"].append(f"🧵 Runtime session: {runtime_sid}")
    report["runtime_session_id"] = runtime_sid
    return report


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-icon">🤖</span>
                <div>
                    <p class="page-title">Risk Intelligence Agent</p>
                    <p class="page-subtitle">Ask questions in plain English — get a full prioritized risk report</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    index = load_index()
    if not index:
        st.markdown(
            """
            <div class="empty-state">
                <p class="empty-state-icon">📂</p>
                <p class="empty-state-title">No filings yet</p>
                <p class="empty-state-sub">Upload a 10-K filing first, then return here to run the agent.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Upload →", key="agent_empty_upload", type="primary"):
            st.session_state["current_page"] = "upload"
            st.rerun()
        return

    col_left, col_right = st.columns([1, 2], gap="large")
    if "agent_exec_runtime" not in st.session_state:
        st.session_state["agent_exec_runtime"] = False
    runtime_arn = _secret_get(
        "AGENTCORE_RUNTIME_ARN",
        _secret_get("AGENTCORE_ARN", ""),
    ).strip()
    runtime_qualifier = _secret_get(
        "AGENTCORE_QUALIFIER",
        _secret_get("AGENTCORE_RUNTIME_QUALIFIER", ""),
    ).strip()
    if "agent_runtime_session_id" not in st.session_state:
        st.session_state["agent_runtime_session_id"] = _ensure_runtime_session_id(str(uuid.uuid4()))
    else:
        st.session_state["agent_runtime_session_id"] = _ensure_runtime_session_id(
            st.session_state["agent_runtime_session_id"]
        )
    runtime_session_id = st.session_state["agent_runtime_session_id"]
    if st.session_state["agent_exec_runtime"] and not runtime_arn:
        st.session_state["agent_exec_runtime"] = False
        st.session_state["agentcore_not_configured_notice"] = True
    mode = "AgentCore Runtime" if st.session_state["agent_exec_runtime"] else "Local"

    # ════════════════════════════════════════════════════
    # LEFT — Configure + Suggested Queries
    # ════════════════════════════════════════════════════
    with col_left:
        # Configure block
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.6rem;">CONFIGURE</p>',
            unsafe_allow_html=True,
        )
        companies = sorted(set(r["company"] for r in index))
        company = st.selectbox("Company", companies, key="agent_company")
        co_recs = [r for r in index if r["company"] == company]
        years = sorted(set(r["year"] for r in co_recs), reverse=True)
        year = st.selectbox("Year", years, key="agent_year")
        mapped_ticker = get_company_ticker(company, "")
        if st.session_state.get("agent_stock_ticker_company") != company:
            st.session_state["agent_stock_ticker_company"] = company
            st.session_state["agent_stock_ticker"] = mapped_ticker
        ticker_col1, ticker_col2 = st.columns([4, 1])
        with ticker_col1:
            stock_ticker = st.text_input(
                "Stock Ticker (manual)",
                key="agent_stock_ticker",
                placeholder="e.g. AAPL",
                help="Auto-filled from saved mapping when available.",
            )
        with ticker_col2:
            st.markdown("<div style='height:1.8rem;'></div>", unsafe_allow_html=True)
            if st.button("Save", key="agent_save_ticker_map", use_container_width=True):
                if not stock_ticker.strip():
                    st.warning("Please enter a valid ticker before saving.")
                else:
                    upsert_company_ticker(company, stock_ticker)
                    st.success(f"Saved ticker mapping: {company} → {stock_ticker.strip().upper()}")

        use_compare = st.checkbox("Include YoY comparison", key="agent_use_compare")
        prior_year = None
        if use_compare:
            prior_opts = [y for y in years if y < year]
            if prior_opts:
                prior_year = st.selectbox("Compare against", prior_opts, key="agent_prior_year")
            else:
                st.caption("No prior year available.")
                use_compare = False

        # Suggested queries
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.6rem;">SUGGESTED QUERIES</p>',
            unsafe_allow_html=True,
        )
        for i, q in enumerate(SUGGESTED_QUERIES):
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["agent_query_text"] = q
                st.rerun()

    # ════════════════════════════════════════════════════
    # RIGHT — Query + Dashboard
    # ════════════════════════════════════════════════════
    with col_right:
        show_not_configured = st.session_state.pop("agentcore_not_configured_notice", False)
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.5rem;">YOUR QUERY</p>',
            unsafe_allow_html=True,
        )
        if show_not_configured:
            st.warning("AgentCore is not configured")
        user_query = st.text_area(
            "query",
            height=88,
            placeholder="Type a question or click a suggested query on the left…",
            key="agent_query_text",
            label_visibility="collapsed",
        )
        run_col, mode_col = st.columns([8, 2], gap="small")
        with run_col:
            run = st.button("🚀 Run Agent", key="btn_run_agent", type="primary", use_container_width=True)
        with mode_col:
            st.markdown(
                '<p style="font-size:0.62rem; color:#94a3b8; margin:0.15rem 0 0.1rem; text-align:right;">demo</p>',
                unsafe_allow_html=True,
            )
            def _on_agentcore_toggle():
                # Keep technical config hidden and fail-safe: auto-revert if backend ARN is missing.
                if st.session_state.get("agent_exec_runtime", False) and not runtime_arn:
                    st.session_state["agent_exec_runtime"] = False
                    st.session_state["agentcore_not_configured_notice"] = True

            st.toggle(
                "AgentCore",
                key="agent_exec_runtime",
                help="Run agent on AWS managed runtime",
                on_change=_on_agentcore_toggle,
            )
            if st.session_state.get("agent_exec_runtime", False):
                st.markdown(
                    '<p style="font-size:0.68rem; color:#22c55e; margin:0.1rem 0 0; text-align:right; font-weight:600;">'
                    '● AgentCore connected</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<p style="font-size:0.68rem; color:#94a3b8; margin:0.1rem 0 0; text-align:right; font-weight:500;">'
                    '● Local runtime</p>',
                    unsafe_allow_html=True,
                )

        if run:
            if not user_query.strip():
                st.error("Please enter a query or select one from the left.")
            else:
                rec = next((r for r in co_recs if r["year"] == year), None)
                if not rec:
                    st.error(f"No record found for {company} {year}.")
                else:
                    result = get_result(rec["record_id"])
                    if not result:
                        st.error("Could not load risk data.")
                    else:
                        risks = result.get("risks", [])
                        if not risks:
                            st.error("No risk data found in this record.")
                        else:
                            compare_data = None
                            if use_compare and prior_year:
                                prior_rec = next((r for r in co_recs if r["year"] == prior_year), None)
                                if prior_rec:
                                    prior_result = get_result(prior_rec["record_id"])
                                    if prior_result:
                                        compare_data = compare_risks(prior_result, result)
                            if mode == "AgentCore Runtime" and not runtime_arn.strip():
                                st.error("AgentCore is not configured")
                                st.session_state["agent_exec_runtime"] = False
                                return

                            safe_runtime_session_id = _ensure_runtime_session_id(runtime_session_id)
                            display_query = user_query.strip()
                            normalized_query = display_query
                            market_context_summary = ""
                            market_context_error = ""
                            market_metrics = {}
                            if stock_ticker.strip():
                                market_context_summary, market_context_error, market_metrics = _build_stock_context_summary(stock_ticker)
                                if market_context_error:
                                    st.warning(market_context_error)
                                elif market_context_summary:
                                    normalized_query = (
                                        f"{display_query}\n\n"
                                        "[Market Context]\n"
                                        f"{market_context_summary}\n"
                                        "Please use this as supplemental context for risk prioritization."
                                    )
                                    upsert_company_ticker(company, stock_ticker)

                            canonical_key = _build_agent_cache_key(
                                mode="canonical",
                                company=company,
                                year=year,
                                user_query=normalized_query,
                                risks=risks,
                                compare_data=compare_data,
                            )
                            canonical_report = _cache_get(canonical_key)

                            cache_key = _build_agent_cache_key(
                                mode=mode,
                                company=company,
                                year=year,
                                user_query=normalized_query,
                                risks=risks,
                                compare_data=compare_data,
                                runtime_arn=runtime_arn.strip(),
                                runtime_qualifier=runtime_qualifier.strip(),
                                runtime_session_id=safe_runtime_session_id,
                            )
                            # Always re-run AgentCore Runtime on user click; keep cache read for Local mode.
                            report = None if mode == "AgentCore Runtime" else _cache_get(cache_key)

                            if report is None:
                                with st.spinner(
                                    "🤖 Agent is analyzing risks…"
                                    if mode == "Local"
                                    else "🌐 AgentCore Runtime is analyzing risks…"
                                ):
                                    if mode == "Local":
                                        report = run_agent(
                                            user_query=normalized_query,
                                            company=company,
                                            year=year,
                                            risks=risks,
                                            compare_data=compare_data,
                                        )
                                        report = _normalize_report_payload(
                                            report,
                                            company=company,
                                            year=year,
                                            user_query=display_query,
                                            mode_label="Local",
                                        )
                                    else:
                                        try:
                                            report = _invoke_agentcore_runtime(
                                                agent_runtime_arn=runtime_arn.strip(),
                                                qualifier=runtime_qualifier,
                                                runtime_session_id=safe_runtime_session_id,
                                                company=company,
                                                year=year,
                                                user_query=normalized_query,
                                                risks=risks,
                                                compare_data=compare_data,
                                            )
                                            # Safety fallback: if remote runtime returns a known LLM-call failure shape,
                                            # immediately compute locally so UI is still actionable.
                                            summary_text = str(report.get("executive_summary", "") or "")
                                            if (
                                                report.get("overall_risk_rating") == "Unknown"
                                                and "Report generation encountered an error:" in summary_text
                                            ):
                                                report = run_agent(
                                                    user_query=normalized_query,
                                                    company=company,
                                                    year=year,
                                                    risks=risks,
                                                    compare_data=compare_data,
                                                )
                                                report = _normalize_report_payload(
                                                    report,
                                                    company=company,
                                                    year=year,
                                                    user_query=display_query,
                                                    mode_label="AgentCore Runtime (Local Fallback)",
                                                )
                                        except Exception as exc:
                                            st.error(f"AgentCore invocation failed: {type(exc).__name__}: {exc}")
                                            st.error(traceback.format_exc())
                                            return
                                if mode == "AgentCore Runtime":
                                    returned_sid = str(report.get("runtime_session_id", "") or "").strip()
                                    if returned_sid:
                                        st.session_state["agent_runtime_session_id"] = _ensure_runtime_session_id(returned_sid)
                                _cache_set(cache_key, report)
                                if canonical_report is None and not _is_error_report(report):
                                    _cache_set(canonical_key, report)
                            if canonical_report is not None and not _is_error_report(canonical_report):
                                report = _normalize_report_payload(
                                    canonical_report,
                                    company=company,
                                    year=year,
                                    user_query=display_query,
                                    mode_label=mode,
                                )
                            if market_context_summary:
                                report["market_context_summary"] = market_context_summary
                                report["stock_ticker"] = str(stock_ticker).strip().upper()
                            if market_metrics:
                                report["market_metrics"] = market_metrics
                                align = _alignment_sentence(
                                    report.get("overall_risk_rating", "Unknown"),
                                    market_metrics.get("return_90d_pct"),
                                    market_metrics.get("max_drawdown_pct"),
                                    market_metrics.get("excess_return_vs_spy_90d_pct"),
                                )
                                report["market_alignment"] = align
                                summary_text = str(report.get("executive_summary", "") or "").strip()
                                if align not in summary_text:
                                    report["executive_summary"] = (
                                        f"{summary_text}\n\n{align}" if summary_text else align
                                    )
                            st.session_state["agent_report"] = report
                            save_agent_report(
                                company=company,
                                year=year,
                                filing_type=rec.get("filing_type", "10-K"),
                                report_json=report,
                            )
                            st.rerun()

        # Output
        st.markdown("<br>", unsafe_allow_html=True)
        if "agent_report" not in st.session_state:
            st.markdown(
                """
                <div class="empty-state" style="height:340px; display:flex; flex-direction:column;
                     justify-content:center; align-items:center;">
                    <p class="empty-state-icon">📊</p>
                    <p class="empty-state-title">Your report will appear here</p>
                    <p class="empty-state-sub">Configure on the left, type a query, then hit Run Agent</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            _display_dashboard(st.session_state["agent_report"])


def _display_dashboard(report: dict):
    company = report.get("company", "")
    year = report.get("year", "")
    pm = report.get("priority_matrix", {})
    enriched_risks = report.get("enriched_risks", [])
    overall = report.get("overall_risk_rating", "—")
    rc = RATING_COLORS.get(overall, "#6b7280")
    themes = report.get("risk_themes", [])

    h_count = pm.get("high", {}).get("count", 0)
    m_count = pm.get("medium", {}).get("count", 0)
    l_count = pm.get("low", {}).get("count", 0)

    # ── Overview strip ────────────────────────────────────────────────────────
    themes_html = " ".join(
        f'<span style="background:#eef2ff; color:#3730a3; border:1px solid #c7d2fe;'
        f'padding:2px 8px; border-radius:20px; font-size:0.68rem; font-weight:500;">{t}</span>'
        for t in themes
    ) if themes else '<span style="color:#94a3b8; font-size:0.8rem;">—</span>'

    oc1, oc2, oc3 = st.columns(3)
    _card_style = (
        "display:flex; flex-direction:column; align-items:center; justify-content:center;"
        "min-height:130px; text-align:center;"
    )
    with oc1:
        st.markdown(
            f'<div class="metric-card" style="border-color:{rc}40; background:{rc}08; {_card_style}">'
            f'<p class="metric-label" style="color:{rc};">OVERALL RISK</p>'
            f'<p class="metric-value" style="color:{rc}; font-size:1.5rem;">{overall}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with oc2:
        st.markdown(
            f'<div class="metric-card" style="{_card_style}">'
            f'<p class="metric-label">PRIORITY BREAKDOWN</p>'
            f'<div style="display:flex; gap:1rem; justify-content:center; align-items:center; margin-top:0.5rem;">'
            f'<div style="text-align:center;">'
            f'<p style="font-size:1.4rem; font-weight:800; color:#ef4444; margin:0;">{h_count}</p>'
            f'<p style="font-size:0.68rem; color:#ef4444; font-weight:700; margin:0;">HIGH</p>'
            f'</div>'
            f'<div style="width:1px; height:2rem; background:#e5e7eb;"></div>'
            f'<div style="text-align:center;">'
            f'<p style="font-size:1.4rem; font-weight:800; color:#f59e0b; margin:0;">{m_count}</p>'
            f'<p style="font-size:0.68rem; color:#f59e0b; font-weight:700; margin:0;">MEDIUM</p>'
            f'</div>'
            f'<div style="width:1px; height:2rem; background:#e5e7eb;"></div>'
            f'<div style="text-align:center;">'
            f'<p style="font-size:1.4rem; font-weight:800; color:#22c55e; margin:0;">{l_count}</p>'
            f'<p style="font-size:0.68rem; color:#22c55e; font-weight:700; margin:0;">LOW</p>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with oc3:
        st.markdown(
            f'<div class="metric-card" style="{_card_style}">'
            f'<p class="metric-label">RISK THEMES</p>'
            f'<div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:0.5rem; justify-content:center;">{themes_html}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Detail tabs ───────────────────────────────────────────────────────────
    tab_risks, tab_summary, tab_findings, tab_recs, tab_full = st.tabs([
        f"🔴 Top Risks ({h_count} High)",
        "📋 Executive Summary",
        "🔍 Key Findings",
        "💡 Recommendations",
        f"⚠️ Full List ({h_count + m_count + l_count})",
    ])

    # Tab 1: Top Risks
    with tab_risks:
        high_top = pm.get("high", {}).get("top", [])
        if not high_top:
            st.info("No high-priority risks identified.")
        else:
            for r in high_top:
                score = r.get("score", 0)
                score_pct = min(int((score / 10) * 100), 100)
                st.markdown(
                    f'''
                    <div style="background:#fff; border:1px solid #fecaca;
                         border-left:4px solid #ef4444; border-radius:10px;
                         padding:0.9rem 1.1rem; margin-bottom:0.65rem;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem;">
                            <p style="margin:0; font-size:0.87rem; color:#111827; font-weight:600; line-height:1.4;">
                                {r["title"]}
                            </p>
                            <div style="text-align:right; flex-shrink:0;">
                                {_badge("High", "#ef4444")}
                                <p style="margin:0.2rem 0 0; font-size:0.72rem; color:#9ca3af;">score {score}</p>
                            </div>
                        </div>
                        <p style="margin:0.4rem 0 0.4rem; font-size:0.79rem; color:#6b7280;">
                            {r.get("reasoning", "")}
                        </p>
                        <div style="background:#fee2e2; border-radius:4px; height:4px;">
                            <div style="background:#ef4444; border-radius:4px; height:4px; width:{score_pct}%;"></div>
                        </div>
                        <p style="margin:0.2rem 0 0; font-size:0.7rem; color:#9ca3af;">
                            Category: {r.get("category", "")}
                        </p>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

    # Tab 2: Executive Summary
    with tab_summary:
        summary = report.get("executive_summary", "")
        if summary:
            st.markdown(
                f'<div style="background:#f8faff; border:1px solid #dbeafe; border-radius:12px;'
                f'padding:1.4rem 1.6rem; line-height:1.8; font-size:0.93rem; color:#1f2937;">'
                f'{summary}</div>',
                unsafe_allow_html=True,
            )
        query_text = report.get("user_query", "")
        if query_text:
            st.markdown(
                f'<p style="margin-top:0.8rem; font-size:0.78rem; color:#9ca3af;">'
                f'Query: "{query_text}"</p>',
                unsafe_allow_html=True,
            )
        ci = report.get("compare_insights", "")
        if ci:
            st.markdown("**📅 Year-over-Year Insights**")
            st.info(ci)

    # Tab 3: Key Findings
    with tab_findings:
        findings = report.get("key_findings", [])
        if not findings:
            st.info("No findings available.")
        else:
            for i, f in enumerate(findings, 1):
                st.markdown(
                    f'<div style="display:flex; gap:0.8rem; align-items:flex-start;'
                    f'padding:0.75rem 0; border-bottom:1px solid #f3f4f6;">'
                    f'<div style="background:#eff6ff; color:#1e40af; font-weight:700;'
                    f'font-size:0.8rem; padding:0.2rem 0.55rem; border-radius:8px;'
                    f'flex-shrink:0; min-width:1.6rem; text-align:center;">{i}</div>'
                    f'<p style="margin:0; font-size:0.88rem; color:#374151; line-height:1.5;">{f}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Tab 4: Recommendations
    with tab_recs:
        recs = report.get("recommendations", [])
        if not recs:
            st.info("No recommendations available.")
        else:
            rec_icons = ["🎯", "👁️", "📈"]
            for i, r in enumerate(recs, 1):
                icon = rec_icons[i - 1] if i <= len(rec_icons) else "•"
                st.markdown(
                    f'<div style="background:#f0fdf4; border:1px solid #bbf7d0;'
                    f'border-left:4px solid #22c55e; border-radius:10px;'
                    f'padding:0.9rem 1.1rem; margin-bottom:0.6rem;'
                    f'display:flex; gap:0.8rem; align-items:flex-start;">'
                    f'<span style="font-size:1.2rem; flex-shrink:0;">{icon}</span>'
                    f'<p style="margin:0; font-size:0.88rem; color:#374151; line-height:1.5;">{r}</p>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Tab 5: Full Prioritized List
    with tab_full:
        if not enriched_risks:
            st.info("No risk data available.")
        else:
            priority_filter = st.segmented_control(
                "Filter",
                ["All", "🔴 High", "🟡 Medium", "🟢 Low"],
                default="All",
                key="agent_priority_filter",
            )
            filter_map = {"All": "All", "🔴 High": "High", "🟡 Medium": "Medium", "🟢 Low": "Low"}
            selected = filter_map.get(priority_filter, "All")

            for cat_block in enriched_risks:
                cat = cat_block.get("category", "Unknown")
                subs = cat_block.get("sub_risks", [])
                if not subs:
                    continue
                filtered = subs if selected == "All" else [
                    s for s in subs if isinstance(s, dict) and s.get("priority") == selected
                ]
                if not filtered:
                    continue
                with st.expander(f"**{cat}** ({len(filtered)} risks)", expanded=False):
                    for s in filtered:
                        if not isinstance(s, dict):
                            continue
                        p = s.get("priority", "Medium")
                        color = PRIORITY_COLORS.get(p, "#6b7280")
                        score = s.get("score", 5.0)
                        st.markdown(
                            f'<div style="border-left:3px solid {color}; padding:0.4rem 0.8rem;'
                            f'margin-bottom:0.4rem; background:#fafafa; border-radius:0 6px 6px 0;">'
                            f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                            f'<span style="font-size:0.83rem; color:#111827;">{s.get("title","")}</span>'
                            f'<span style="white-space:nowrap; margin-left:0.5rem;">'
                            f'{_badge(p, color)}'
                            f'<span style="font-size:0.7rem; color:#9ca3af; margin-left:4px;">{score}</span>'
                            f'</span></div>'
                            f'<p style="margin:0.12rem 0 0; font-size:0.74rem; color:#9ca3af;">'
                            f'{s.get("reasoning","")}</p>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

    # ── Agent trace ───────────────────────────────────────────────────────────
    steps = report.get("agent_steps", [])
    if steps:
        with st.expander("🔎 Agent execution trace", expanded=False):
            for s in steps:
                st.caption(f"· {s}")

    # ── Download ──────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    dl_data = {k: v for k, v in report.items() if k != "enriched_risks"}
    dl_data["prioritized_risks"] = enriched_risks
    st.download_button(
        "📥 Download Full Agent Report (JSON)",
        data=json.dumps(dl_data, indent=2, ensure_ascii=False),
        file_name=f"{company}_{year}_agent_report.json".replace(" ", "_"),
        mime="application/json",
        key="dl_agent_report",
        use_container_width=True,
    )
