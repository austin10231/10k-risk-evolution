"""Compare page — NEW / REMOVED risk diff. Readable text display."""

import streamlit as st
import json

from storage.store import load_index, get_result, save_compare_result
from core.comparator import compare_risks
from core.bedrock import analyze_changes


def render():
    index = load_index()
    if not index:
        st.info("No records yet. Go to **Analyze → New Analysis** first.")
        return

    companies = sorted(set(r["company"] for r in index))
    company = st.selectbox("Company", companies, key="cmp_co")

    co_recs = [r for r in index if r["company"] == company]
    ftypes = sorted(set(r["filing_type"] for r in co_recs))
    ftype = st.selectbox("Filing Type", ftypes, key="cmp_ft")

    type_recs = [r for r in co_recs if r["filing_type"] == ftype]
    years = sorted(set(r["year"] for r in type_recs))

    if len(years) < 2:
        st.warning(f"Need at least 2 years for **{company}** / **{ftype}**.")
        return

    c1, c2 = st.columns(2)
    with c1:
        latest_year = st.selectbox("Latest year (t)", years[::-1], key="cmp_ly")
    with c2:
        prior_opts = [y for y in years if y < latest_year]
        if not prior_opts:
            st.warning("No prior year available.")
            return
        prior_years = st.multiselect(
            "Prior year(s)", prior_opts[::-1],
            default=[prior_opts[-1]], key="cmp_py",
        )

    if not prior_years:
        st.warning("Select at least one prior year.")
        return

    run = st.button("🚀 Run Compare", key="btn_run_cmp")
    if not run:
        # Show previous results if available
        if "cmp_results" in st.session_state:
            _display_compare_results(st.session_state["cmp_results"], company, ftype)
        return

    def find_rec(yr):
        return next((r for r in type_recs if r["year"] == yr), None)

    latest_rec = find_rec(latest_year)
    latest_res = get_result(latest_rec["record_id"]) if latest_rec else None
    if latest_res is None:
        st.error(f"Cannot load {company} {latest_year}.")
        return

    all_comparisons = []

    for py in sorted(prior_years, reverse=True):
        prior_rec = find_rec(py)
        prior_res = get_result(prior_rec["record_id"]) if prior_rec else None
        if prior_res is None:
            st.error(f"Cannot load {company} {py}.")
            continue

        cmp = compare_risks(prior_res, latest_res)

        all_comparisons.append({
            "company": company,
            "filing_type": ftype,
            "prior_year": py,
            "latest_year": latest_year,
            "new_risks": cmp["new_risks"],
            "removed_risks": cmp["removed_risks"],
        })

    # Store in session state and display
    st.session_state["cmp_results"] = all_comparisons
    _display_compare_results(all_comparisons, company, ftype)


def _display_compare_results(all_comparisons, company, ftype):
    """Display compare results with AI analysis support."""

    # Initialize AI results storage
    if "cmp_ai_texts" not in st.session_state:
        st.session_state["cmp_ai_texts"] = {}

    for export in all_comparisons:
        py = export["prior_year"]
        latest_year = export["latest_year"]

        st.divider()
        st.subheader(f"{latest_year} vs {py}")

        m1, m2 = st.columns(2)
        m1.metric("🟢 New Risks", len(export["new_risks"]))
        m2.metric("🔴 Removed Risks", len(export["removed_risks"]))

        if export["new_risks"]:
            st.markdown(f"**🟢 New Risks in {latest_year}** (not in {py})")
            for r in export["new_risks"]:
                st.markdown(f"- **[{r.get('category', '')}]** {r.get('title', '')[:150]}")

        if export["removed_risks"]:
            st.markdown(f"**🔴 Removed Risks** (in {py}, not in {latest_year})")
            for r in export["removed_risks"]:
                st.markdown(f"- **[{r.get('category', '')}]** {r.get('title', '')[:150]}")

        if not export["new_risks"] and not export["removed_risks"]:
            st.success("No new or removed risks detected.")

        # AI Change Analysis
        ai_key = f"{company}_{latest_year}_{py}"

        if ai_key in st.session_state["cmp_ai_texts"]:
            st.markdown("##### 🤖 AI Analysis")
            st.info(st.session_state["cmp_ai_texts"][ai_key])
        else:
            if st.button("🤖 AI Change Analysis", key=f"ai_cmp_{latest_year}_{py}"):
                with st.spinner("🤖 Analyzing changes …"):
                    ai_text = analyze_changes(
                        company, latest_year, py,
                        export["new_risks"], export["removed_risks"],
                    )
                st.session_state["cmp_ai_texts"][ai_key] = ai_text
                st.rerun()

        st.download_button(
            "⬇️ Download Compare JSON",
            data=json.dumps(export, indent=2, ensure_ascii=False),
            file_name=f"{company}_compare_{latest_year}_vs_{py}.json",
            mime="application/json",
            key=f"dl_cmp_{latest_year}_{py}",
        )

    if all_comparisons:
        combined = {
            "company": company,
            "filing_type": ftype,
            "latest_year": all_comparisons[0]["latest_year"],
            "prior_years": [c["prior_year"] for c in all_comparisons],
            "comparisons": all_comparisons,
        }
        s3_key = save_compare_result(
            company=company,
            filing_type=ftype,
            latest_year=all_comparisons[0]["latest_year"],
            prior_years=[c["prior_year"] for c in all_comparisons],
            compare_json=combined,
        )
        st.divider()
        st.success(f"Compare result saved to S3: `{s3_key}`")
