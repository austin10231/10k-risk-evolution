"""Library page — card grid for browsing uploaded filings."""

import streamlit as st
import json

from storage.store import (
    load_index,
    get_result,
    filter_records,
    delete_record,
    _s3_write,
    RESULTS_PREFIX,
    has_table_result,
    load_table_result,
    save_table_result,
    load_table_presence_tokens,
    get_company_ticker,
    get_original_file,
)
from core.bedrock import classify_risks, generate_summary
from core.comprehend import enrich_risks_with_comprehend
from core.table_extractor import extract_tables_from_pdf
from core.sec_edgar import download_10k_pdf_for_company_year, build_filing_html_url
from components.filters import library_filters
from components.table_viewer import classified_to_csv, count_found_tables, render_table_output

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
    with st.spinner("Extracting entities and key phrases with Comprehend…"):
        enriched_risks, comprehend_meta = enrich_risks_with_comprehend(classified)
    result["risks"] = enriched_risks
    result["comprehend_meta"] = comprehend_meta
    with st.spinner("Generating executive summary…"):
        summary = generate_summary(ov.get("company", ""), ov.get("year", 0), enriched_risks)
    result["ai_summary"] = summary
    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    st.session_state["lib_selected_result"] = result
    st.rerun()


def _extract_financial_tables_for_record(rec: dict, result: dict, ticker_override: str = "") -> None:
    company = str(rec.get("company", "")).strip()
    filing_type = str(rec.get("filing_type", "10-K") or "10-K")
    try:
        year = int(rec.get("year", 0))
    except Exception:
        year = 0

    if not company or not year:
        st.error("Missing company/year metadata for this record.")
        return
    if filing_type.upper() != "10-K":
        st.warning("Financial table extraction currently supports 10-K only.")
        return

    sec_meta = result.get("sec_meta", {}) if isinstance(result, dict) else {}
    ticker = str(ticker_override or "").strip().upper()
    if not ticker:
        ticker = str(sec_meta.get("ticker", "") or "").strip().upper()
    if not ticker:
        ticker = get_company_ticker(company, "")

    pdf_bytes = None
    pdf_meta = {}
    err = ""

    source = "library_one_click_extract"

    # 1) Prefer original uploaded file when this record itself is PDF.
    if str(rec.get("file_ext", "")).lower() == "pdf":
        with st.spinner("Using original uploaded PDF for this filing…"):
            pdf_bytes = get_original_file(record_id=rec.get("record_id", ""), file_ext="pdf")
        if pdf_bytes:
            pdf_meta = {"source": "library_original_pdf"}
            source = "library_original_pdf"

    # 2) Otherwise auto-fetch PDF from SEC.
    if not pdf_bytes:
        with st.spinner(f"Downloading {company} {year} 10-K PDF from SEC EDGAR…"):
            pdf_bytes, pdf_meta, err = download_10k_pdf_for_company_year(
                company_name=company,
                year=year,
                ticker=ticker,
            )
        if pdf_bytes:
            source = "library_sec_pdf"

    if not pdf_bytes:
        st.error(err or "Could not download 10-K PDF from SEC EDGAR.")
        filing_url = build_filing_html_url(pdf_meta or {})
        if filing_url:
            st.link_button("Open SEC filing (print/save as PDF)", filing_url, use_container_width=True)
        st.caption("Textract requires PDF. If this filing is HTML-only, open filing and print/save to PDF, then use Tables → Manual PDF Upload.")
        return

    with st.spinner("Extracting financial tables via AWS Textract…"):
        classified = extract_tables_from_pdf(pdf_bytes)

    found_count = count_found_tables(classified)
    if found_count == 0:
        st.error("No core financial tables could be identified in this filing PDF.")
        return

    table_result = {
        "company": company,
        "industry": rec.get("industry", "Other"),
        "year": year,
        "filing_type": filing_type,
        "tables_found": found_count,
        "source": source,
        "sec_pdf_meta": pdf_meta,
        **classified,
    }
    csv_data = classified_to_csv(classified)
    save_table_result(
        company=company,
        year=year,
        filing_type=filing_type,
        table_json=table_result,
        csv_string=csv_data,
    )
    st.success(f"Financial tables extracted and saved for {company} {year}.")
    st.rerun()


