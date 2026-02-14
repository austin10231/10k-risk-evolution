"""Compare page — cross-year diff of risk blocks."""

import streamlit as st
import json
from storage.store import load_index, get_result
from core.comparator import compare_filings
from components.display import download_json_button


def render():
    st.title("⚖️ Compare — Year-over-Year Risk Changes")

    index = load_index()
    if not index:
        st.info(
            "No records in the Library yet. "
            "Please go to **Analyze → New Analysis** to upload filings first."
        )
        return

    # ── Inputs ────────────────────────────────────────────────────────────────
    companies = sorted(set(r["company"] for r in index))
    company = st.selectbox("Company", companies, key="cmp_company")

    company_recs = [r for r in index if r["company"] == company]
    filing_types = sorted(set(r["filing_type"] for r in company_recs))
    filing_type = st.selectbox("Filing Type", filing_types, key="cmp_ftype")

    type_recs = [r for r in company_recs if r["filing_type"] == filing_type]
    years_available = sorted(set(r["year"] for r in type_recs))

    if len(years_available) < 2:
        st.warning(
            f"Only {len(years_available)} filing(s) found for **{company}** / "
            f"**{filing_type}**. You need at least 2 years to compare."
        )
        return

    col_a, col_b = st.columns(2)
    with col_a:
        latest_year = st.selectbox(
            "Latest year (t)",
            years_available[::-1],
            key="cmp_latest",
        )
    with col_b:
        prior_options = [y for y in years_available if y < latest_year]
        if not prior_options:
            st.warning("No prior year available before the selected latest year.")
            return
        prior_years = st.multiselect(
            "Prior year(s) (t−1, t−2, …)",
            prior_options[::-1],
            default=[prior_options[-1]],
            key="cmp_prior",
        )

    if not prior_years:
        st.warning("Select at least one prior year.")
        return

    run = st.button("🚀 Run Compare", type="primary", key="btn_run_compare")

    if not run:
        return

    # ── Resolve records ───────────────────────────────────────────────────────
    def find_record(yr):
        for r in type_recs:
            if r["year"] == yr:
                return r
        return None

    latest_rec = find_record(latest_year)
    latest_result = get_result(latest_rec["record_id"]) if latest_rec else None

    if latest_result is None:
        st.error(f"Cannot load result for {company} {latest_year}.")
        return

    # ── Run comparisons ──────────────────────────────────────────────────────
    for py in sorted(prior_years, reverse=True):
        prior_rec = find_record(py)
        prior_result = get_result(prior_rec["record_id"]) if prior_rec else None
        if prior_result is None:
            st.error(f"Cannot load result for {company} {py}.")
            continue

        st.divider()
        st.subheader(f"Comparison: {latest_year} vs {py}")

        with st.spinner("Computing changes …"):
            changes = compare_filings(prior_result, latest_result)

        if not changes:
            st.success("No significant changes detected.")
            continue

        # ── Top changes table ─────────────────────────────────────────────────
        st.markdown(f"**Top {len(changes)} Risk Changes**")

        for idx, ch in enumerate(changes):
            badge_color = {
                "NEW": "🟢", "REMOVED": "🔴", "MODIFIED": "🟡",
            }.get(ch["change_type"], "⚪")

            label = (
                f"{badge_color} **{ch['change_type']}** — "
                f"`{ch['risk_theme']}` — score {ch['change_score']}"
            )
            with st.expander(label, expanded=(idx < 3)):
                st.write(ch["short_explanation"])

                # Drill-down: old vs new side-by-side
                c_old, c_new = st.columns(2)
                with c_old:
                    st.markdown(f"**Prior ({py})**")
                    if ch["prior_block"]:
                        st.text_area(
                            "Prior text",
                            ch["prior_block"]["risk_text"],
                            height=180,
                            key=f"prior_{py}_{idx}_{latest_year}",
                            disabled=True,
                        )
                    else:
                        st.caption("— not present —")
                with c_new:
                    st.markdown(f"**Latest ({latest_year})**")
                    if ch["latest_block"]:
                        st.text_area(
                            "Latest text",
                            ch["latest_block"]["risk_text"],
                            height=180,
                            key=f"latest_{py}_{idx}_{latest_year}",
                            disabled=True,
                        )
                    else:
                        st.caption("— not present —")

        # ── Export compare JSON ───────────────────────────────────────────────
        export = {
            "company": company,
            "filing_type": filing_type,
            "latest_year": latest_year,
            "prior_year": py,
            "total_changes": len(changes),
            "changes": [
                {k: v for k, v in ch.items() if k not in ("latest_block", "prior_block")}
                for ch in changes
            ],
            "changes_with_evidence": changes,
        }
        download_json_button(
            export,
            filename=f"{company}_compare_{latest_year}_vs_{py}.json",
            key=f"dl_cmp_{latest_year}_{py}",
        )
