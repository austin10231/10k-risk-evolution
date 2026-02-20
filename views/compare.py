"""Compare page — NEW / REMOVED risk diff by sub-risk title matching."""

import streamlit as st
import json

from storage.store import load_index, get_result, save_compare_result
from core.comparator import compare_risks


def render():
    index = load_index()
    if not index:
        st.info("No records yet. Go to **Analyze → New Analysis** first.")
        return

    companies = sorted(set(r["company"] for r in index))
    company = st.selectbox("Company", companies, key="cmp_company")

    co_recs = [r for r in index if r["company"] == company]
    ftypes = sorted(set(r["filing_type"] for r in co_recs))
    ftype = st.selectbox("Filing Type", ftypes, key="cmp_ftype")

    type_recs = [r for r in co_recs if r["filing_type"] == ftype]
    years = sorted(set(r["year"] for r in type_recs))

    if len(years) < 2:
        st.warning(f"Need at least 2 years for **{company}** / **{ftype}**.")
        return

    c1, c2 = st.columns(2)
    with c1:
        latest_year = st.selectbox("Latest year (t)", years[::-1], key="cmp_latest")
    with c2:
        prior_opts = [y for y in years if y < latest_year]
        if not prior_opts:
            st.warning("No prior year available.")
            return
        prior_years = st.multiselect(
            "Prior year(s)", prior_opts[::-1],
            default=[prior_opts[-1]], key="cmp_prior",
        )

    if not prior_years:
        st.warning("Select at least one prior year.")
        return

    run = st.button("🚀 Run Compare", type="primary", key="btn_cmp")
    if not run:
        return

    def find_rec(yr):
        return next((r for r in type_recs if r["year"] == yr), None)

    latest_rec = find_rec(latest_year)
    latest_res = get_result(latest_rec["record_id"]) if latest_rec else None
    if latest_res is None:
        st.error(f"Cannot load {company} {latest_year}.")
        return

    for py in sorted(prior_years, reverse=True):
        prior_rec = find_rec(py)
        prior_res = get_result(prior_rec["record_id"]) if prior_rec else None
        if prior_res is None:
            st.error(f"Cannot load {company} {py}.")
            continue

        st.divider()
        st.subheader(f"{latest_year} vs {py}")

        cmp = compare_risks(prior_res, latest_res)

        # ── Stats ─────────────────────────────────────────────────────────
        m1, m2 = st.columns(2)
        m1.metric("🟢 New Risks", len(cmp["new_risks"]))
        m2.metric("🔴 Removed Risks", len(cmp["removed_risks"]))

        # ── Output as JSON ────────────────────────────────────────────────
        export = {
            "company": company,
            "filing_type": ftype,
            "prior_year": py,
            "latest_year": latest_year,
            "new_risks": cmp["new_risks"],
            "removed_risks": cmp["removed_risks"],
        }

        st.json(export)

        # ── Save to S3 ───────────────────────────────────────────────
        s3_key = save_compare_result(
            company=company,
            filing_type=ftype,
            latest_year=latest_year,
            prior_years=[py],
            compare_json=export,
        )
        st.caption(f"Saved to S3: `{s3_key}`")

        st.download_button(
            "⬇️ Download Compare JSON",
            data=json.dumps(export, indent=2, ensure_ascii=False),
            file_name=f"{company}_compare_{latest_year}_vs_{py}.json",
            mime="application/json",
            key=f"dl_cmp_{latest_year}_{py}_{company}",
        )
