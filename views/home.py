"""Home / Introduction page."""

import streamlit as st


def _run_ai(result, record_id):
    """Run AI classification + summary, update result in S3."""
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

    # Save updated result back to S3
    from storage.store import _s3_write, RESULTS_PREFIX
    import json as _json
    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        _json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    st.session_state["last_analyze_result"] = result
    st.rerun()


def render():
    st.markdown(
        "**Automatically extract, structure, and compare SEC 10-K Risk Factors "
        "(Item 1A) across filing years — producing a memo-ready risk change report.**"
    )
    st.divider()

    st.subheader("How It Works")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            '<div class="card"><h4>① Upload</h4>'
            "<p>Upload a 10-K filing (HTML or PDF) from SEC EDGAR.</p></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="card"><h4>② Extract</h4>'
            "<p>Item 1 overview & Item 1A risks are extracted into structured JSON.</p></div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="card"><h4>③ Compare</h4>'
            "<p>Compare years to find NEW and REMOVED risks, then export JSON.</p></div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            '<div class="card"><h4>④ Tables</h4>'
            "<p>Extract financial tables from PDF filings via AWS Textract.</p></div>",
            unsafe_allow_html=True,
        )

    st.divider()
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### ✅ Current Features")
        st.markdown(
            "- 10-K filing upload (HTML & PDF)\n"
            "- Item 1 overview + Item 1A hierarchical risk extraction\n"
            "- PDF text extraction via AWS Textract\n"
            "- Financial statement table extraction (PDF)\n"
            "- AI-powered risk classification & summarization (AWS Bedrock)\n"
            "- YoY / multi-year NEW & REMOVED comparison\n"
            "- AI-powered change analysis\n"
            "- JSON & CSV export\n"
            "- AWS S3 persistent storage"
        )
    with col_b:
        st.markdown("##### 🔮 Phase 2")
        st.markdown(
            "- 10-Q support\n"
            "- Cross-company risk comparison\n"
            "- Risk trend dashboard\n"
            "- EDGAR direct download by CIK / ticker"
        )
