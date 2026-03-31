"""Tables page — Extract 5 core financial tables from PDF via Textract."""

from __future__ import annotations

import streamlit as st

from core.table_extractor import extract_tables_from_pdf
from core.sec_edgar import download_10k_pdf_for_company_year, build_filing_html_url
from storage.store import save_table_result
from components.table_viewer import classified_to_csv, count_found_tables, render_table_output

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def _process_and_save_tables(company: str, industry: str, year: int, filing_type: str, classified: dict, source: str = ""):

    found_count = count_found_tables(classified)
    if found_count == 0:
        st.error("No core financial tables could be identified in this filing.")
        return

    result = {
        "company": company.strip(),
        "industry": industry,
        "year": int(year),
        "filing_type": filing_type,
        "tables_found": found_count,
        "source": source or "tables_manual",
        **classified,
    }
    csv_data = classified_to_csv(classified)
    s3_key = save_table_result(
        company=company.strip(),
        year=int(year),
        filing_type=filing_type,
        table_json=result,
        csv_string=csv_data,
    )
    st.session_state["last_table_result"] = result
    st.session_state["last_table_rid"] = s3_key
    st.success(f"Financial tables extracted and saved for {company} {year}.")
    st.rerun()


def _render_results_panel():
    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.8rem;">RESULTS</p>',
        unsafe_allow_html=True,
    )
    if "last_table_result" in st.session_state:
        render_table_output(
            st.session_state["last_table_result"],
            key_prefix=f"tbl_{st.session_state.get('last_table_rid', 'x')}",
        )
    else:
        st.markdown(
            """
            <div class="empty-state" style="height:380px; display:flex; flex-direction:column;
                 justify-content:center; align-items:center;">
                <p class="empty-state-icon">📊</p>
                <p class="empty-state-title">Extracted tables will appear here</p>
                <p class="empty-state-sub">Upload a PDF or auto-fetch from SEC, then click extract</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_manual_panel():
    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.8rem;">MANUAL CONFIGURE</p>',
        unsafe_allow_html=True,
    )
    uploaded = st.file_uploader("Upload 10-K PDF", type=["pdf"], key="tbl_upload")
    company = st.text_input("Company Name", key="tbl_company", placeholder="e.g. Apple Inc.")

    col_y, col_i = st.columns(2)
    with col_y:
        year = st.selectbox("Filing Year", list(range(2025, 2009, -1)), key="tbl_year")
    with col_i:
        industry = st.selectbox("Industry", INDUSTRIES, key="tbl_industry")

    filing_type = st.selectbox("Filing Type", ["10-K", "10-Q (coming soon)"], key="tbl_ftype")
    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("Extract Tables (Manual PDF)", key="btn_extract_tables", type="primary", use_container_width=True)
    st.caption("Upload a 10-K PDF and run Textract extraction.")

    if not run:
        return
    if not company.strip():
        st.error("Please enter a company name.")
        return
    if uploaded is None:
        st.error("Please upload a PDF file.")
        return
    if "coming soon" in filing_type:
        st.warning("10-Q support is not yet available.")
        return
    with st.spinner("Locating Item 8 & extracting tables via AWS Textract…"):
        classified = extract_tables_from_pdf(uploaded.read())
    _process_and_save_tables(
        company.strip(),
        industry,
        int(year),
        filing_type,
        classified=classified,
        source="tables_manual_pdf",
    )


def _render_auto_panel():
    default_company = str(st.session_state.get("tbl_auto_company", "") or "")
    default_ticker = str(st.session_state.get("tbl_auto_ticker", "") or "")
    default_year = int(st.session_state.get("tbl_auto_year", 2025) or 2025)
    default_industry = str(st.session_state.get("tbl_auto_industry", "Technology") or "Technology")
    year_opts = list(range(2025, 2009, -1))
    year_idx = year_opts.index(default_year) if default_year in year_opts else 0
    industry_idx = INDUSTRIES.index(default_industry) if default_industry in INDUSTRIES else 0

    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.8rem;">AUTO CONFIGURE</p>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        company = st.text_input("Company Name", key="tbl_auto_company_input", value=default_company, placeholder="e.g. Apple")
    with c2:
        ticker = st.text_input("Ticker (optional)", key="tbl_auto_ticker_input", value=default_ticker, placeholder="e.g. AAPL")

    c3, c4, c5 = st.columns(3)
    with c3:
        year = st.selectbox("Filing Year", year_opts, index=year_idx, key="tbl_auto_year_input")
    with c4:
        industry = st.selectbox("Industry", INDUSTRIES, index=industry_idx, key="tbl_auto_industry_input")
    with c5:
        filing_type = st.selectbox("Filing Type", ["10-K"], key="tbl_auto_ftype_input")

    st.markdown("<br>", unsafe_allow_html=True)
    run_auto = st.button("Auto Fetch + Extract Tables", key="btn_auto_extract_tables", type="primary", use_container_width=True)
    st.caption("Auto-fetches SEC 10-K PDF by company/year (ticker optional), then runs Textract.")

    if not run_auto:
        return
    if not company.strip():
        st.error("Please enter a company name.")
        return

    with st.spinner(f"Downloading {company.strip()} {int(year)} 10-K document from SEC EDGAR…"):
        pdf_bytes, meta, err = download_10k_pdf_for_company_year(
            company_name=company.strip(),
            year=int(year),
            ticker=str(ticker or "").strip().upper(),
        )
    if pdf_bytes:
        with st.spinner("Locating Item 8 & extracting tables via AWS Textract…"):
            classified = extract_tables_from_pdf(pdf_bytes)
        _process_and_save_tables(
            company.strip(),
            industry,
            int(year),
            filing_type,
            classified=classified,
            source="tables_auto_sec_pdf",
        )
        return

    st.error(err or "Could not auto-download 10-K PDF from SEC EDGAR.")
    filing_url = build_filing_html_url(meta or {})
    if filing_url:
        st.link_button("Open SEC filing (print/save as PDF)", filing_url, use_container_width=True)
    st.caption("Textract requires PDF. If SEC filing is HTML-only, open filing and print/save to PDF, then use Manual PDF Upload.")


def render():
    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-icon">📊</span>
                <div>
                    <p class="page-title">Financial Tables</p>
                    <p class="page-subtitle">Extract 5 core financial statements from 10-K PDFs via AWS Textract</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_input, col_output = st.columns([2, 3], gap="large")
    with col_input:
        mode_manual, mode_auto = st.tabs(["📄 Manual PDF Upload", "🛰️ Auto Fetch from SEC EDGAR"])
        with mode_manual:
            _render_manual_panel()
        with mode_auto:
            _render_auto_panel()
    with col_output:
        _render_results_panel()
