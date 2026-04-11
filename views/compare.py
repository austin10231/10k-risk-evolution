"""Compare page — Year-over-Year and Cross-Company risk diff."""

import streamlit as st
import json
import re
from datetime import datetime, timedelta

import plotly.graph_objects as go
import yfinance as yf

from storage.store import (
    load_index,
    get_result,
    save_compare_result,
    load_agent_reports,
    get_company_ticker,
    upsert_company_ticker,
)
from core.comparator import compare_risks
from core.bedrock import analyze_changes
from core.global_context import sync_widget_from_context, get_global_context, render_current_config_box


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_stock_history(ticker: str, start_date: str, end_date: str):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return []
    hist = yf.Ticker(symbol).history(start=start_date, end=end_date, auto_adjust=False)
    if hist is None or hist.empty or "Close" not in hist.columns:
        return []
    df = hist.reset_index()
    if "Date" not in df.columns:
        return []
    rows = []
    for _, row in df.iterrows():
        close = row.get("Close")
        dt = row.get("Date")
        if close is None or dt is None:
            continue
        if close != close:  # NaN guard
            continue
        rows.append({
            "date": dt.strftime("%Y-%m-%d"),
            "close": float(close),
        })
    return rows


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_ticker_profile_name(ticker: str) -> str:
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return ""
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        return ""
    for k in ("longName", "shortName", "displayName"):
        v = str(info.get(k, "") or "").strip()
        if v:
            return v
    return ""


def _normalize_company_tokens(name: str):
    raw = re.sub(r"[^a-z0-9]+", " ", str(name or "").lower()).strip()
    stop = {
        "inc", "incorporated", "corp", "corporation", "co", "company", "plc",
        "ltd", "limited", "class", "common", "stock", "holdings", "group", "the",
    }
    return {tok for tok in raw.split() if len(tok) > 1 and tok not in stop}


def _ticker_matches_company(company: str, ticker: str):
    symbol = str(ticker or "").strip().upper()
    if not symbol:
        return False, "", "Ticker is empty."
    profile_name = _fetch_ticker_profile_name(symbol)
    if not profile_name:
        return False, "", f"Could not verify ticker `{symbol}` from market profile."
    company_tokens = _normalize_company_tokens(company)
    profile_tokens = _normalize_company_tokens(profile_name)
    if company_tokens and profile_tokens and company_tokens.intersection(profile_tokens):
        return True, profile_name, ""
    return False, profile_name, (
        f"Ticker `{symbol}` appears to map to `{profile_name}`, which does not match selected company `{company}`."
    )


def _agent_rating_lookup():
    out = {}
    for report in load_agent_reports():
        company = report.get("company")
        year = report.get("year")
        rating = report.get("overall_risk_rating")
        if company and year and rating:
            out[(str(company), int(year))] = str(rating)
    return out


def _closest_point_for_year(points, year):
    target = datetime(int(year), 1, 1)
    parsed = []
    for p in points:
        try:
            dt = datetime.fromisoformat(str(p.get("date", "")))
            parsed.append((dt, p))
        except Exception:
            continue
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])
    for dt, p in parsed:
        if dt >= target:
            return p
    return parsed[-1][1]


def _closest_point_on_or_after(points, target_dt: datetime):
    parsed = []
    for p in points:
        try:
            dt = datetime.fromisoformat(str(p.get("date", "")))
            parsed.append((dt, p))
        except Exception:
            continue
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])
    for dt, p in parsed:
        if dt >= target_dt:
            return dt, p
    return parsed[-1]


def _event_window_points(points, event_date: datetime, pre_days: int, post_days: int):
    out = []
    start = event_date - timedelta(days=pre_days)
    end = event_date + timedelta(days=post_days)
    for p in points:
        try:
            dt = datetime.fromisoformat(str(p.get("date", "")))
        except Exception:
            continue
        if start <= dt <= end:
            out.append((dt, p))
    out.sort(key=lambda x: x[0])
    return out


