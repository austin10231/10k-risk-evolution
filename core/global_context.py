"""Global cross-page context helpers for strong sync interaction."""

from __future__ import annotations

from datetime import datetime
import html

import streamlit as st

_CTX_KEY = "global_context"
_DEFAULT_INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def _default_context() -> dict:
    return {
        "company": "",
        "year": None,
        "filing_type": "",
        "industry": "",
        "ticker": "",
        "prior_years": [],
        "source": "",
        "updated_at": "",
        "nonce": 0,
    }


def _norm_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _normalize(field: str, value):
    if field == "year":
        return _norm_int(value)
    if field == "prior_years":
        if not isinstance(value, (list, tuple, set)):
            return []
        out = []
        for v in value:
            iv = _norm_int(v)
            if iv is not None and iv not in out:
                out.append(iv)
        return sorted(out, reverse=True)
    if field == "ticker":
        return str(value or "").strip().upper()
    if field in {"company", "filing_type", "industry", "source"}:
        return str(value or "").strip()
    return value


def ensure_global_context() -> dict:
    if _CTX_KEY not in st.session_state or not isinstance(st.session_state[_CTX_KEY], dict):
        st.session_state[_CTX_KEY] = _default_context()
    ctx = st.session_state[_CTX_KEY]
    for key, default_value in _default_context().items():
        ctx.setdefault(key, default_value)
    return ctx


def get_global_context() -> dict:
    return ensure_global_context()


