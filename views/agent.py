"""views/agent.py — Risk Intelligence Agent tab. Left/right split layout."""

import streamlit as st
import json

from storage.store import load_index, get_result
from core.agent import run_agent
from core.comparator import compare_risks


SUGGESTED_QUERIES = [
    "Prioritize all risks and identify the top 5 most critical threats",
    "Which risks pose the greatest financial impact?",
    "Summarize the emerging risks and recommend monitoring actions",
    "Compare risks year-over-year and highlight what changed most",
    "What are the most urgent risks requiring immediate attention?",
]


def _priority_color(p):
    return {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}.get(p, "#6b7280")


def _priority_badge(p):
    color = _priority_color(p)
    return (
        f'<span style="background:{color}; color:#fff; padding:2px 10px; '
        f'border-radius:12px; font-size:0.78rem; font-weight:600;">{p}</span>'
    )


def render():
    index = load_index()

    if not index:
        st.info("No records yet. Go to **Analyze → New Analysis** to upload a filing first.")
        return

    # ── Left / Right split ───────────────────────────────────────────────────
    col_left, col_right = st.columns([1, 2], gap="large")

    # ════════════════════════════════════════════════════════
    # LEFT PANEL — Configuration + Query
    # ════════════════════════════════════════════════════════
    with col_left:
        st.markdown(
            """
            <div style="background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);
                 border:1px solid #bbf7d0; border-radius:12px; padding:0.8rem 1rem; margin-bottom:1rem;">
                <p style="margin:0; font-size:0.9rem; color:#166534;">
                    🤖 <strong>Risk Intelligence Agent</strong><br>
                    <span style="font-size:0.82rem;">Configure below, ask a question, and run the agent.</span>
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Company & Year
        st.markdown('<div class="section-header">⚙️ Configure</div>', unsafe_allow_html=True)
        companies = sorted(set(r["company"] for r in index))
        company = st.selectbox("Company", companies, key="agent_company")
        co_recs = [r for r in index if r["company"] == company]
        years = sorted(set(r["year"] for r in co_recs), reverse=True)
        year = st.selectbox("Year", years, key="agent_year")

        # Optional YoY compare
        use_compare = st.checkbox("Include YoY comparison", key="agent_use_compare")
        prior_year = None
        if use_compare:
            prior_opts = [y for y in years if y < year]
            if prior_opts:
                prior_year = st.selectbox("Compare against", prior_opts, key="agent_prior_year")
            else:
                st.caption("No prior year available.")
                use_compare = False

        # Suggested queries
        st.markdown('<div class="section-header">💬 Query</div>', unsafe_allow_html=True)
        st.caption("Quick select:")
        for i, q in enumerate(SUGGESTED_QUERIES):
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["agent_query_text"] = q
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        user_query = st.text_area(
            "Or type your own question",
            height=100,
            placeholder="e.g. What are the most critical risks?",
            key="agent_query_text",
        )

        run = st.button(
            "🚀 Run Agent",
            key="btn_run_agent",
            type="primary",
            use_container_width=True,
        )

        # Run logic
        if run:
            if not user_query.strip():
                st.error("Please enter a query.")
            else:
                rec = next((r for r in co_recs if r["year"] == year), None)
                if not rec:
                    st.error(f"No record found for {company} {year}.")
                else:
                    result = get_result(rec["record_id"])
                    if not result:
                        st.error("Could not load risk data.")
                    else:
                        risks = result.get("risks", [])
                        if not risks:
                            st.error("No risk data found in this record.")
                        else:
                            compare_data = None
                            if use_compare and prior_year:
                                prior_rec = next(
                                    (r for r in co_recs if r["year"] == prior_year), None
                                )
                                if prior_rec:
                                    prior_result = get_result(prior_rec["record_id"])
                                    if prior_result:
                                        compare_data = compare_risks(prior_result, result)

                            with st.spinner("🤖 Agent is working…"):
                                report = run_agent(
                                    user_query=user_query.strip(),
                                    company=company,
                                    year=year,
                                    risks=risks,
                                    compare_data=compare_data,
                                )
                            st.session_state["agent_report"] = report
                            st.rerun()

    # ════════════════════════════════════════════════════════
    # RIGHT PANEL — Report output
    # ════════════════════════════════════════════════════════
    with col_right:
        if "agent_report" not in st.session_state:
            st.markdown(
                """
                <div style="height:500px; display:flex; flex-direction:column;
                     justify-content:center; align-items:center;
                     background:#f8f9fb; border:2px dashed #e0e3e8; border-radius:16px;">
                    <p style="font-size:2.5rem; margin:0;">🤖</p>
                    <p style="font-size:1rem; color:#6b7280; margin:0.5rem 0 0 0;">
                        Configure and run the agent to see the report here
                    </p>
                    <p style="font-size:0.82rem; color:#9ca3af; margin:0.3rem 0 0 0;">
                        Results will appear in this panel
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            _display_report(st.session_state["agent_report"])


def _display_report(report: dict):
    company = report.get("company", "")
    year = report.get("year", "")
    query = report.get("user_query", "")
    pm = report.get("priority_matrix", {})
    enriched_risks = report.get("enriched_risks", [])

    # Header with overall rating
    overall = report.get("overall_risk_rating", "—")
    rating_colors = {
        "High": "#ef4444", "Medium-High": "#f97316",
        "Medium": "#f59e0b", "Medium-Low": "#84cc16", "Low": "#22c55e",
    }
    rc = rating_colors.get(overall, "#6b7280")
    st.markdown(
        f"""
        <div style="background:#f8f9fb; border:1px solid #e0e3e8; border-radius:12px;
             padding:1rem 1.5rem; margin-bottom:1rem; display:flex;
             justify-content:space-between; align-items:center;">
            <div>
                <p style="margin:0; font-size:1.05rem; font-weight:700; color:#111827;">
                    🤖 Agent Report — {company} {year}
                </p>
                <p style="margin:0.2rem 0 0 0; font-size:0.82rem; color:#6b7280;">
                    Query: "{query}"
                </p>
            </div>
            <div style="text-align:right; flex-shrink:0; margin-left:1rem;">
                <span style="font-size:0.72rem; color:#6b7280;">Overall Risk Rating</span><br>
                <span style="background:{rc}; color:#fff; padding:4px 14px;
                      border-radius:20px; font-weight:700; font-size:0.88rem;">{overall}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Agent execution trace
    steps = report.get("agent_steps", [])
    if steps:
        with st.expander("🔎 Agent execution trace", expanded=False):
            for s in steps:
                st.markdown(f"- {s}")

    # Priority matrix
    st.markdown('<div class="section-header">📊 Priority Matrix</div>', unsafe_allow_html=True)
    m1, m2, m3 = st.columns(3)
    m1.metric("🔴 High", pm.get("high", {}).get("count", 0))
    m2.metric("🟡 Medium", pm.get("medium", {}).get("count", 0))
    m3.metric("🟢 Low", pm.get("low", {}).get("count", 0))

    # Top High risks
    high_top = pm.get("high", {}).get("top", [])
    if high_top:
        st.markdown("**🔴 Top High-Priority Risks**")
        for r in high_top:
            st.markdown(
                f'<div class="card" style="border-left:4px solid #ef4444; padding:0.7rem 1rem; margin-bottom:0.4rem;">'
                f'<div style="display:flex; justify-content:space-between; align-items:flex-start;">'
                f'<span style="font-size:0.88rem; color:#111827; font-weight:500;">{r["title"]}</span>'
                f'<span style="margin-left:0.8rem; white-space:nowrap;">{_priority_badge("High")} '
                f'<span style="font-size:0.75rem; color:#6b7280;">score: {r["score"]}</span></span></div>'
                f'<p style="margin:0.25rem 0 0 0; font-size:0.8rem; color:#6b7280;">{r.get("reasoning","")}</p>'
                f'<p style="margin:0.15rem 0 0 0; font-size:0.75rem; color:#9ca3af;">Category: {r.get("category","")}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Executive Summary
    st.markdown('<div class="section-header">📋 Executive Summary</div>', unsafe_allow_html=True)
    st.info(report.get("executive_summary", "—"))

    # Risk themes
    themes = report.get("risk_themes", [])
    if themes:
        theme_html = " ".join(
            f'<span style="background:#eff6ff; color:#1e40af; padding:3px 10px; '
            f'border-radius:20px; font-size:0.8rem; margin-right:4px;">{t}</span>'
            for t in themes
        )
        st.markdown(f"**Risk Themes:** {theme_html}", unsafe_allow_html=True)

    # Key findings
    findings = report.get("key_findings", [])
    if findings:
        st.markdown('<div class="section-header">🔍 Key Findings</div>', unsafe_allow_html=True)
        for i, f in enumerate(findings, 1):
            st.markdown(f"**{i}.** {f}")

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        st.markdown('<div class="section-header">💡 Recommendations</div>', unsafe_allow_html=True)
        for i, r in enumerate(recs, 1):
            st.markdown(
                f'<div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; '
                f'padding:0.5rem 0.9rem; margin-bottom:0.4rem;">'
                f'<span style="font-weight:600; color:#166534;">{i}.</span> '
                f'<span style="color:#374151; font-size:0.9rem;">{r}</span></div>',
                unsafe_allow_html=True,
            )

    # YoY compare insights
    ci = report.get("compare_insights", "")
    if ci:
        st.markdown('<div class="section-header">📅 Year-over-Year Insights</div>', unsafe_allow_html=True)
        st.info(ci)

    # Full prioritized risk list
    if enriched_risks:
        st.markdown('<div class="section-header">⚠️ Full Prioritized Risk List</div>', unsafe_allow_html=True)
        priority_filter = st.selectbox(
            "Filter by priority",
            ["All", "High", "Medium", "Low"],
            key="agent_priority_filter",
        )
        for cat_block in enriched_risks:
            cat = cat_block.get("category", "Unknown")
            subs = cat_block.get("sub_risks", [])
            if not subs:
                continue
            filtered_subs = subs if priority_filter == "All" else [
                s for s in subs if isinstance(s, dict) and s.get("priority") == priority_filter
            ]
            if not filtered_subs:
                continue
            with st.expander(f"**{cat}** ({len(filtered_subs)} risks)", expanded=False):
                for s in filtered_subs:
                    if not isinstance(s, dict):
                        continue
                    p = s.get("priority", "Medium")
                    score = s.get("score", 5.0)
                    st.markdown(
                        f'<div style="border-left:3px solid {_priority_color(p)}; '
                        f'padding:0.4rem 0.8rem; margin-bottom:0.3rem;">'
                        f'<div style="display:flex; justify-content:space-between;">'
                        f'<span style="font-size:0.85rem; color:#111827;">{s.get("title","")[:150]}</span>'
                        f'<span style="white-space:nowrap; margin-left:0.5rem;">'
                        f'{_priority_badge(p)} <span style="font-size:0.73rem; color:#9ca3af;">{score}</span>'
                        f'</span></div>'
                        f'<p style="margin:0.15rem 0 0 0; font-size:0.76rem; color:#9ca3af;">{s.get("reasoning","")}</p>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    # Download
    st.divider()
    dl_data = {k: v for k, v in report.items() if k != "enriched_risks"}
    dl_data["prioritized_risks"] = enriched_risks
    st.download_button(
        "📥 Download Agent Report (JSON)",
        data=json.dumps(dl_data, indent=2, ensure_ascii=False),
        file_name=f"{company}_{year}_agent_report.json".replace(" ", "_"),
        mime="application/json",
        key="dl_agent_report",
        use_container_width=True,
    )
