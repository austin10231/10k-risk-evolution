import streamlit as st
from services.storage import (
    ensure_storage, upsert_record_and_save_files,
    list_records, load_report_json, get_record_by_id
)
from services.extract_item1a import extract_item_1a_text
from services.risk_blocks import build_risk_blocks
from services.exporter import build_report_payload
from ui.components import info_kv_card, risk_blocks_list, json_viewer, download_json_button

INDUSTRY_OPTIONS = [
    "Technology - Consumer Electronics",
    "Technology - Cloud / Software",
    "Semiconductors",
    "Retail",
    "Energy",
    "Other",
]

def render_analyze_page():
    ensure_storage()
    st.header("Analyze (Single Filing → Structured JSON)")

    # ---------- Library ----------
    st.markdown("## Library (Previously Uploaded)")
    records = list_records()

    with st.expander("Open Library", expanded=True):
        colf1, colf2, colf3 = st.columns(3)

        industries = sorted(list({r["industry"] for r in records})) if records else []
        companies = sorted(list({r["company"] for r in records})) if records else []
        years = sorted(list({r["year"] for r in records})) if records else []

        industry_f = colf1.selectbox("Filter: Industry", options=["(All)"] + industries, index=0)
        company_f = colf2.selectbox("Filter: Company", options=["(All)"] + companies, index=0)
        year_f = colf3.selectbox("Filter: Year", options=["(All)"] + years, index=0)

        def match(r):
            if industry_f != "(All)" and r["industry"] != industry_f: return False
            if company_f != "(All)" and r["company"] != company_f: return False
            if year_f != "(All)" and str(r["year"]) != str(year_f): return False
            return True

        filtered = [r for r in records if match(r)]
        if not filtered:
            st.info("No records match the filters.")
        else:
            options = [f'{r["industry"]} | {r["company"]} | {r["year"]} | {r["filing_type"]} | id={r["record_id"][:8]}' for r in filtered]
            pick = st.selectbox("Select a record to load", options=options, index=0)
            picked_id = pick.split("id=")[-1]
            # record_id在展示里截断了，这里用前缀匹配
            chosen = next((r for r in filtered if r["record_id"].startswith(picked_id)), None)

            if chosen:
                report = load_report_json(chosen["record_id"])
                st.markdown("### Loaded Report (from Library)")
                info_kv_card("Company Overview", report.get("company_overview", {}))
                risk_blocks_list(report.get("risk_blocks", []))
                json_viewer(report, title="Full JSON")
                download_json_button(report, filename=f'{chosen["company"]}-{chosen["year"]}-{chosen["filing_type"]}.json')

    st.divider()

    # ---------- New Analyze ----------
    st.markdown("## New Analysis (Upload HTML)")

    c1, c2, c3, c4 = st.columns(4)
    industry = c1.selectbox("Industry", options=INDUSTRY_OPTIONS, index=0)
    company = c2.text_input("Company (Ticker/CIK)", value="AAPL")
    year = c3.selectbox("Year", options=[2022, 2023, 2024, 2025], index=2)
    filing_type = c4.selectbox("Filing Type", options=["10-K", "10-Q (Phase 2)"], index=0)

    uploaded = st.file_uploader("Upload SEC filing (HTML)", type=["html", "htm"])

    run = st.button("Run Analyze", type="primary", use_container_width=True)

    if run:
        if not uploaded:
            st.error("Please upload an HTML filing first.")
            return

        filing_type_norm = "10-K" if filing_type.startswith("10-K") else "10-Q"

        html_bytes = uploaded.read()
        html_text = html_bytes.decode("utf-8", errors="ignore")

        with st.spinner("Extracting Item 1A..."):
            item1a_text, locator = extract_item_1a_text(html_text)

        with st.spinner("Building risk blocks..."):
            blocks = build_risk_blocks(item1a_text)

        with st.spinner("Building report JSON..."):
            report = build_report_payload(
                company=company.strip(),
                year=int(year),
                filing_type=filing_type_norm,
                industry=industry,
                item1a_locator=locator,
                risk_blocks=blocks,
            )

        with st.spinner("Saving to Library..."):
            record_id = upsert_record_and_save_files(
                company=company.strip(),
                year=int(year),
                filing_type=filing_type_norm,
                industry=industry,
                html_filename=uploaded.name,
                html_bytes=html_bytes,
                report_json=report,
            )

        st.success(f"Saved. record_id = {record_id}")

        info_kv_card("Company Overview", report["company_overview"])
        risk_blocks_list(report["risk_blocks"])
        download_json_button(report, filename=f"{company}-{year}-{filing_type_norm}.json")