def update_global_context(source: str = "", **kwargs) -> bool:
    """Update global context and bump nonce when values change."""
    ctx = ensure_global_context()
    data_changed = False

    for field in ("company", "year", "filing_type", "industry", "ticker", "prior_years"):
        if field not in kwargs:
            continue
        raw = kwargs.get(field)
        norm = _normalize(field, raw)
        if field == "year" and norm is None:
            continue
        if field == "prior_years" and norm is None:
            norm = []
        if ctx.get(field) != norm:
            ctx[field] = norm
            data_changed = True

    src = _normalize("source", source)
    source_changed = bool(src and ctx.get("source") != src)
    if source_changed:
        ctx["source"] = src

    if data_changed:
        ctx["nonce"] = int(ctx.get("nonce", 0) or 0) + 1
        ctx["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        st.session_state[_CTX_KEY] = ctx
        return True

    if source_changed:
        st.session_state[_CTX_KEY] = ctx
    return False


def clear_global_context(source: str = "manual_reset") -> None:
    ctx = _default_context()
    ctx["source"] = source
    ctx["updated_at"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    prev = ensure_global_context()
    ctx["nonce"] = int(prev.get("nonce", 0) or 0) + 1
    st.session_state[_CTX_KEY] = ctx


def sync_widget_from_context(
    widget_key: str,
    field: str,
    *,
    options=None,
    allow_empty: bool = False,
) -> None:
    """
    Apply global context value to a widget key at most once per context nonce.
    Call this before widget creation.
    """
    ctx = ensure_global_context()
    nonce = int(ctx.get("nonce", 0) or 0)
    marker_key = f"_ctx_sync_nonce::{widget_key}"
    if st.session_state.get(marker_key) == nonce:
        return

    value = ctx.get(field)
    if options is not None:
        opts = list(options)
        if isinstance(value, list):
            value = [v for v in value if v in opts]
        elif value not in opts:
            st.session_state[marker_key] = nonce
            return

    if isinstance(value, list):
        if value:
            st.session_state[widget_key] = value
    elif isinstance(value, str):
        if value or allow_empty:
            st.session_state[widget_key] = value
    elif value is not None:
        st.session_state[widget_key] = value

    st.session_state[marker_key] = nonce


def render_current_config_box(
    *,
    key_prefix: str,
    year_options=None,
    industry_options=None,
) -> None:
    """
    Render editable global context box.
    Intended placement: right side of page header on config-heavy pages.
    """
    ctx = ensure_global_context()
    years = list(year_options or range(2025, 2009, -1))
    industries = list(industry_options or _DEFAULT_INDUSTRIES)

    cur_year = _norm_int(ctx.get("year"))
    if cur_year is not None and cur_year not in years:
        years = [cur_year] + years

    cur_industry = str(ctx.get("industry", "") or "").strip()
    if cur_industry and cur_industry not in industries:
        industries = [cur_industry] + industries

    if not years:
        years = [2025]
    if not industries:
        industries = list(_DEFAULT_INDUSTRIES)

    y_idx = years.index(cur_year) if cur_year in years else 0
    i_idx = industries.index(cur_industry) if cur_industry in industries else 0

    company_raw = str(ctx.get("company", "") or "").strip() or "—"
    year_raw = str(ctx.get("year", "") or "").strip() or "—"
    industry_raw = str(ctx.get("industry", "") or "").strip() or "—"
    ticker_raw = str(ctx.get("ticker", "") or "").strip().upper() or "—"
    company_val = company_raw
    industry_val = industry_raw
    year_val = year_raw
    ticker_val = ticker_raw

    st.markdown('<div style="height:0.28rem;"></div>', unsafe_allow_html=True)
    st.markdown(
        """
        <style>
        .ctx-strip {
            background:#ffffff;
            border:1px solid #e2e8f0;
            border-radius:12px;
            padding:0.28rem 0.42rem;
            display:flex;
            align-items:center;
            gap:0.28rem;
            flex-wrap:nowrap;
            overflow:visible;
            min-height:38px;
            width:100%;
            position:relative;
        }
        .ctx-label {
            font-size:0.70rem;
            font-weight:700;
            color:#0f172a;
            white-space:nowrap;
            margin-right:0.1rem;
            flex-shrink:0;
        }
        .ctx-chip {
            display:inline-flex;
            align-items:center;
            border-radius:999px;
            padding:0.08rem 0.40rem;
            font-size:0.62rem;
            font-weight:700;
            white-space:nowrap;
            flex-shrink:0;
            border:1px solid transparent;
        }
        .ctx-chip-indigo { background:#eef2ff; color:#3730a3; border-color:#c7d2fe; }
        .ctx-chip-blue   { background:#eff6ff; color:#1e40af; border-color:#bfdbfe; }
        .ctx-chip-green  { background:#f0fdf4; color:#166534; border-color:#bbf7d0; }
        .ctx-chip-gray   { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }
        .ctx-help-wrap {
            position:relative;
            display:inline-flex;
            align-items:center;
            flex-shrink:0;
        }
        .ctx-help {
            display:inline-flex;
            align-items:center;
            justify-content:center;
            width:20px;
            height:20px;
            border-radius:999px;
            border:1px solid #94a3b8;
            color:#64748b;
            font-size:0.75rem;
            font-weight:700;
            line-height:1;
            cursor:help;
            flex-shrink:0;
            background:#ffffff;
            margin-left:0.08rem;
        }
        .ctx-help-tip {
            display:none;
            position:absolute;
            right:-4px;
            top:132%;
            width:340px;
            background:#ffffff;
            color:#0f172a !important;
            border:1px solid #cbd5e1;
            border-radius:10px;
            padding:0.5rem 0.65rem;
            box-shadow:0 6px 20px rgba(15,23,42,0.15);
            font-size:0.84rem;
            font-weight:500;
            line-height:1.35;
            white-space:normal;
            z-index:99999;
            pointer-events:none;
        }
        .ctx-help-wrap:hover .ctx-help-tip,
        .ctx-help-wrap:focus-within .ctx-help-tip {
            display:block;
        }
        [data-testid="stPopover"] button[data-testid="stBaseButton-secondary"] {
            white-space:nowrap !important;
            min-width:92px !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    c_strip, c_edit = st.columns([8.85, 1.15], gap="small")
    with c_strip:
        st.markdown(
            (
                '<div class="ctx-strip">'
                '<span class="ctx-label">Current Configuration</span>'
                f'<span class="ctx-chip ctx-chip-indigo" title="Company: {html.escape(company_raw)}">Company: {html.escape(company_val)}</span>'
                f'<span class="ctx-chip ctx-chip-blue" title="Year: {html.escape(year_raw)}">Year: {html.escape(year_val)}</span>'
                f'<span class="ctx-chip ctx-chip-green" title="Ticker: {html.escape(ticker_raw)}">Ticker: {html.escape(ticker_val)}</span>'
                f'<span class="ctx-chip ctx-chip-gray" title="Industry: {html.escape(industry_raw)}">Industry: {html.escape(industry_val)}</span>'
                '<span class="ctx-help-wrap">'
                '<span class="ctx-help">?</span>'
                '<span class="ctx-help-tip">This configuration auto-applies to pages that require Company, Year, Industry, and Ticker inputs.</span>'
                '</span>'
                '</div>'
            ),
            unsafe_allow_html=True,
        )

    apply_clicked = False
    clear_clicked = False
    with c_edit:
        with st.popover(
            "Edit",
            use_container_width=True,
            help="Edit global Company / Year / Industry / Ticker used across Upload, Compare, Agent, and Tables.",
        ):
            company = st.text_input(
                "Company",
                value=str(ctx.get("company", "") or ""),
                key=f"{key_prefix}_company",
                placeholder="e.g. Apple",
            )
            y1, y2 = st.columns(2)
            with y1:
                year = st.selectbox("Year", years, index=y_idx, key=f"{key_prefix}_year")
            with y2:
                industry = st.selectbox(
                    "Industry",
                    industries,
                    index=i_idx,
                    key=f"{key_prefix}_industry",
                )
            ticker = st.text_input(
                "Ticker",
                value=str(ctx.get("ticker", "") or ""),
                key=f"{key_prefix}_ticker",
                placeholder="e.g. AAPL",
            )
            b1, b2 = st.columns(2, gap="small")
            with b1:
                apply_clicked = st.button(
                    "Apply",
                    key=f"{key_prefix}_apply",
                    type="primary",
                    use_container_width=True,
                )
            with b2:
                clear_clicked = st.button(
                    "Clear",
                    key=f"{key_prefix}_clear",
                    use_container_width=True,
                )

    if clear_clicked:
        clear_global_context(source=f"{key_prefix}_clear")
        st.rerun()
    if apply_clicked:
        update_global_context(
            source=f"{key_prefix}_apply",
            company=company,
            year=year,
            industry=industry,
            ticker=ticker,
        )
        st.rerun()
