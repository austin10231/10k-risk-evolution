"""Home / Introduction page."""

import streamlit as st


def render():
    st.title("🛡️ Risk Change Alert Report")
    st.markdown(
        "**Automatically extract, structure, and compare SEC 10-K Risk Factors "
        "(Item 1A) across filing years — producing a memo-ready risk change report.**"
    )

    st.divider()

    # ── 3-step workflow ──────────────────────────────────────────────────────
    st.subheader("How It Works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            '<div class="card">'
            "<h4>① Upload</h4>"
            "<p>Upload a 10-K filing HTML from SEC EDGAR.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="card">'
            "<h4>② Extract & Classify</h4>"
            "<p>Item 1A is located, split into risk blocks, and each block is tagged "
            "with a risk theme.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="card">'
            "<h4>③ Compare & Export</h4>"
            "<p>Compare year-over-year changes (NEW / REMOVED / MODIFIED) and export "
            "a structured JSON report.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Scope ────────────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### ✅ MVP Scope (current)")
        st.markdown(
            "- 10-K filing HTML upload\n"
            "- Item 1A (Risk Factors) text extraction\n"
            "- Risk block segmentation & keyword-based theme tagging\n"
            "- YoY & multi-year comparison with change scoring\n"
            "- Structured JSON export"
        )
    with col_b:
        st.markdown("##### 🔮 Phase 2 (planned)")
        st.markdown(
            "- 10-Q support\n"
            "- PDF upload parsing\n"
            "- Financial statement table extraction\n"
            "- LLM-powered risk summarization\n"
            "- EDGAR direct download by CIK / ticker"
        )

    st.divider()
    st.markdown("**Ready?** Use the sidebar to navigate to **Analyze** or **Compare**.")
