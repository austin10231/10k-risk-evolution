"""Home / Introduction page."""

import streamlit as st


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
            "- YoY / multi-year NEW & REMOVED comparison\n"
            "- JSON & CSV export\n"
            "- AWS S3 persistent storage"
        )
    with col_b:
        st.markdown("##### 🔮 Phase 2")
        st.markdown(
            "- 10-Q support\n"
            "- LLM-powered risk summarization (AWS Bedrock)\n"
            "- Cross-company risk comparison\n"
            "- EDGAR direct download by CIK / ticker"
        )
