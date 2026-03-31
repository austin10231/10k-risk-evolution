"""Stock page — searchable market board with risk overlays."""

from datetime import datetime, timedelta

import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from storage.store import load_agent_reports, load_company_ticker_map

RECOMMENDED = [
    ("AAPL", "Apple"),
    ("GOOGL", "Alphabet"),
    ("MSFT", "Microsoft"),
    ("AMZN", "Amazon"),
    ("NVDA", "NVIDIA"),
]

RISK_LEVEL_NUM = {
    "Low": 1,
    "Medium-Low": 2,
    "Medium": 3,
    "Medium-High": 4,
    "High": 5,
}

RISK_COLOR = {
    "High": "#ef4444",
    "Medium-High": "#f97316",
    "Medium": "#f59e0b",
    "Medium-Low": "#84cc16",
    "Low": "#22c55e",
}


def _to_float(v):
    try:
        x = float(v)
        if x != x:
            return None
        return x
    except Exception:
        return None


def _first_valid(values):
    for v in values:
        fv = _to_float(v)
        if fv is not None:
            return fv
    return None


def _fmt_price(v):
    return "—" if v is None else f"${v:,.2f}"


def _fmt_pct(v):
    if v is None:
        return "—"
    arrow = "▲" if v >= 0 else "▼"
    return f"{arrow} {v:+.2f}%"


def _fmt_market_cap(v):
    fv = _to_float(v)
    if fv is None:
        return "—"
    abs_v = abs(fv)
    if abs_v >= 1_000_000_000_000:
        return f"${fv / 1_000_000_000_000:.2f}T"
    if abs_v >= 1_000_000_000:
        return f"${fv / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"${fv / 1_000_000:.2f}M"
    return f"${fv:,.0f}"


def _fmt_dividend_yield(v):
    fv = _to_float(v)
    if fv is None:
        return "—"
    pct = fv * 100.0 if abs(fv) <= 1 else fv
    return f"{pct:.2f}%"


def _parse_date(s):
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def _search_quotes(query: str):
    q = str(query or "").strip()
    if not q:
        return {"error": "", "results": []}
    try:
        search = yf.Search(q, max_results=12)
        raw = getattr(search, "quotes", []) or []
    except Exception as exc:
        return {"error": f"Search failed: {exc}", "results": []}

    seen = set()
    results = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        quote_type = str(item.get("quoteType", "") or "").upper()
        if quote_type and quote_type not in {"EQUITY", "ETF"}:
            continue
        name = str(item.get("shortname") or item.get("longname") or symbol).strip()
        exchange = str(item.get("exchange") or item.get("exchDisp") or "").strip()
        seen.add(symbol)
        results.append({"symbol": symbol, "name": name, "exchange": exchange})
    return {"error": "", "results": results}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_stock_bundle(symbol: str):
    sym = str(symbol or "").strip().upper()
    if not sym:
        return {"error": "Ticker is empty.", "symbol": sym}

    try:
        tk = yf.Ticker(sym)
        hist = tk.history(period="1y", interval="1d", auto_adjust=False)
    except Exception as exc:
        return {"error": f"Failed to fetch market data: {exc}", "symbol": sym}

    if hist is None or hist.empty or "Close" not in hist.columns:
        return {"error": "No market data returned for this ticker.", "symbol": sym}

    df = hist.reset_index()
    date_col = "Date" if "Date" in df.columns else None
    if date_col is None:
        return {"error": "Market data missing date field.", "symbol": sym}

    history = []
    for _, row in df.iterrows():
        dt = row.get(date_col)
        close = _to_float(row.get("Close"))
        vol = _to_float(row.get("Volume"))
        if dt is None or close is None:
            continue
        if dt.weekday() >= 5:
            continue
        history.append(
            {
                "date": dt.strftime("%Y-%m-%d"),
                "close": close,
                "volume": 0.0 if vol is None else vol,
            }
        )

    if len(history) < 2:
        return {"error": "Not enough history points for this ticker.", "symbol": sym}

    info = {}
    fast = {}
    try:
        info = tk.info or {}
    except Exception:
        info = {}
    try:
        fast = dict(getattr(tk, "fast_info", {}) or {})
    except Exception:
        fast = {}

    latest_close = history[-1]["close"]
    prev_close = history[-2]["close"]
    day_change = latest_close - prev_close
    day_change_pct = 0.0 if prev_close == 0 else (day_change / prev_close) * 100.0

    current_price = _first_valid(
        [
            info.get("currentPrice"),
            fast.get("lastPrice"),
            fast.get("last_price"),
            latest_close,
        ]
    )
    market_cap = _first_valid([info.get("marketCap"), fast.get("market_cap")])
    pe_ratio = _first_valid(
        [info.get("trailingPE"), info.get("forwardPE"), fast.get("trailing_pe")]
    )
    high_52 = _first_valid(
        [
            info.get("fiftyTwoWeekHigh"),
            fast.get("year_high"),
            max(h["close"] for h in history),
        ]
    )
    low_52 = _first_valid(
        [
            info.get("fiftyTwoWeekLow"),
            fast.get("year_low"),
            min(h["close"] for h in history),
        ]
    )
    dividend_yield = _first_valid(
        [info.get("dividendYield"), info.get("trailingAnnualDividendYield")]
    )
    analyst_target_price = _first_valid([info.get("targetMeanPrice")])

    return {
        "error": "",
        "symbol": sym,
        "name": str(info.get("shortName") or info.get("longName") or sym),
        "history": history,
        "current_price": current_price,
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "high_52": high_52,
        "low_52": low_52,
        "dividend_yield": dividend_yield,
        "analyst_target_price": analyst_target_price,
    }


