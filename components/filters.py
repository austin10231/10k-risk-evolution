"""Reusable filter widgets for the Library."""

import streamlit as st

def library_filters(index, key_prefix="flt"):
    industries = sorted(set(r["industry"] for r in index))
    companies = sorted(set(r["company"] for r in index))
    years = sorted(set(str(r["year"]) for r in index), reverse=True)
    ftypes = sorted(set(r["filing_type"] for r in index))
    formats = sorted(set(r.get("file_ext", "html").upper() for r in index))
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        industry = st.selectbox("Industry", ["All"] + industries, key=f"{key_prefix}_ind")
    with c2:
        company = st.selectbox("Company", ["All"] + companies, key=f"{key_prefix}_comp")
    with c3:
        year = st.selectbox("Year", ["All"] + years, key=f"{key_prefix}_yr")
    with c4:
        ftype = st.selectbox("Filing Type", ["All"] + ftypes, key=f"{key_prefix}_ft")
    with c5:
        fmt = st.selectbox("Format", ["All"] + formats, key=f"{key_prefix}_fmt")
    return {"industry": industry, "company": company, "year": year, "filing_type": ftype, "format": fmt}