def _forward_return(points, event_date: datetime, days_forward: int = 20):
    parsed = []
    for p in points:
        try:
            dt = datetime.fromisoformat(str(p.get("date", "")))
            close = float(p.get("close", 0))
        except Exception:
            continue
        parsed.append((dt, close))
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[0])
    start_idx = None
    for i, (dt, _) in enumerate(parsed):
        if dt >= event_date:
            start_idx = i
            break
    if start_idx is None:
        return None
    end_idx = min(start_idx + days_forward, len(parsed) - 1)
    start_price = parsed[start_idx][1]
    end_price = parsed[end_idx][1]
    if start_price <= 0:
        return None
    return ((end_price - start_price) / start_price) * 100.0


def _render_stock_event_window_analysis(company: str, ticker: str, latest_year: int, prior_years: list[int]):
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-size:0.95rem; font-weight:700; color:#111827; margin:0 0 0.6rem;">'
        '📈 Risk Event Window Analysis (±60 days around Jan 1 filing-date proxy)</p>',
        unsafe_allow_html=True,
    )

    symbol = str(ticker or "").strip().upper()
    if not symbol:
        st.info("Enter a stock ticker above to view the stock trend and risk event markers.")
        return

    valid_years = sorted({int(y) for y in [latest_year, *prior_years] if str(y).isdigit()})
    if not valid_years:
        st.info("No years selected for stock linkage chart.")
        return

    start_dt = datetime(min(valid_years), 1, 1) - timedelta(days=80)
    end_dt = datetime(max(valid_years), 1, 1) + timedelta(days=80)
    start_date = start_dt.strftime("%Y-%m-%d")
    end_date = end_dt.strftime("%Y-%m-%d")
    points = _fetch_stock_history(symbol, start_date, end_date)
    if not points:
        st.warning(f"Could not load stock data for ticker `{symbol}`. Please verify the ticker and try again.")
        return

    fig = go.Figure()

    rating_map = _agent_rating_lookup()
    rating_rank = {"Low": 1, "Medium-Low": 2, "Medium": 3, "Medium-High": 4, "High": 5}
    marker_colors = {
        "High": "#ef4444",
        "Medium-High": "#f97316",
        "Medium": "#f59e0b",
        "Medium-Low": "#84cc16",
        "Low": "#22c55e",
    }

    seen_pairs = []
    upgrade_returns = []

    for yr in valid_years:
        event_date = datetime(int(yr), 1, 1)
        window = _event_window_points(points, event_date, pre_days=60, post_days=60)
        if not window:
            continue
        wx = [dt.strftime("%Y-%m-%d") for dt, _ in window]
        wy = [row["close"] for _, row in window]
        rating = rating_map.get((company, int(yr)), "No Agent report")
        color = marker_colors.get(rating, "#94a3b8")
        fig.add_trace(
            go.Scatter(
                x=wx,
                y=wy,
                mode="lines",
                name=f"{yr} window ({rating})",
                line=dict(color=color, width=2),
            )
        )
        event_point = _closest_point_on_or_after(points, event_date)
        if event_point:
            event_dt, event_row = event_point
            fig.add_trace(
                go.Scatter(
                    x=[event_dt.strftime("%Y-%m-%d")],
                    y=[event_row["close"]],
                    mode="markers+text",
                    text=[f"{yr} · {rating}"],
                    textposition="top center",
                    marker=dict(size=9, color=color, line=dict(width=1, color="#ffffff")),
                    showlegend=False,
                )
            )
            fig.add_vline(
                x=event_dt.strftime("%Y-%m-%d"),
                line_dash="dot",
                line_color=color,
                opacity=0.4,
            )

    latest_rating = rating_map.get((company, int(latest_year)))
    latest_rank = rating_rank.get(latest_rating, 0)
    latest_event = datetime(int(latest_year), 1, 1)
    latest_ret20 = _forward_return(points, latest_event, days_forward=20)
    for py in sorted({int(y) for y in prior_years if str(y).isdigit()}):
        pair = (py, int(latest_year))
        if pair in seen_pairs:
            continue
        seen_pairs.append(pair)
        prior_rank = rating_rank.get(rating_map.get((company, py)), 0)
        if latest_rank > prior_rank and latest_ret20 is not None:
            upgrade_returns.append({"pair": f"{py}→{latest_year}", "ret20": latest_ret20})

    fig.update_layout(
        margin=dict(l=20, r=20, t=24, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, -apple-system, sans-serif", color="#0f172a"),
        xaxis=dict(title="Date", gridcolor="#e2e8f0"),
        yaxis=dict(title="Close Price (USD)", gridcolor="#e2e8f0"),
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=""),
        height=360,
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"cmp_stock_event_window_{company}_{latest_year}_{'_'.join(str(y) for y in sorted(prior_years))}_{symbol}",
    )

    if upgrade_returns:
        avg_ret = sum(item["ret20"] for item in upgrade_returns) / len(upgrade_returns)
        st.metric("风险升级后20天平均涨跌幅", f"{avg_ret:+.2f}%")
        st.caption(
            "Upgrade pairs: " + ", ".join(item["pair"] for item in upgrade_returns) +
            " (post-event window: 20 trading days)"
        )
    else:
        st.info("当前对比未检测到风险评级升级，或缺少足够的事件后 20 天股价数据。")


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    header_left, header_right = st.columns([2.35, 2.65], gap="medium")
    with header_left:
        st.markdown(
            """
            <div class="page-header">
                <div class="page-header-left">
                    <span class="page-icon">⚖️</span>
                    <div>
                        <p class="page-title">Compare</p>
                        <p class="page-subtitle">Detect risk changes year-over-year or between companies</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_right:
        render_current_config_box(
            key_prefix="ctx_compare",
            year_options=list(range(2025, 2009, -1)),
        )

    index = load_index()
    if not index:
        st.markdown(
            """
            <div class="empty-state">
                <p class="empty-state-icon">📂</p>
                <p class="empty-state-title">No filings yet</p>
                <p class="empty-state-sub">Upload at least two filings to compare risk changes.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Upload →", key="cmp_empty_upload", type="primary"):
            st.session_state["current_page"] = "upload"
            st.rerun()
        return

    # ── Mode selector ─────────────────────────────────────────────────────────
    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.6rem;">COMPARISON MODE</p>',
        unsafe_allow_html=True,
    )
    mode_tab_yoy, mode_tab_cross = st.tabs(["📅  Year-over-Year", "🏢  Cross-Company"])

    with mode_tab_yoy:
        _render_yoy(index)

    with mode_tab_cross:
        _render_cross(index)