@st.cache_data(ttl=300, show_spinner=False)
def _load_agent_reports_cached():
    return load_agent_reports()


@st.cache_data(ttl=300, show_spinner=False)
def _load_company_ticker_map_cached():
    return load_company_ticker_map()


def _slice_history(history, range_key: str):
    if not history:
        return []
    days_map = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}
    days = days_map.get(range_key, 365)
    cutoff = datetime.utcnow() - timedelta(days=days)
    sliced = []
    for h in history:
        dt = _parse_date(h.get("date"))
        if dt is None:
            continue
        if dt.weekday() >= 5:
            continue
        if dt >= cutoff:
            sliced.append(h)
    if len(sliced) < 2:
        return [
            h for h in history
            if (_parse_date(h.get("date")) is not None and _parse_date(h.get("date")).weekday() < 5)
        ]
    return sliced


def _xaxis_config(range_key: str):
    cfg = dict(
        title="Date",
        gridcolor="#e2e8f0",
        type="date",
        rangebreaks=[dict(bounds=["sat", "mon"])],
    )
    if range_key == "1W":
        cfg.update(dtick="D1", tickformat="%b %d")
    elif range_key in {"1M", "3M"}:
        cfg.update(tickformat="%b %d")
    else:
        cfg.update(tickformat="%b %Y")
    return cfg


def _company_for_ticker(symbol: str, ticker_map: dict):
    sym = str(symbol or "").strip().upper()
    for company, ticker in ticker_map.items():
        if str(ticker or "").strip().upper() == sym:
            return company
    return ""


def _norm_name(text: str):
    raw = str(text or "").strip().lower()
    out = []
    for ch in raw:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
    return " ".join("".join(out).split())


def _resolve_company_for_risk(symbol: str, selected_name: str, ticker_map: dict, latest_map: dict):
    by_ticker = _company_for_ticker(symbol, ticker_map)
    if by_ticker:
        return by_ticker

    target = _norm_name(selected_name)
    if not target:
        return ""

    keys = list(latest_map.keys())
    exact = [k for k in keys if _norm_name(k) == target]
    if exact:
        return exact[0]

    loose = [k for k in keys if target in _norm_name(k) or _norm_name(k) in target]
    if loose:
        return loose[0]
    return ""


