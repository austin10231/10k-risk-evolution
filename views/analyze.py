"""Analyze page — Library + New Analysis."""

import streamlit as st
import json

from storage.store import load_index, add_record, get_result, filter_records
from core.extractor import extract_item1_overview, extract_item1a_risks
from components.display import show_analysis_result
from components.filters import library_filters

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def render():
    tab_lib, tab_new = st.tabs(["📚 Library", "➕ New Analysis"])

    # ══════════════════════════════════════════════════════════════════════════
    #  LIBRARY
    # ══════════════════════════════════════════════════════════════════════════
    with tab_lib:
        index = load_index()
        if not index:
            st.info("No records yet. Switch to **New Analysis** to upload a filing.")
        else:
            flt = library_filters(index, key_prefix="lib")
            filtered = filter_records(
                industry=flt["industry"],
                company=flt["company"],
                year=flt["year"],
                filing_type=flt["filing_type"],
            )
            if not filtered:
                st.warning("No records match the current filters.")
            else:
                labels = [
                    f"{r['company']} | {r['year']} | {r['filing_type']} | {r['industry']}"
                    for r in filtered
                ]
                sel = st.selectbox(
                    "Select a record", range(len(labels)),
                    format_func=lambda i: labels[i], key="lib_select",
                )
                rec = filtered[sel]
                result = get_result(rec["record_id"])
                if result is None:
                    st.error("Result JSON not found.")
                else:
                    show_analysis_result(result, key_prefix=f"lib_{rec['record_id']}")

    # ══════════════════════════════════════════════════════════════════════════
    #  NEW ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_new:
        col_l, col_r = st.columns(2)
        with col_l:
            industry = st.selectbox("Industry", INDUSTRIES, key="new_industry")
            company = st.text_input("Company Name", key="new_company")
            year = st.selectbox("Filing Year", list(range(2025, 2009, -1)), key="new_year")
        with col_r:
            filing_type = st.selectbox(
                "Filing Type", ["10-K", "10-Q (coming soon)"], key="new_ftype",
            )
            uploaded = st.file_uploader("Upload filing HTML", type=["html", "htm"], key="new_upload")

        run = st.button("🚀 Run Analyze", type="primary", key="btn_run_analyze")

        if run:
            if not company.strip():
                st.error("Please enter a company name.")
                return
            if uploaded is None:
                st.error("Please upload an HTML file.")
                return
            if "coming soon" in filing_type:
                st.warning("10-Q support is not yet available.")
                return

            html_bytes = uploaded.read()

            with st.spinner("Extracting Item 1 overview …"):
                overview_text = extract_item1_overview(html_bytes)

            with st.spinner("Extracting Item 1A risks …"):
                risks = extract_item1a_risks(html_bytes)

            if not risks:
                st.error("Could not extract any risks from Item 1A. Check the HTML file.")
                return

            result = {
                "company_overview": {
                    "company": company.strip(),
                    "industry": industry,
                    "year": int(year),
                    "filing_type": filing_type,
                    "overview_text": overview_text,
                },
                "risks": risks,
            }

            rid = add_record(
                company=company.strip(),
                industry=industry,
                year=int(year),
                filing_type=filing_type,
                html_bytes=html_bytes,
                result_json=result,
            )

            st.success(f"Saved (record `{rid}`). Now available in Library.")
            st.divider()
            show_analysis_result(result, key_prefix=f"new_{rid}")