# ── Year-over-Year ─────────────────────────────────────────────────────────────
def _render_yoy(index):
    companies = sorted(set(r["company"] for r in index))
    sync_widget_from_context("cmp_co", "company", options=companies)

    col1, col2 = st.columns(2)
    with col1:
        company = st.selectbox("Company", companies, key="cmp_co")
    with col2:
        co_recs = [r for r in index if r["company"] == company]
        ftypes = sorted(set(r["filing_type"] for r in co_recs))
        sync_widget_from_context("cmp_ft", "filing_type", options=ftypes)
        ftype = st.selectbox("Filing Type", ftypes, key="cmp_ft")

    type_recs = [r for r in co_recs if r["filing_type"] == ftype]
    years = sorted(set(r["year"] for r in type_recs))

    if len(years) < 2:
        st.warning(f"Need at least 2 years for **{company}** / **{ftype}**.")
        return

    col3, col4 = st.columns(2)
    with col3:
        sync_widget_from_context("cmp_ly", "year", options=years[::-1])
        latest_year = st.selectbox("Latest Year", years[::-1], key="cmp_ly")
    with col4:
        prior_opts = [y for y in years if y < latest_year]
        if not prior_opts:
            st.warning("No prior year available.")
            return
        sync_widget_from_context("cmp_py", "prior_years", options=prior_opts[::-1])
        prior_years = st.multiselect(
            "Prior Year(s)", prior_opts[::-1],
            default=[prior_opts[-1]], key="cmp_py",
        )

    mapped_ticker = get_company_ticker(company, "")
    if st.session_state.get("cmp_stock_ticker_company") != company:
        st.session_state["cmp_stock_ticker_company"] = company
        ctx = get_global_context()
        ctx_ticker = str(ctx.get("ticker", "") or "").strip().upper()
        if str(ctx.get("company", "") or "").strip() == company and ctx_ticker:
            st.session_state["cmp_stock_ticker"] = ctx_ticker
        else:
            st.session_state["cmp_stock_ticker"] = mapped_ticker

    t1, t2 = st.columns([4, 1])
    with t1:
        ticker = st.text_input(
            "Stock Ticker (manual)",
            key="cmp_stock_ticker",
            placeholder="e.g. AAPL",
            help="Auto-filled from saved mapping when available.",
        )
    with t2:
        st.markdown("<div style='height:1.8rem;'></div>", unsafe_allow_html=True)
        if st.button("Save", key="cmp_save_ticker_map", use_container_width=True):
            if not ticker.strip():
                st.warning("请输入有效 ticker 后再保存。")
            else:
                ok, profile_name, err = _ticker_matches_company(company, ticker)
                if not ok:
                    st.error(err)
                else:
                    upsert_company_ticker(company, ticker)
                    st.success(
                        f"Saved ticker mapping: {company} → {ticker.strip().upper()} "
                        f"(verified as {profile_name})"
                    )

    if not prior_years:
        st.warning("Select at least one prior year.")
        return

    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("🚀 Run Compare", key="btn_run_yoy", type="primary")

    if not run:
        if "cmp_results" in st.session_state and st.session_state.get("cmp_last_mode") == "yoy":
            _display_compare_results(
                st.session_state["cmp_results"],
                st.session_state.get("cmp_last_label_a", company),
                st.session_state.get("cmp_last_label_b", ""),
                ftype, mode="yoy",
            )
            _render_stock_event_window_analysis(company, ticker, latest_year, prior_years)
        return

    def find_rec(yr):
        return next((r for r in type_recs if r["year"] == yr), None)

    latest_rec = find_rec(latest_year)
    latest_res = get_result(latest_rec["record_id"]) if latest_rec else None
    if latest_res is None:
        st.error(f"Cannot load {company} {latest_year}.")
        return

    all_comparisons = []
    for py in sorted(prior_years, reverse=True):
        prior_rec = find_rec(py)
        prior_res = get_result(prior_rec["record_id"]) if prior_rec else None
        if prior_res is None:
            st.error(f"Cannot load {company} {py}.")
            continue
        cmp = compare_risks(prior_res, latest_res)
        all_comparisons.append({
            "company": company,
            "filing_type": ftype,
            "prior_year": py,
            "latest_year": latest_year,
            "label_a": f"{company} {py}",
            "label_b": f"{company} {latest_year}",
            "new_risks": cmp["new_risks"],
            "removed_risks": cmp["removed_risks"],
        })

    st.session_state["cmp_results"] = all_comparisons
    st.session_state["cmp_last_mode"] = "yoy"
    st.session_state["cmp_last_label_a"] = company
    st.session_state["cmp_last_label_b"] = ""
    if ticker.strip():
        ok, _, err = _ticker_matches_company(company, ticker)
        if ok:
            upsert_company_ticker(company, ticker)
        else:
            st.warning(err)
    _display_compare_results(all_comparisons, company, "", ftype, mode="yoy")
    _render_stock_event_window_analysis(company, ticker, latest_year, prior_years)


