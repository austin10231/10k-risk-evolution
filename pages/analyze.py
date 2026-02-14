"""Analyze page — Library browser + New Analysis."""

import streamlit as st
import json
from storage.store import (
    load_index, add_record, get_result, filter_records,
)
from core.extractor import extract_item1a
from core.classifier import build_risk_blocks
from components.display import (
    show_overview, show_risk_blocks, show_json_preview, download_json_button,
)
from components.filters import library_filters

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def render():
    st.title("🔍 Analyze — Single Filing")

    tab_lib, tab_new = st.tabs(["📚 Library", "➕ New Analysis"])

    # ══════════════════════════════════════════════════════════════════════════
    #  TAB: LIBRARY
    # ══════════════════════════════════════════════════════════════════════════
    with tab_lib:
        st.subheader("Saved Analyses")
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
                    "Select a record",
                    range(len(labels)),
                    format_func=lambda i: labels[i],
                    key="lib_select",
                )
                rec = filtered[sel]
                result = get_result(rec["record_id"])

                if result is None:
                    st.error("Result JSON not found for this record.")
                else:
                    st.divider()
                    show_overview(result)
                    show_risk_blocks(result, key_prefix=f"lib_{rec['record_id']}")
                    show_json_preview(result, key_prefix=f"lib_{rec['record_id']}")
                    download_json_button(
                        result,
                        filename=f"{rec['company']}_{rec['year']}.json",
                        key=f"dl_lib_{rec['record_id']}",
                    )

    # ══════════════════════════════════════════════════════════════════════════
    #  TAB: NEW ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_new:
        st.subheader("Upload & Analyze a New Filing")

        col_l, col_r = st.columns(2)
        with col_l:
            industry = st.selectbox("Industry", INDUSTRIES, key="new_industry")
            company = st.text_input("Company Name", key="new_company")
            year = st.selectbox(
                "Filing Year",
                list(range(2025, 2009, -1)),
                key="new_year",
            )
        with col_r:
            filing_type = st.selectbox(
                "Filing Type",
                ["10-K", "10-Q (coming soon)"],
                key="new_ftype",
            )
            uploaded = st.file_uploader(
                "Upload filing HTML",
                type=["html", "htm"],
                key="new_upload",
            )

        run = st.button("🚀 Run Analyze", type="primary", key="btn_run_analyze")

        if run:
            # ── Validation ───────────────────────────────────────────────────
            if not company.strip():
                st.error("Please enter a company name.")
                return
            if uploaded is None:
                st.error("Please upload an HTML file.")
                return
            if "coming soon" in filing_type:
                st.warning("10-Q support is not yet available. Please select 10-K.")
                return

            html_bytes = uploaded.read()

            with st.spinner("Extracting Item 1A …"):
                item1a_text, locator = extract_item1a(html_bytes)

            if item1a_text is None:
                st.error(f"Extraction failed: {locator}")
                return

            with st.spinner("Building risk blocks …"):
                risk_blocks = build_risk_blocks(item1a_text)

            # ── Assemble result JSON ─────────────────────────────────────────
            result = {
                "company_overview": {
                    "company": company.strip(),
                    "industry": industry,
                    "year": int(year),
                    "filing_type": filing_type,
                    "source": uploaded.name,
                    "scope": "Item 1A – Risk Factors",
                    "item1a_locator": locator,
                },
                "risk_blocks": risk_blocks,
            }

            # ── Persist ─────────────────────────────────────────────────────
            rid = add_record(
                company=company.strip(),
                industry=industry,
                year=int(year),
                filing_type=filing_type,
                html_bytes=html_bytes,
                result_json=result,
            )

            st.success(f"Analysis saved (record `{rid}`). It now appears in the Library.")
            st.divider()

            show_overview(result)
            show_risk_blocks(result, key_prefix=f"new_{rid}")
            show_json_preview(result, key_prefix=f"new_{rid}")
            download_json_button(
                result,
                filename=f"{company.strip()}_{year}.json",
                key=f"dl_new_{rid}",
            )
