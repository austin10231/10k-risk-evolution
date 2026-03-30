"""Upload page — new 10-K filing with stepper progress indicator."""

import streamlit as st
import json

from storage.store import add_record, _s3_write, RESULTS_PREFIX
from core.extractor import (
    extract_item1_overview, extract_item1a_risks,
    extract_text_from_pdf, extract_item1_overview_from_text,
    extract_item1a_risks_from_text,
)
from core.bedrock import classify_risks, generate_summary
from core.comprehend import enrich_risks_with_comprehend

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


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
    st.session_state["upload_result"] = result
    st.rerun()


def _stepper(step: int):
    """Render a 3-step progress indicator. step: 1=Upload, 2=Processing, 3=Done."""
    def _cls(n):
        if n < step:   return "done"
        if n == step:  return "active"
        return "pending"
    def _lbl(n, text):
        c = _cls(n)
        icon = "✓" if c == "done" else str(n)
        return (
            f'<div class="step-item">'
            f'<div class="step-circle {c}">{icon}</div>'
            f'<span class="step-text {c}">{text}</span>'
            f'</div>'
        )
    def _conn(n):
        c = "done" if n < step else ""
        return f'<div class="step-connector {c}"></div>'

    st.markdown(
        f'<div class="stepper">'
        f'{_lbl(1,"Configure")} {_conn(1)} {_lbl(2,"Extract")} {_conn(2)} {_lbl(3,"Results")}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _show_result(result, rid):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")
    comprehend_meta = result.get("comprehend_meta", {})

    # Metrics strip
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Company", ov.get("company", "—"))
    mc2.metric("Year", ov.get("year", "—"))
    mc3.metric("Risk Categories", len(risks))
    mc4.metric("Risk Items", _count_sub_risks(risks))

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
        if st.button("🤖 Run AI Summarize", key=f"ai_up_{rid}"):
            _run_ai(result, rid)

    # Business overview
    bg = ov.get("background", "")
    if bg:
        st.markdown('<div class="section-header">🏢 Business Overview</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-size:0.88rem; color:#374151; line-height:1.6;">{bg}</p>',
            unsafe_allow_html=True,
        )

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
                    st.markdown(f"- {s.get('title','')[:150]}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
                    if tag_str:
                        st.caption(f"   Tags: {tag_str}")
        else:
            st.markdown(f"- **{cat_name}** — {len(subs)} items")

    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"{ov.get('company','export')}_{ov.get('year','')}.json",
        mime="application/json",
        key=f"dl_up_{rid}",
        use_container_width=True,
    )


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-icon">➕</span>
                <div>
                    <p class="page-title">Upload Filing</p>
                    <p class="page-subtitle">Extract risk factors from a new 10-K filing</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Determine current step for stepper
    has_result = "upload_result" in st.session_state
    _stepper(3 if has_result else 1)

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([2, 3], gap="large")

    with col_left:
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.8rem;">CONFIGURE</p>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Filing file (HTML or PDF)",
            type=["html", "htm", "pdf"],
            key="up_file",
        )
        company = st.text_input("Company Name", key="up_company", placeholder="e.g. Apple Inc.")

        col_y, col_i = st.columns(2)
        with col_y:
            year = st.selectbox("Filing Year", list(range(2025, 2009, -1)), key="up_year")
        with col_i:
            industry = st.selectbox("Industry", INDUSTRIES, key="up_industry")

        filing_type = st.selectbox(
            "Filing Type", ["10-K", "10-Q (coming soon)"], key="up_ftype"
        )

        st.markdown("<br>", unsafe_allow_html=True)

        run = st.button("🚀 Extract & Save", key="btn_run_upload",
                        type="primary", use_container_width=True)
        st.caption("HTML works best for structured extraction. PDF uses AWS Textract.")

    # ── Right panel: results or empty state ───────────────────────────────────
    with col_right:
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.8rem;">RESULTS</p>',
            unsafe_allow_html=True,
        )

        if not has_result:
            st.markdown(
                """
                <div class="empty-state" style="height:380px; display:flex; flex-direction:column;
                     justify-content:center; align-items:center;">
                    <p class="empty-state-icon">📋</p>
                    <p class="empty-state-title">Extraction results will appear here</p>
                    <p class="empty-state-sub">Configure the inputs on the left, then hit Extract & Save</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            result = st.session_state["upload_result"]
            rid = st.session_state.get("upload_rid", "x")
            _show_result(result, rid)

    # ── Handle extraction ─────────────────────────────────────────────────────
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
        is_pdf = uploaded.name.lower().endswith(".pdf")

        if is_pdf:
            with st.spinner("Extracting text via AWS Textract…"):
                pdf_text = extract_text_from_pdf(file_bytes)
            if not pdf_text:
                st.error("Textract could not extract text from this PDF.")
                return
            with st.spinner("Parsing Item 1 overview…"):
                overview = extract_item1_overview_from_text(pdf_text, company.strip(), industry)
            with st.spinner("Parsing Item 1A risks…"):
                risks = extract_item1a_risks_from_text(pdf_text)
        else:
            with st.spinner("Extracting Item 1 overview…"):
                overview = extract_item1_overview(file_bytes, company.strip(), industry)
            with st.spinner("Extracting Item 1A risks…"):
                risks = extract_item1a_risks(file_bytes)

        if not risks:
            st.error(
                "Could not extract risks from Item 1A. "
                "Check that the file is a valid SEC 10-K filing."
            )
            return

        overview["year"] = int(year)
        overview["filing_type"] = filing_type
        result = {"company_overview": overview, "risks": risks}

        rid = add_record(
            company=company.strip(),
            industry=industry,
            year=int(year),
            filing_type=filing_type,
            file_bytes=file_bytes,
            file_ext="pdf" if is_pdf else "html",
            result_json=result,
        )

        st.session_state["upload_result"] = result
        st.session_state["upload_rid"] = rid
        st.rerun()