# ── Cross-Company ──────────────────────────────────────────────────────────────
def _render_cross(index):
    companies = sorted(set(r["company"] for r in index))
    sync_widget_from_context("cmp_co_b", "company", options=companies)

    col_a_head, col_b_head = st.columns(2)
    with col_a_head:
        st.markdown(
            '<div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;'
            'padding:0.45rem 1rem; font-weight:600; color:#1e40af; font-size:0.85rem; margin-bottom:0.7rem;">Company A</div>',
            unsafe_allow_html=True,
        )
    with col_b_head:
        st.markdown(
            '<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px;'
            'padding:0.45rem 1rem; font-weight:600; color:#166534; font-size:0.85rem; margin-bottom:0.7rem;">Company B</div>',
            unsafe_allow_html=True,
        )

    col_a, col_b = st.columns(2)
    with col_a:
        co_a = st.selectbox("Company", companies, key="cmp_co_a")
        recs_a = [r for r in index if r["company"] == co_a]
        ftypes_a = sorted(set(r["filing_type"] for r in recs_a))
        ft_a = st.selectbox("Filing Type", ftypes_a, key="cmp_ft_a")
        years_a = sorted(set(r["year"] for r in recs_a if r["filing_type"] == ft_a), reverse=True)
        yr_a = st.selectbox("Year", years_a, key="cmp_yr_a")

    with col_b:
        co_b = st.selectbox("Company", companies, key="cmp_co_b")
        recs_b = [r for r in index if r["company"] == co_b]
        ftypes_b = sorted(set(r["filing_type"] for r in recs_b))
        sync_widget_from_context("cmp_ft_b", "filing_type", options=ftypes_b)
        ft_b = st.selectbox("Filing Type", ftypes_b, key="cmp_ft_b")
        years_b = sorted(set(r["year"] for r in recs_b if r["filing_type"] == ft_b), reverse=True)
        sync_widget_from_context("cmp_yr_b", "year", options=years_b)
        yr_b = st.selectbox("Year", years_b, key="cmp_yr_b")

    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("🚀 Run Compare", key="btn_run_cross", type="primary")

    if not run:
        if "cmp_results" in st.session_state and st.session_state.get("cmp_last_mode") == "cross":
            _display_compare_results(
                st.session_state["cmp_results"],
                st.session_state.get("cmp_last_label_a", ""),
                st.session_state.get("cmp_last_label_b", ""),
                "", mode="cross",
            )
        return

    rec_a = next((r for r in index if r["company"] == co_a and r["filing_type"] == ft_a and r["year"] == yr_a), None)
    rec_b = next((r for r in index if r["company"] == co_b and r["filing_type"] == ft_b and r["year"] == yr_b), None)

    if not rec_a or not rec_b:
        st.error("Could not find one or both selected records.")
        return

    res_a = get_result(rec_a["record_id"])
    res_b = get_result(rec_b["record_id"])
    if res_a is None or res_b is None:
        st.error("Could not load result JSON for one or both records.")
        return

    cmp = compare_risks(res_a, res_b)
    label_a = f"{co_a} {yr_a}"
    label_b = f"{co_b} {yr_b}"

    all_comparisons = [{
        "company": f"{co_a} vs {co_b}",
        "filing_type": f"{ft_a} / {ft_b}",
        "prior_year": yr_a,
        "latest_year": yr_b,
        "label_a": label_a,
        "label_b": label_b,
        "new_risks": cmp["new_risks"],
        "removed_risks": cmp["removed_risks"],
    }]

    st.session_state["cmp_results"] = all_comparisons
    st.session_state["cmp_last_mode"] = "cross"
    st.session_state["cmp_last_label_a"] = label_a
    st.session_state["cmp_last_label_b"] = label_b
    _display_compare_results(all_comparisons, label_a, label_b, "", mode="cross")