def _latest_ratings(agent_reports):
    out = {}
    for report in agent_reports:
        company = str(report.get("company", "") or "").strip()
        rating = str(report.get("overall_risk_rating", "") or "").strip()
        year = report.get("year")
        if not company or rating not in RISK_LEVEL_NUM:
            continue
        try:
            y = int(year)
        except Exception:
            continue
        prev = out.get(company)
        if not prev or y > prev["year"]:
            out[company] = {"year": y, "rating": rating}
    return out


def _rating_bucket(rating: str):
    r = str(rating or "").strip()
    if r == "High":
        return "High", "#ef4444"
    if r in {"Medium-High", "Medium"}:
        return "Medium", "#f59e0b"
    if r in {"Medium-Low", "Low"}:
        return "Low", "#22c55e"
    return "", "#94a3b8"


def _risk_change_markers(company: str, agent_reports, history):
    if not company or not history:
        return []
    latest_by_year = {}
    for report in agent_reports:
        if str(report.get("company", "") or "").strip() != company:
            continue
        rating = str(report.get("overall_risk_rating", "") or "").strip()
        year = report.get("year")
        if rating not in RISK_LEVEL_NUM:
            continue
        try:
            y = int(year)
        except Exception:
            continue
        latest_by_year[y] = rating

    if not latest_by_year:
        return []

    ordered = sorted(latest_by_year.items(), key=lambda x: x[0])
    changes = []
    prev = None
    for y, rating in ordered:
        if prev is None or rating != prev:
            changes.append((y, rating))
        prev = rating

    parsed = []
    for row in history:
        dt = _parse_date(row.get("date"))
        if dt is None:
            continue
        parsed.append((dt, row))
    parsed.sort(key=lambda x: x[0])
    if not parsed:
        return []

    markers = []
    for y, rating in changes:
        target = datetime(y, 1, 1)
        hit = None
        for dt, row in parsed:
            if dt >= target:
                hit = row
                break
        if hit is None:
            hit = parsed[-1][1]
        markers.append({"year": y, "rating": rating, "date": hit["date"], "close": hit["close"]})
    return markers