def _show_result(result, record_id, rec):
    """Render the analysis result panel."""
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")
    comprehend_meta = result.get("comprehend_meta", {})

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
        if comprehend_meta:
            if comprehend_meta.get("enabled"):
                st.caption(
                    "Comprehend enriched "
                    f"{comprehend_meta.get('enriched', 0)}/{comprehend_meta.get('processed', 0)} risk items."
                )
            else:
                st.caption(f"Comprehend skipped: {comprehend_meta.get('error', 'unknown reason')}")
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
                    tags = s.get("tags", [])
                    label_str = " · ".join(f"`{l}`" for l in labels) if labels else ""
                    tag_str = " · ".join(f"`{t}`" for t in tags[:6]) if tags else ""
                    st.markdown(f"- {s.get('title','')}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
                    if tag_str:
                        st.caption(f"   Tags: {tag_str}")
        else:
            if subs:
                with st.expander(f"**{cat_name}** ({len(subs)} risks)", expanded=False):
                    for s in subs:
                        title = str(s or "").strip()
                        if title:
                            st.markdown(f"- {title}")
            else:
                st.markdown(f"- **{cat_name}** — 0 items")

    st.markdown('<div class="section-header">📊 Financial Tables</div>', unsafe_allow_html=True)
    company = str(rec.get("company", ov.get("company", "")) or "").strip()
    year = rec.get("year", ov.get("year", ""))
    filing_type = rec.get("filing_type", ov.get("filing_type", "10-K"))
    table_result = None
    if company and year:
        table_result = load_table_result(company=company, year=year, filing_type=filing_type)

    if table_result:
        render_table_output(
            table_result,
            key_prefix=f"lib_tables_{record_id}",
            show_json_preview=False,
        )
    else:
        st.info("No extracted financial tables found for this filing.")
        can_extract = bool(result.get("risks"))
        if not can_extract:
            st.caption("Extraction unavailable: this record has no parsed risk analysis payload.")
        else:
            sec_meta = result.get("sec_meta", {}) if isinstance(result, dict) else {}
            ticker_default = str(sec_meta.get("ticker", "") or "").strip().upper() or get_company_ticker(company, "")
            ticker_input = st.text_input(
                "Ticker (optional, improves SEC lookup accuracy)",
                value=ticker_default,
                key=f"lib_extract_ticker_{record_id}",
                placeholder="e.g. AAPL",
            )
            c_btn1, c_btn2 = st.columns(2)
            with c_btn1:
                if st.button("Extract Financial Tables", key=f"lib_extract_tables_{record_id}", type="primary", use_container_width=True):
                    _extract_financial_tables_for_record(rec, result, ticker_override=ticker_input)
            with c_btn2:
                if st.button("Open Tables Page", key=f"lib_open_tables_{record_id}", use_container_width=True):
                    st.session_state["tbl_auto_company"] = company
                    st.session_state["tbl_auto_ticker"] = ticker_input
                    st.session_state["tbl_auto_year"] = int(year)
                    st.session_state["tbl_auto_industry"] = str(rec.get("industry", "Technology"))
                    st.session_state["current_page"] = "tables"
                    st.rerun()

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

    table_presence_tokens = load_table_presence_tokens()

    # ── Selected detail panel (moved above card grid for easier access) ─────
    if "lib_selected_rid" in st.session_state and "lib_selected_result" in st.session_state:
        result = st.session_state["lib_selected_result"]
        rid = st.session_state["lib_selected_rid"]
        selected_rec = next((r for r in index if r.get("record_id") == rid), None)
        if result:
            st.markdown(
                '<div style="margin:0.3rem 0 1rem; padding:0.6rem 0.8rem; border:1px solid #dbeafe; '
                'background:#f8fbff; border-radius:10px;">'
                '<p style="margin:0; font-size:0.78rem; color:#334155; font-weight:600;">'
                'Selected filing loaded. Details are shown below (above the card list) for faster review.'
                '</p></div>',
                unsafe_allow_html=True,
            )
            with st.expander("📌 Loaded Filing Details", expanded=True):
                _show_result(result, rid, selected_rec or {})
            st.markdown(
                '<hr style="border:none; border-top:1px solid #e2e8f0; margin:1.1rem 0 1rem;">',
                unsafe_allow_html=True,
            )
        else:
            st.error("Could not load result data for this record.")

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
            has_tables = has_table_result(
                company=company,
                year=year,
                filing_type=ftype,
                presence_tokens=table_presence_tokens,
            )

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
                    <p style="margin:0.55rem 0 0; font-size:0.7rem; font-weight:600; color:{'#166534' if has_tables else '#94a3b8'};">
                        {'📊 Financial tables available' if has_tables else '○ No financial tables extracted'}
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