# ── Display results ────────────────────────────────────────────────────────────
def _display_compare_results(all_comparisons, label_a, label_b, ftype, mode="yoy"):
    if "cmp_ai_texts" not in st.session_state:
        st.session_state["cmp_ai_texts"] = {}

    for export in all_comparisons:
        la = export.get("label_a", label_a)
        lb = export.get("label_b", label_b)

        st.markdown('<hr style="border:none; border-top:1px solid #e5e7eb; margin:1.2rem 0;">', unsafe_allow_html=True)

        # Section title
        if mode == "yoy":
            title = f"{export['latest_year']} vs {export['prior_year']}"
            analysis_title = f"{export['company']} · {export['latest_year']} vs {export['prior_year']}"
        else:
            title = f"{lb}  vs  {la}"
            analysis_title = f"{lb} vs {la}"

        st.markdown(
            f'<p style="font-size:1rem; font-weight:700; color:#111827; margin:0 0 0.8rem;">{title}</p>',
            unsafe_allow_html=True,
        )

        # Metric cards
        mc1, mc2 = st.columns(2)
        with mc1:
            n_new = len(export["new_risks"])
            st.markdown(
                f'<div class="metric-card" style="border-color:#bbf7d0;">'
                f'<p class="metric-label">Only in {lb[:20]}</p>'
                f'<p class="metric-value" style="color:#16a34a;">{n_new} new</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with mc2:
            n_rem = len(export["removed_risks"])
            st.markdown(
                f'<div class="metric-card" style="border-color:#fecaca;">'
                f'<p class="metric-label">Only in {la[:20]}</p>'
                f'<p class="metric-value" style="color:#dc2626;">{n_rem} removed</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Risk lists
        col_new, col_rem = st.columns(2)

        with col_new:
            if export["new_risks"]:
                st.markdown(
                    f'<p style="font-size:0.82rem; font-weight:600; color:#16a34a; margin:0 0 0.5rem;">🟢 Risks unique to {lb}</p>',
                    unsafe_allow_html=True,
                )
                grouped_new = {}
                for r in export["new_risks"]:
                    cat = r.get("category", "Uncategorized")
                    grouped_new.setdefault(cat, []).append(r.get("title", "")[:150])
                for cat, titles in grouped_new.items():
                    with st.expander(f"{cat} ({len(titles)})", expanded=False):
                        for t in titles:
                            st.markdown(f"- {t}")
            else:
                st.markdown('<p style="font-size:0.82rem; color:#9ca3af;">No unique risks in newer filing.</p>', unsafe_allow_html=True)

        with col_rem:
            if export["removed_risks"]:
                st.markdown(
                    f'<p style="font-size:0.82rem; font-weight:600; color:#dc2626; margin:0 0 0.5rem;">🔴 Risks unique to {la}</p>',
                    unsafe_allow_html=True,
                )
                grouped_removed = {}
                for r in export["removed_risks"]:
                    cat = r.get("category", "Uncategorized")
                    grouped_removed.setdefault(cat, []).append(r.get("title", "")[:150])
                for cat, titles in grouped_removed.items():
                    with st.expander(f"{cat} ({len(titles)})", expanded=False):
                        for t in titles:
                            st.markdown(f"- {t}")
            else:
                st.markdown('<p style="font-size:0.82rem; color:#9ca3af;">No unique risks in older filing.</p>', unsafe_allow_html=True)

        if not export["new_risks"] and not export["removed_risks"]:
            st.success("No differing risks detected between the two selections.")

        # AI Change Analysis
        ai_key = f"{la}_vs_{lb}"
        if ai_key in st.session_state["cmp_ai_texts"]:
            st.markdown('<div class="section-header">🤖 AI Change Analysis</div>', unsafe_allow_html=True)
            st.info(st.session_state["cmp_ai_texts"][ai_key])
        else:
            if st.button("🤖 AI Change Analysis", key=f"ai_cmp_{ai_key}"):
                with st.spinner("Analyzing differences…"):
                    ai_text = analyze_changes(
                        analysis_title, lb, la,
                        export["new_risks"], export["removed_risks"],
                        mode=mode,
                    )
                st.session_state["cmp_ai_texts"][ai_key] = ai_text
                st.rerun()

        st.download_button(
            "📥 Download Compare JSON",
            data=json.dumps(export, indent=2, ensure_ascii=False),
            file_name=f"compare_{la}_vs_{lb}.json".replace(" ", "_"),
            mime="application/json",
            key=f"dl_cmp_{ai_key}",
        )

    # Save to S3
    if all_comparisons and mode == "yoy":
        combined = {
            "company": all_comparisons[0]["company"],
            "filing_type": ftype,
            "latest_year": all_comparisons[0]["latest_year"],
            "prior_years": [c["prior_year"] for c in all_comparisons],
            "comparisons": all_comparisons,
        }
        s3_key = save_compare_result(
            company=all_comparisons[0]["company"],
            filing_type=ftype,
            latest_year=all_comparisons[0]["latest_year"],
            prior_years=[c["prior_year"] for c in all_comparisons],
            compare_json=combined,
            mode="yoy",
        )
        st.divider()
        st.success(f"Compare result saved to S3: `{s3_key}`")

    elif all_comparisons and mode == "cross":
        export = all_comparisons[0]
        la = export.get("label_a", "")
        lb = export.get("label_b", "")
        safe_la = re.sub(r"[^\w]", "_", la).strip("_")
        safe_lb = re.sub(r"[^\w]", "_", lb).strip("_")
        s3_key = save_compare_result(
            company=f"{safe_la}_vs_{safe_lb}",
            filing_type="",
            latest_year=export["latest_year"],
            prior_years=[export["prior_year"]],
            compare_json=export,
            mode="cross",
        )
        st.divider()
        st.success(f"Compare result saved to S3: `{s3_key}`")
