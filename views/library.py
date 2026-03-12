"""Library page — card grid for browsing uploaded filings."""

import streamlit as st
import json

from storage.store import load_index, get_result, filter_records, delete_record, _s3_write, RESULTS_PREFIX
from core.bedrock import classify_risks, generate_summary
from components.filters import library_filters

# Industry → accent color map
INDUSTRY_COLORS = {
    "Technology":             "#2563eb",
    "Healthcare":             "#059669",
    "Financials":             "#7c3aed",
    "Energy":                 "#d97706",
    "Consumer Discretionary": "#db2777",
    "Consumer Staples":       "#0891b2",
    "Industrials":            "#65a30d",
    "Materials":              "#b45309",
    "Utilities":              "#0284c7",
    "Real Estate":            "#6d28d9",
    "Telecom":                "#0f766e",
    "Other":                  "#6b7280",
}


def _count_sub_risks(risks):
    return sum(len(c.get("sub_risks", [])) for c in risks)


def _run_ai(result, record_id):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    with st.spinner("Classifying risks with AI…"):
        classified = classify_risks(risks)
    result["risks"] = classified
    with st.spinner("Generating executive summary…"):
        summary = generate_summary(ov.get("company", ""), ov.get("year", 0), classified)
    result["ai_summary"] = summary
    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    st.session_state["lib_selected_result"] = result
    st.rerun()


