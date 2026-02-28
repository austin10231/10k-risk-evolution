"""Compare page — YoY and Cross-Company risk diff."""

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

    # ── Mode toggle as styled tabs ───────────────────────
    mode_tab_yoy, mode_tab_cross = st.tabs(["📅  Year-over-Year", "🏢  Cross-Company"])

    with mode_tab_yoy:
        _render_yoy(index)

    with mode_tab_cross:
        _render_cross(index)


# ── Year-over-Year ───────────────────────────────────────
def _render_yoy(index):
    companies = sorted(set(r["company"] for r in index))

    col1, col2 = st.columns(2)
    with col1:
        company = st.selectbox("Company", companies, key="cmp_co")
    with col2:
        co_recs = [r for r in index if r["company"] == company]
        ftypes = sorted(set(r["filing_type"] for r in co_recs))
        ftype = st.selectbox("Filing Type", ftypes, key="cmp_ft")

    type_recs = [r for r in co_recs if r["filing_type"] == ftype]
    years = sorted(set(r["year"] for r in type_recs))

    if len(years) < 2:
        st.warning(f"Need at least 2 years for **{company}** / **{ftype}**.")
        return

    col3, col4 = st.columns(2)
    with col3:
        latest_year = st.selectbox("Latest Year", years[::-1], key="cmp_ly")
    with col4:
        prior_opts = [y for y in years if y < latest_year]
        if not prior_opts:
            st.warning("No prior year available.")
            return
        prior_years = st.multiselect(
            "Prior Year(s)", prior_opts[::-1],
            default=[prior_opts[-1]], key="cmp_py",
        )

    if not prior_years:
        st.warning("Select at least one prior year.")
        return

    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("🚀 Run Compare", key="btn_run_yoy", type="primary")

    if not run:
        if "cmp_results" in st.session_state and st.session_state.get("cmp_last_mode") == "yoy":
            _display_compare_results(
                st.session_state["cmp_results"],
                st.session_state.get("cmp_last_label_a", company),
                st.session_state.get("cmp_last_label_b", ""),
                ftype, mode="yoy",
            )
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
            "label_a": f"{company} {py}",
            "label_b": f"{company} {latest_year}",
            "new_risks": cmp["new_risks"],
            "removed_risks": cmp["removed_risks"],
        })

    st.session_state["cmp_results"] = all_comparisons
    st.session_state["cmp_last_mode"] = "yoy"
    st.session_state["cmp_last_label_a"] = company
    st.session_state["cmp_last_label_b"] = ""
    _display_compare_results(all_comparisons, company, "", ftype, mode="yoy")


# ── Cross-Company ────────────────────────────────────────
def _render_cross(index):
    companies = sorted(set(r["company"] for r in index))

    col_a_head, col_b_head = st.columns(2)
    with col_a_head:
        st.markdown(
            '<div style="background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;'
            'padding:0.5rem 1rem; font-weight:600; color:#1e40af; margin-bottom:0.8rem;">Company A</div>',
            unsafe_allow_html=True,
        )
    with col_b_head:
        st.markdown(
            '<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px;'
            'padding:0.5rem 1rem; font-weight:600; color:#166534; margin-bottom:0.8rem;">Company B</div>',
            unsafe_allow_html=True,
        )

    col_a, col_b = st.columns(2)
    with col_a:
        co_a = st.selectbox("Company", companies, key="cmp_co_a")
        recs_a = [r for r in index if r["company"] == co_a]
        ftypes_a = sorted(set(r["filing_type"] for r in recs_a))
        ft_a = st.selectbox("Filing Type", ftypes_a, key="cmp_ft_a")
        years_a = sorted(set(r["year"] for r in recs_a if r["filing_type"] == ft_a), reverse=True)
        yr_a = st.selectbox("Year", years_a, key="cmp_yr_a")

    with col_b:
        co_b = st.selectbox("Company", companies, key="cmp_co_b")
        recs_b = [r for r in index if r["company"] == co_b]
        ftypes_b = sorted(set(r["filing_type"] for r in recs_b))
        ft_b = st.selectbox("Filing Type", ftypes_b, key="cmp_ft_b")
        years_b = sorted(set(r["year"] for r in recs_b if r["filing_type"] == ft_b), reverse=True)
        yr_b = st.selectbox("Year", years_b, key="cmp_yr_b")

    st.markdown("<br>", unsafe_allow_html=True)
    run = st.button("🚀 Run Compare", key="btn_run_cross", type="primary")

    if not run:
        if "cmp_results" in st.session_state and st.session_state.get("cmp_last_mode") == "cross":
            _display_compare_results(
                st.session_state["cmp_results"],
                st.session_state.get("cmp_last_label_a", ""),
                st.session_state.get("cmp_last_label_b", ""),
                "", mode="cross",
            )
        return

    rec_a = next((r for r in index if r["company"] == co_a and r["filing_type"] == ft_a and r["year"] == yr_a), None)
    rec_b = next((r for r in index if r["company"] == co_b and r["filing_type"] == ft_b and r["year"] == yr_b), None)

    if not rec_a or not rec_b:
        st.error("Could not find one or both selected records.")
        return

    res_a = get_result(rec_a["record_id"])
    res_b = get_result(rec_b["record_id"])
    if res_a is None or res_b is None:
        st.error("Could not load result JSON for one or both records.")
        return

    cmp = compare_risks(res_a, res_b)
    label_a = f"{co_a} {yr_a}"
    label_b = f"{co_b} {yr_b}"

    all_comparisons = [{
        "company": f"{co_a} vs {co_b}",
        "filing_type": f"{ft_a} / {ft_b}",
        "prior_year": yr_a,
        "latest_year": yr_b,
        "label_a": label_a,
        "label_b": label_b,
        "new_risks": cmp["new_risks"],
        "removed_risks": cmp["removed_risks"],
    }]

    st.session_state["cmp_results"] = all_comparisons
    st.session_state["cmp_last_mode"] = "cross"
    st.session_state["cmp_last_label_a"] = label_a
    st.session_state["cmp_last_label_b"] = label_b
    _display_compare_results(all_comparisons, label_a, label_b, "", mode="cross")


