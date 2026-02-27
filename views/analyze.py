"""Analyze page — Library + New Analysis. Readable text display."""

import streamlit as st
import json

from storage.store import (
    load_index, add_record, get_result, filter_records, delete_record,
    _s3_write, RESULTS_PREFIX,
)
from core.extractor import (
    extract_item1_overview, extract_item1a_risks,
    extract_text_from_pdf, extract_item1_overview_from_text,
    extract_item1a_risks_from_text,
)
from core.bedrock import classify_risks, generate_summary
from components.filters import library_filters

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def _count_sub_risks(risks):
    return sum(len(c.get("sub_risks", [])) for c in risks)


def _show_output(result, key):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")

    st.markdown(
        f"**{ov.get('company', '—')}** · {ov.get('year', '—')} · "
        f"**{len(risks)}** risk categories · "
        f"**{_count_sub_risks(risks)}** risk items"
    )

    # AI Summary at top
    if ai_summary:
        st.markdown("##### 🤖 AI Executive Summary")
        st.info(ai_summary)

    # Company Overview
    st.markdown("##### 🏢 Company Overview")
    st.markdown(f"**Company:** {ov.get('company', '—')}")
    st.markdown(f"**Industry:** {ov.get('industry', '—')}")
    st.markdown(f"**Year:** {ov.get('year', '—')} · **Filing:** {ov.get('filing_type', '—')}")
    bg = ov.get("background", "")
    if bg:
        st.markdown(f"**Background:** {bg}")

    # Risk Categories
    st.markdown(f"##### ⚠️ Risk Categories ({len(risks)})")
    for cat_block in risks:
        cat_name = cat_block.get("category", "Unknown")
        subs = cat_block.get("sub_risks", [])
        sub_count = len(subs)

        if subs and isinstance(subs[0], dict):
            with st.expander(f"**{cat_name}** ({sub_count} risks)", expanded=False):
                for s in subs:
                    labels = s.get("labels", [])
                    label_str = " · ".join(f"`{l}`" for l in labels) if labels else ""
                    title = s.get("title", "")[:150]
                    st.markdown(f"- {title}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
        else:
            st.markdown(f"- **{cat_name}** — {sub_count} risk items")

    # Download at bottom
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"{ov.get('company','export')}_{ov.get('year','')}.json",
        mime="application/json",
        key=f"dl_{key}",
        use_container_width=True,
    )


def _run_ai(result, record_id):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])

    with st.spinner("🤖 Classifying risks with AI …"):
        classified = classify_risks(risks)
    result["risks"] = classified

    with st.spinner("🤖 Generating executive summary …"):
        summary = generate_summary(
            ov.get("company", ""), ov.get("year", 0), classified
        )
    result["ai_summary"] = summary

    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    st.session_state["last_analyze_result"] = result
    st.rerun()


def render():
    tab_lib, tab_new = st.tabs(["📚 Library", "➕ New Analysis"])

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
                fmt=flt["format"],
            )
            if not filtered:
                st.warning("No records match the current filters.")
            else:
                labels = [
                    f"{r['company']} | {r['year']} | {r['filing_type']} | {r['industry']} | ({r.get('file_ext', 'html').upper()})"
                    for r in filtered
                ]
                sel = st.selectbox(
                    "Select a record", range(len(labels)),
                    format_func=lambda i: labels[i], key="lib_select",
                )
                rec = filtered[sel]

                if st.button(
                    "🗑️ Delete this record",
                    key=f"del_{rec['record_id']}",
                    type="secondary",
                ):
                    delete_record(rec["record_id"])
                    st.success("Record deleted.")
                    st.rerun()

                result = get_result(rec["record_id"])
                if result is None:
                    st.error("Result JSON not found.")
                else:
                    st.divider()
                    _show_output(result, key=f"lib_{rec['record_id']}")

                    if not result.get("ai_summary"):
                        if st.button(
                            "🤖 AI Summarize",
                            key=f"ai_lib_{rec['record_id']}",
                        ):
                            _run_ai(result, rec["record_id"])

    with tab_new:
        col_input, col_output = st.columns([2, 3])

        with col_input:
            st.markdown("##### Inputs")
            uploaded = st.file_uploader(
                "Upload filing (HTML or PDF)",
                type=["html", "htm", "pdf"],
                key="new_upload",
            )
            year = st.selectbox(
                "Filing Year", list(range(2025, 2009, -1)), key="new_year",
            )
            company = st.text_input("Company Name", key="new_company")
            industry = st.selectbox("Industry", INDUSTRIES, key="new_industry")
            filing_type = st.selectbox(
                "Filing Type", ["10-K", "10-Q (coming soon)"], key="new_ftype",
            )
            run = st.button(
                "🚀 Extract & Save",
                key="btn_run_analyze", use_container_width=True,
            )
            st.caption(
                "Tip: HTML works best for structured extraction. "
                "PDF uses AWS Textract for text extraction."
            )

        with col_output:
            if "last_analyze_result" in st.session_state:
                res = st.session_state["last_analyze_result"]
                rid = st.session_state.get("last_analyze_rid", "x")
                _show_output(res, key=f"new_{rid}")

                if not res.get("ai_summary"):
                    if st.button(
                        "🤖 AI Summarize",
                        key=f"ai_new_{rid}",
                    ):
                        _run_ai(res, rid)

        if run:
            if not company.strip():
                st.error("Please enter a company name.")
                return
            if uploaded is None:
                st.error("Please upload a file.")
                return
            if "coming soon" in filing_type:
                st.warning("10-Q support is not yet available.")
                return

            file_bytes = uploaded.read()
            file_name = uploaded.name.lower()
            is_pdf = file_name.endswith(".pdf")

            if is_pdf:
                with st.spinner("Extracting text from PDF via AWS Textract …"):
                    pdf_text = extract_text_from_pdf(file_bytes)
                if not pdf_text:
                    st.error("Textract could not extract text from this PDF.")
                    return
                with st.spinner("Parsing Item 1 overview …"):
                    overview = extract_item1_overview_from_text(
                        pdf_text, company.strip(), industry,
                    )
                with st.spinner("Parsing Item 1A risks …"):
                    risks = extract_item1a_risks_from_text(pdf_text)
            else:
                with st.spinner("Extracting Item 1 overview …"):
                    overview = extract_item1_overview(
                        file_bytes, company.strip(), industry,
                    )
                with st.spinner("Extracting Item 1A risks …"):
                    risks = extract_item1a_risks(file_bytes)

            if not risks:
                st.error(
                    "Could not extract risks from Item 1A. "
                    "Check that the file is a valid SEC 10-K filing."
                )
                return

            overview["year"] = int(year)
            overview["filing_type"] = filing_type

            result = {
                "company_overview": overview,
                "risks": risks,
            }

            rid = add_record(
                company=company.strip(),
                industry=industry,
                year=int(year),
                filing_type=filing_type,
                file_bytes=file_bytes,
                file_ext="pdf" if is_pdf else "html",
                result_json=result,
            )

            st.session_state["last_analyze_result"] = result
            st.session_state["last_analyze_rid"] = rid
            st.rerun()
