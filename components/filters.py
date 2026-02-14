"""Reusable filter widgets for the Library."""

import streamlit as st


def library_filters(index: list[dict], key_prefix: str = "flt") -> dict:
    """Render filter dropdowns and return selected values."""
    industries = sorted(set(r["industry"] for r in index))
    companies = sorted(set(r["company"] for r in index))
    years = sorted(set(str(r["year"]) for r in index), reverse=True)
    ftypes = sorted(set(r["filing_type"] for r in index))

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        industry = st.selectbox(
            "Industry", ["All"] + industries, key=f"{key_prefix}_ind"
        )
    with c2:
        company = st.selectbox(
            "Company", ["All"] + companies, key=f"{key_prefix}_comp"
        )
    with c3:
        year = st.selectbox(
            "Year", ["All"] + years, key=f"{key_prefix}_yr"
        )
    with c4:
        ftype = st.selectbox(
            "Filing Type", ["All"] + ftypes, key=f"{key_prefix}_ft"
        )

    return {
        "industry": industry,
        "company": company,
        "year": year,
        "filing_type": ftype,
    }