# ── Display results ──────────────────────────────────────
def _display_compare_results(all_comparisons, label_a, label_b, ftype, mode="yoy"):
    if "cmp_ai_texts" not in st.session_state:
        st.session_state["cmp_ai_texts"] = {}

    for export in all_comparisons:
        la = export.get("label_a", label_a)
        lb = export.get("label_b", label_b)

        st.divider()
        if mode == "yoy":
            st.subheader(f"{export['latest_year']} vs {export['prior_year']}")
            analysis_title = f"{export['company']} · {export['latest_year']} vs {export['prior_year']}"
        else:
            st.subheader(f"{lb}  vs  {la}")
            analysis_title = f"{lb} vs {la}"

        m1, m2 = st.columns(2)
        m1.metric(f"🟢 Only in {lb}", len(export["new_risks"]))
        m2.metric(f"🔴 Only in {la}", len(export["removed_risks"]))

        if export["new_risks"]:
            st.markdown(f"**🟢 Risks unique to {lb}**")
            grouped_new = {}
            for r in export["new_risks"]:
                cat = r.get("category", "Uncategorized")
                grouped_new.setdefault(cat, []).append(r.get("title", "")[:150])
            for cat, titles in grouped_new.items():
                with st.expander(f"{cat} ({len(titles)})", expanded=False):
                    for t in titles:
                        st.markdown(f"- {t}")

        if export["removed_risks"]:
            st.markdown(f"**🔴 Risks unique to {la}**")
            grouped_removed = {}
            for r in export["removed_risks"]:
                cat = r.get("category", "Uncategorized")
                grouped_removed.setdefault(cat, []).append(r.get("title", "")[:150])
            for cat, titles in grouped_removed.items():
                with st.expander(f"{cat} ({len(titles)})", expanded=False):
                    for t in titles:
                        st.markdown(f"- {t}")

        if not export["new_risks"] and not export["removed_risks"]:
            st.success("No differing risks detected between the two selections.")

        # AI Change Analysis
        ai_key = f"{la}_vs_{lb}"
        if ai_key in st.session_state["cmp_ai_texts"]:
            st.markdown("##### 🤖 AI Analysis")
            st.info(st.session_state["cmp_ai_texts"][ai_key])
        else:
            if st.button("🤖 AI Change Analysis", key=f"ai_cmp_{ai_key}"):
                with st.spinner("🤖 Analyzing differences …"):
                    ai_text = analyze_changes(
                        analysis_title, lb, la,
                        export["new_risks"], export["removed_risks"],
                        mode=mode,
                    )
                st.session_state["cmp_ai_texts"][ai_key] = ai_text
                st.rerun()

        st.download_button(
            "⬇️ Download Compare JSON",
            data=json.dumps(export, indent=2, ensure_ascii=False),
            file_name=f"compare_{la}_vs_{lb}.json".replace(" ", "_"),
            mime="application/json",
            key=f"dl_cmp_{ai_key}",
        )

    if all_comparisons and mode == "yoy":
        combined = {
            "company": all_comparisons[0]["company"],
            "filing_type": ftype,
            "latest_year": all_comparisons[0]["latest_year"],
            "prior_years": [c["prior_year"] for c in all_comparisons],
            "comparisons": all_comparisons,
        }
        s3_key = save_compare_result(
            company=all_comparisons[0]["company"],
            filing_type=ftype,
            latest_year=all_comparisons[0]["latest_year"],
            prior_years=[c["prior_year"] for c in all_comparisons],
            compare_json=combined,
        )
        st.divider()
        st.success(f"Compare result saved to S3: `{s3_key}`")
