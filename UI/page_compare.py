import streamlit as st
from functions.storage import ensure_storage, list_records, load_report_json
from functions.compare import compare_reports
from UI.components import changes_table, side_by_side_evidence, download_json_button

def render_compare_page():
    ensure_storage()
    st.header("Compare (t vs t-1)")

    records = list_records()
    if not records:
        st.info("Library is empty. Go to Analyze page and upload filings first.")
        return

    # 简化：从Library里选两条记录做对比
    st.markdown("## Select two records from Library")
    companies = sorted(list({r["company"] for r in records}))
    company = st.selectbox("Company", options=companies, index=0)

    company_records = [r for r in records if r["company"] == company]
    years = sorted(list({r["year"] for r in company_records}))
    if len(years) < 2:
        st.warning("Need at least two years in library for this company.")
        return

    col1, col2 = st.columns(2)
    year_latest = col1.selectbox("Latest year (t)", options=sorted(years, reverse=True), index=0)
    year_prior = col2.selectbox("Prior year (t-1)", options=[y for y in sorted(years, reverse=True) if y != year_latest], index=0)

    # pick record id by year + filing type (default 10-K)
    latest_record = next((r for r in company_records if r["year"] == year_latest and r["filing_type"] == "10-K"), None)
    prior_record  = next((r for r in company_records if r["year"] == year_prior and r["filing_type"] == "10-K"), None)

    if not latest_record or not prior_record:
        st.warning("Could not find 10-K records for selected years. Upload them in Analyze page.")
        return

    run = st.button("Run Compare", type="primary", use_container_width=True)

    if run:
        latest_report = load_report_json(latest_record["record_id"])
        prior_report = load_report_json(prior_record["record_id"])

        with st.spinner("Comparing risk blocks..."):
            result = compare_reports(
                latest=latest_report,
                prior=prior_report,
                company=company,
                year_latest=year_latest,
                year_prior=year_prior,
            )

        changes_table(result["risk_changes"])

        # Drill-down
        st.markdown("## Drill-down Evidence")
        if result["risk_changes"]:
            labels = [
                f'{i+1}. {c["change_type"]} | {c["risk_theme"]} | score={c.get("change_score",0)}'
                for i, c in enumerate(result["risk_changes"])
            ]
            pick = st.selectbox("Pick a change", options=labels, index=0)
            idx = int(pick.split(".")[0]) - 1
            chosen = result["risk_changes"][idx]
            side_by_side_evidence(chosen.get("old_text"), chosen.get("new_text"))

        download_json_button(result, filename=f"{company}-{year_latest}-vs-{year_prior}-compare.json", label="Export Compare JSON")
