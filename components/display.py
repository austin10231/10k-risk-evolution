"""Reusable display components for risk analysis results."""

import streamlit as st
import json


def show_overview(result: dict):
    """Render company overview as metric cards."""
    ov = result.get("company_overview", {})
    st.markdown("#### Company Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Company", ov.get("company", "—"))
    c2.metric("Industry", ov.get("industry", "—"))
    c3.metric("Year", ov.get("year", "—"))
    c4.metric("Filing", ov.get("filing_type", "—"))

    c5, c6 = st.columns(2)
    c5.caption(f"Source: {ov.get('source', '—')}")
    c6.caption(f"Scope: {ov.get('scope', '—')}")


def show_risk_blocks(result: dict, key_prefix: str = ""):
    """Render risk blocks list with theme summary."""
    blocks = result.get("risk_blocks", [])
    st.markdown(f"#### Risk Blocks ({len(blocks)})")

    # Theme distribution
    themes: dict[str, int] = {}
    for b in blocks:
        t = b["risk_theme"]
        themes[t] = themes.get(t, 0) + 1

    if themes:
        sorted_themes = sorted(themes.items(), key=lambda x: -x[1])
        cols = st.columns(min(len(sorted_themes), 6))
        for i, (theme, count) in enumerate(sorted_themes):
            cols[i % len(cols)].metric(theme, count)

    for i, b in enumerate(blocks):
        with st.expander(
            f"[{b['risk_theme'].upper()}] {b['title']}",
            expanded=False,
        ):
            st.write(b["risk_text"])
            st.caption(
                f"Block ID: `{b['block_id'][:12]}…` · "
                f"Evidence: {b['evidence_pointer']}"
            )


def show_json_preview(result: dict, key_prefix: str = ""):
    """Collapsible full JSON viewer."""
    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)


def download_json_button(data: dict, filename: str, key: str):
    """Download button with unique key."""
    st.download_button(
        label="⬇️ Download JSON",
        data=json.dumps(data, indent=2, default=str),
        file_name=filename,
        mime="application/json",
        key=key,
    )