def _show_result(result, record_id):
    """Render the analysis result panel."""
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")

    # Header strip
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", ov.get("company", "—"))
    c2.metric("Year", ov.get("year", "—"))
    c3.metric("Risk Categories", len(risks))
    c4.metric("Risk Items", _count_sub_risks(risks))

    # AI Summary
    if ai_summary:
        st.markdown('<div class="section-header">🤖 AI Executive Summary</div>', unsafe_allow_html=True)
        st.info(ai_summary)
    else:
        if st.button("🤖 Run AI Summarize", key=f"ai_lib_{record_id}"):
            _run_ai(result, record_id)

    # Company overview
    bg = ov.get("background", "")
    if bg:
        st.markdown('<div class="section-header">🏢 Business Overview</div>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:0.88rem; color:#374151; line-height:1.6;">{bg}</p>',
                    unsafe_allow_html=True)

    # Risk categories
    st.markdown(
        f'<div class="section-header">⚠️ Risk Categories ({len(risks)})</div>',
        unsafe_allow_html=True,
    )
    for cat_block in risks:
        cat_name = cat_block.get("category", "Unknown")
        subs = cat_block.get("sub_risks", [])
        if subs and isinstance(subs[0], dict):
            with st.expander(f"**{cat_name}** ({len(subs)} risks)", expanded=False):
                for s in subs:
                    labels = s.get("labels", [])
                    label_str = " · ".join(f"`{l}`" for l in labels) if labels else ""
                    st.markdown(f"- {s.get('title','')[:150]}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
        else:
            st.markdown(f"- **{cat_name}** — {len(subs)} items")

    # Download
    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"{ov.get('company','export')}_{ov.get('year','')}.json",
        mime="application/json",
        key=f"dl_lib_{record_id}",
        use_container_width=True,
    )


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    col_h, col_btn = st.columns([3, 1])
    with col_h:
        st.markdown(
            """
            <div class="page-header" style="border-bottom:none; margin-bottom:0.5rem; padding-bottom:0;">
                <div class="page-header-left">
                    <span class="page-icon">📚</span>
                    <div>
                        <p class="page-title">Library</p>
                        <p class="page-subtitle">Browse and manage your uploaded 10-K filings</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("➕ New Filing", key="lib_go_upload", type="primary"):
            st.session_state["current_page"] = "upload"
            st.rerun()

    st.markdown('<hr style="border:none; border-top:1px solid #e2e8f0; margin:0.5rem 0 1.2rem;">', unsafe_allow_html=True)

    # ── Load data ─────────────────────────────────────────────────────────────
    index = load_index()
    if not index:
        st.markdown(
            """
            <div class="empty-state">
                <p class="empty-state-icon">📂</p>
                <p class="empty-state-title">No filings yet</p>
                <p class="empty-state-sub">Upload your first 10-K filing to get started.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Upload →", key="lib_empty_upload", type="primary"):
            st.session_state["current_page"] = "upload"
            st.rerun()
        return

    # ── Filters ───────────────────────────────────────────────────────────────
    with st.container():
        flt = library_filters(index, key_prefix="lib")

    filtered = filter_records(
        industry=flt["industry"],
        company=flt["company"],
        year=flt["year"],
        filing_type=flt["filing_type"],
        fmt=flt["format"],
    )

    # Count label
    st.markdown(
        f'<p style="font-size:0.75rem; color:#94a3b8; margin:0.5rem 0 1rem; font-weight:400;">'
        f'Showing <strong style="color:#334155; font-weight:600;">{len(filtered)}</strong>'
        f' of {len(index)} records</p>',
        unsafe_allow_html=True,
    )

    if not filtered:
        st.warning("No records match the current filters.")
        return

    # ── Card grid (3 columns) ──────────────────────────────────────────────────
    cols = st.columns(3, gap="medium")
    for i, rec in enumerate(filtered):
        with cols[i % 3]:
            company = rec["company"]
            year = rec["year"]
            industry = rec.get("industry", "Other")
            ftype = rec.get("filing_type", "10-K")
            fmt = rec.get("file_ext", "html").upper()
            rid = rec["record_id"]
            color = INDUSTRY_COLORS.get(industry, "#6b7280")
            is_selected = st.session_state.get("lib_selected_rid") == rid

            border_style = "border:1.5px solid #6366f1; background:#fafafe;" if is_selected else "border:1px solid #e2e8f0;"
            st.markdown(
                f"""
                <div style="background:#ffffff; {border_style} border-radius:10px;
                     padding:1rem 1.1rem; margin-bottom:0.4rem;
                     box-shadow:0 1px 2px rgba(15,23,42,0.04);">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:0.6rem;">
                        <div style="background:{color}15; color:{color}; font-size:0.82rem;
                             font-weight:800; padding:0.28rem 0.55rem; border-radius:7px;
                             letter-spacing:0.04em; border:1px solid {color}20;">
                            {company[:4].upper()}
                        </div>
                        <span style="background:#f1f5f9; color:#64748b; border:1px solid #e2e8f0;
                              font-size:0.67rem; font-weight:600; padding:2px 7px; border-radius:20px;">
                            {fmt}
                        </span>
                    </div>
                    <p style="font-size:0.87rem; font-weight:700; color:#0f172a; margin:0 0 0.22rem;
                       letter-spacing:-0.01em;">{company}</p>
                    <p style="font-size:0.74rem; color:#64748b; margin:0;">
                        {industry} &nbsp;·&nbsp; {ftype} &nbsp;·&nbsp; {year}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                load_type = "primary" if is_selected else "secondary"
                if st.button("Load" if not is_selected else "✓ Loaded",
                             key=f"load_{rid}", use_container_width=True, type=load_type):
                    st.session_state["lib_selected_rid"] = rid
                    st.session_state["lib_selected_result"] = get_result(rid)
                    st.rerun()
            with btn_col2:
                if st.button("Delete", key=f"del_{rid}", use_container_width=True):
                    delete_record(rid)
                    if st.session_state.get("lib_selected_rid") == rid:
                        st.session_state.pop("lib_selected_rid", None)
                        st.session_state.pop("lib_selected_result", None)
                    st.rerun()

    # ── Detail panel ──────────────────────────────────────────────────────────
    if "lib_selected_rid" in st.session_state and "lib_selected_result" in st.session_state:
        result = st.session_state["lib_selected_result"]
        rid = st.session_state["lib_selected_rid"]
        if result:
            st.markdown('<hr style="border:none; border-top:1px solid #e2e8f0; margin:1.5rem 0 1.2rem;">', unsafe_allow_html=True)
            st.markdown(
                '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
                'letter-spacing:0.1em; margin:0 0 1rem;">ANALYSIS RESULT</p>',
                unsafe_allow_html=True,
            )
            _show_result(result, rid)
        else:
            st.error("Could not load result data for this record.")
