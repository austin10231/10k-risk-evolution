"""Reusable display helpers for analysis results."""

import streamlit as st
import json


def show_analysis_result(result: dict, key_prefix: str = ""):
    """Display overview + risks + JSON preview + download."""
    ov = result.get("company_overview", {})

    # ── Overview card ─────────────────────────────────────────────────────────
    st.markdown("#### Company Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", ov.get("company", "—"))
    c2.metric("Industry", ov.get("industry", "—"))
    c3.metric("Year", ov.get("year", "—"))
    c4.metric("Filing", ov.get("filing_type", "—"))

    overview_text = ov.get("overview_text", "")
    if overview_text:
        with st.expander("📝 Item 1 Overview Text", expanded=False):
            st.write(overview_text)

    # ── Risks summary ────────────────────────────────────────────────────────
    risks = result.get("risks", [])
    st.markdown(f"#### Risks Extracted ({len(risks)})")

    for i, r in enumerate(risks):
        with st.expander(r.get("title", f"Risk {i+1}"), expanded=False):
            st.write(r.get("content", ""))

    # ── JSON preview ─────────────────────────────────────────────────────────
    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)

    # ── Download ─────────────────────────────────────────────────────────────
    fname = f"{ov.get('company','export')}_{ov.get('year','')}.json"
    st.download_button(
        "⬇️ Download JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=fname,
        mime="application/json",
        key=f"dl_{key_prefix}",
    )