def render():
    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-icon">💹</span>
                <div>
                    <p class="page-title">Stock</p>
                    <p class="page-subtitle">Search market data and overlay your system risk signals</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_refresh_col, _ = st.columns([1, 9])
    with top_refresh_col:
        if st.button("Refresh", key="stock_refresh_data", help="Reload latest quote + risk cache"):
            _fetch_stock_bundle.clear()
            _search_quotes.clear()
            _load_agent_reports_cached.clear()
            _load_company_ticker_map_cached.clear()
            st.session_state.pop("stock_bundle_symbol", None)
            st.session_state.pop("stock_bundle_data", None)
            st.rerun()

    if "stock_search_cache" not in st.session_state:
        st.session_state["stock_search_cache"] = {}

    search_query = st.text_input(
        "Search company or ticker",
        key="stock_query",
        placeholder="e.g. Apple, AAPL, Microsoft, NVDA",
    ).strip()

    selected_symbol = ""
    selected_name = ""

    if search_query:
        cache_key = search_query.lower()
        if cache_key not in st.session_state["stock_search_cache"]:
            st.session_state["stock_search_cache"][cache_key] = _search_quotes(search_query)
        payload = st.session_state["stock_search_cache"].get(cache_key, {"error": "", "results": []})
        if payload.get("error"):
            st.warning(payload["error"])
        matches = payload.get("results", [])
        if matches:
            options = [
                f"{m['name']} · {m['symbol']}" + (f" ({m['exchange']})" if m.get("exchange") else "")
                for m in matches
            ]
            selected_option = st.selectbox(
                "Matching companies",
                options,
                key="stock_search_match_pick",
                help="Results from yfinance.Search().quotes",
            )
            selected_idx = options.index(selected_option)
            selected_symbol = matches[selected_idx]["symbol"]
            selected_name = matches[selected_idx]["name"]
        else:
            st.info("No matching companies found. Try another keyword or ticker.")
    else:
        st.caption("Popular: AAPL, GOOGL, MSFT, AMZN, NVDA")
        default_pick = st.selectbox(
            "Recommended tickers",
            [f"{sym} · {name}" for sym, name in RECOMMENDED],
            key="stock_default_pick",
        )
        selected_symbol, selected_name = default_pick.split(" · ", 1)

    if not selected_symbol:
        return

    st.session_state["stock_selected_symbol"] = selected_symbol
    st.session_state["stock_selected_name"] = selected_name

    bundle = None
    if st.session_state.get("stock_bundle_symbol") == selected_symbol:
        bundle = st.session_state.get("stock_bundle_data")

    if not bundle:
        with st.spinner(f"Loading market data for {selected_symbol}..."):
            bundle = _fetch_stock_bundle(selected_symbol)
        st.session_state["stock_bundle_symbol"] = selected_symbol
        st.session_state["stock_bundle_data"] = bundle

    if bundle.get("error"):
        st.error(bundle["error"])
        return

    symbol = bundle["symbol"]
    display_name = bundle.get("name") or selected_name or symbol

    ticker_map = _load_company_ticker_map_cached()
    agent_reports = _load_agent_reports_cached()
    latest_map = _latest_ratings(agent_reports)
    mapped_company = _resolve_company_for_risk(symbol, display_name, ticker_map, latest_map)
    mapped_rating = latest_map.get(mapped_company, {}) if mapped_company else {}
    rating_text = str(mapped_rating.get("rating", "") or "")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(
        f'<div class="metric-card"><p class="metric-label">CURRENT PRICE</p>'
        f'<p class="metric-value">{_fmt_price(bundle.get("current_price"))}</p></div>',
        unsafe_allow_html=True,
    )
    today_pct = _to_float(bundle.get("day_change_pct"))
    if today_pct is None:
        today_color = "#94a3b8"
    elif today_pct >= 0:
        today_color = "#16a34a"
    else:
        today_color = "#dc2626"
    c2.markdown(
        f'<div class="metric-card"><p class="metric-label">TODAY</p>'
        f'<p class="metric-value" style="font-size:1.05rem; color:{today_color};">'
        f'{_fmt_pct(bundle.get("day_change_pct"))}</p></div>',
        unsafe_allow_html=True,
    )
    c3.markdown(
        f'<div class="metric-card"><p class="metric-label">MARKET CAP</p>'
        f'<p class="metric-value" style="font-size:1.05rem;">{_fmt_market_cap(bundle.get("market_cap"))}</p></div>',
        unsafe_allow_html=True,
    )
    pe_val = bundle.get("pe_ratio")
    c4.markdown(
        f'<div class="metric-card"><p class="metric-label">PE RATIO</p>'
        f'<p class="metric-value" style="font-size:1.05rem;">{"—" if pe_val is None else f"{pe_val:.2f}"}</p></div>',
        unsafe_allow_html=True,
    )
    c5.markdown(
        f'<div class="metric-card"><p class="metric-label">52W HIGH / LOW</p>'
        f'<p class="metric-value" style="font-size:0.95rem;">'
        f'{_fmt_price(bundle.get("high_52"))} / {_fmt_price(bundle.get("low_52"))}</p></div>',
        unsafe_allow_html=True,
    )

    if rating_text:
        bucket_label, bucket_color = _rating_bucket(rating_text)
        c6.markdown(
            f'<div class="metric-card"><p class="metric-label">RISK LEVEL</p>'
            f'<p class="metric-value" style="font-size:1.05rem; color:{bucket_color};">{bucket_label}</p>'
            f'<p style="margin:0; font-size:0.73rem; color:#64748b;">{rating_text} · {mapped_company}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        c6.markdown(
            '<div class="metric-card"><p class="metric-label">RISK LEVEL</p>'
            '<p class="metric-value" style="font-size:0.95rem; color:#94a3b8;">No data</p></div>',
            unsafe_allow_html=True,
        )

    optional_metrics = []
    if bundle.get("dividend_yield") is not None:
        optional_metrics.append(("DIVIDEND YIELD", _fmt_dividend_yield(bundle.get("dividend_yield"))))
    if bundle.get("analyst_target_price") is not None:
        optional_metrics.append(("ANALYST TARGET PRICE", _fmt_price(bundle.get("analyst_target_price"))))
    if optional_metrics:
        st.markdown("<br>", unsafe_allow_html=True)
        extra_cols = st.columns(len(optional_metrics))
        for idx, (label, value) in enumerate(optional_metrics):
            extra_cols[idx].markdown(
                f'<div class="metric-card"><p class="metric-label">{label}</p>'
                f'<p class="metric-value" style="font-size:1.0rem;">{value}</p></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    range_key = st.radio(
        "Time Range",
        ["1W", "1M", "3M", "6M", "1Y"],
        horizontal=True,
        key="stock_range_key",
    )

    history = _slice_history(bundle.get("history", []), range_key)
    if len(history) < 2:
        st.warning("Not enough data points in the selected range.")
        return

    x_vals = [h["date"] for h in history]
    close_vals = [h["close"] for h in history]
    vol_vals = [h.get("volume", 0) for h in history]

    price_fig = go.Figure(
        data=[
            go.Scatter(
                x=x_vals,
                y=close_vals,
                mode="lines",
                line=dict(color="#2563eb", width=2.2),
                name=f"{symbol} Close",
            )
        ]
    )
    price_fig.update_layout(
        margin=dict(l=20, r=20, t=30, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, -apple-system, sans-serif", color="#0f172a"),
        xaxis=_xaxis_config(range_key),
        yaxis=dict(title="Close Price (USD)", gridcolor="#e2e8f0"),
        hovermode="x unified",
        height=430,
        title=dict(text=f"{display_name} ({symbol}) — Closing Price", font=dict(size=14)),
    )

    all_markers = _risk_change_markers(mapped_company, agent_reports, bundle.get("history", [])) if mapped_company else []
    visible_dates = {str(h.get("date", "")) for h in history}
    markers = [m for m in all_markers if str(m.get("date", "")) in visible_dates]
    if markers:
        marker_x = [m["date"] for m in markers]
        marker_y = [m["close"] for m in markers]
        marker_colors = [RISK_COLOR.get(m["rating"], "#94a3b8") for m in markers]
        marker_text = [f"{m['year']} · {m['rating']}" for m in markers]
        price_fig.add_trace(
            go.Scatter(
                x=marker_x,
                y=marker_y,
                mode="markers",
                marker=dict(size=10, color=marker_colors, line=dict(width=1, color="#ffffff")),
                text=marker_text,
                name="Risk rating change",
                hovertemplate="<b>Risk update</b><br>%{text}<br>Close: %{y:.2f}<extra></extra>",
            )
        )

    st.plotly_chart(price_fig, use_container_width=True, key=f"stock_price_{symbol}_{range_key}")

    if not all_markers:
        st.info("No risk analysis available — go to Analyze to add")
    elif not markers:
        st.caption("Risk analysis exists, but no risk-change marker falls inside the selected date range.")
    else:
        st.caption("Risk overlays from Agent reports: " + " | ".join([f"{m['year']}: {m['rating']}" for m in markers]))

    volume_fig = go.Figure(
        data=[
            go.Bar(
                x=x_vals,
                y=vol_vals,
                marker=dict(color="#93c5fd"),
                name="Volume",
            )
        ]
    )
    volume_fig.update_layout(
        margin=dict(l=20, r=20, t=46, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#ffffff",
        font=dict(family="Inter, -apple-system, sans-serif", color="#0f172a"),
        xaxis=_xaxis_config(range_key),
        yaxis=dict(title="Volume", gridcolor="#e2e8f0"),
        hovermode="x unified",
        height=270,
        title=dict(
            text="Trading Volume",
            font=dict(size=13),
            x=0.0,
            xanchor="left",
            y=0.98,
            yanchor="top",
            pad=dict(b=14),
        ),
    )
    st.plotly_chart(volume_fig, use_container_width=True, key=f"stock_volume_{symbol}_{range_key}")
