"""views/agent.py — Risk Intelligence Agent tab. Dashboard layout."""

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

PRIORITY_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"}
RATING_COLORS = {
    "High": "#ef4444", "Medium-High": "#f97316",
    "Medium": "#f59e0b", "Medium-Low": "#84cc16", "Low": "#22c55e",
}


def _badge(text, color):
    return (
        f'<span style="background:{color}; color:#fff; padding:2px 10px; '
        f'border-radius:12px; font-size:0.78rem; font-weight:600;">{text}</span>'
    )


def render():
    index = load_index()
    if not index:
        st.info("No records yet. Go to **Analyze → New Analysis** to upload a filing first.")
        return

    col_left, col_right = st.columns([1, 2], gap="large")

    # ════════════════════════════════════════════════════
    # LEFT — Configure + Suggested Queries
    # ════════════════════════════════════════════════════
    with col_left:
        st.markdown(
            """
            <div style="background:linear-gradient(135deg,#f0fdf4 0%,#dcfce7 100%);
                 border:1px solid #bbf7d0; border-radius:12px;
                 padding:0.8rem 1rem; margin-bottom:1.2rem;">
                <p style="margin:0; font-size:0.9rem; color:#166534; font-weight:600;">
                    🤖 Risk Intelligence Agent
                </p>
                <p style="margin:0.2rem 0 0 0; font-size:0.8rem; color:#166534;">
                    Configure, pick a query, then run.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Configure block ──────────────────────────
        st.markdown(
            '<p style="font-size:0.7rem; font-weight:700; color:#9ca3af; ' +
            'letter-spacing:0.08em; text-transform:uppercase; margin:0 0 0.5rem 0;">⚙️ Configure</p>',
            unsafe_allow_html=True,
        )
        companies = sorted(set(r["company"] for r in index))
        company = st.selectbox("Company", companies, key="agent_company", label_visibility="collapsed" if False else "visible")
        co_recs = [r for r in index if r["company"] == company]
        years = sorted(set(r["year"] for r in co_recs), reverse=True)
        year = st.selectbox("Year", years, key="agent_year")

        use_compare = st.checkbox("Include YoY comparison", key="agent_use_compare")
        prior_year = None
        if use_compare:
            prior_opts = [y for y in years if y < year]
            if prior_opts:
                prior_year = st.selectbox("Compare against", prior_opts, key="agent_prior_year")
            else:
                st.caption("No prior year available.")
                use_compare = False

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Suggested queries block ──────────────────
        st.markdown(
            '<p style="font-size:0.7rem; font-weight:700; color:#9ca3af; ' +
            'letter-spacing:0.08em; text-transform:uppercase; margin:0 0 0.5rem 0;">💬 Suggested Queries</p>',
            unsafe_allow_html=True,
        )
        for i, q in enumerate(SUGGESTED_QUERIES):
            if st.button(q, key=f"sq_{i}", use_container_width=True):
                st.session_state["agent_query_text"] = q
                st.rerun()

    # ════════════════════════════════════════════════════
    # RIGHT — Query input + Dashboard output
    # ════════════════════════════════════════════════════
    with col_right:

        # ── Query input ──────────────────────────────
        st.markdown(
            '<p style="font-size:0.7rem; font-weight:700; color:#9ca3af; ' +
            'letter-spacing:0.08em; text-transform:uppercase; margin:0 0 0.4rem 0;">💬 Your Query</p>',
            unsafe_allow_html=True,
        )
        user_query = st.text_area(
            "query",
            height=90,
            placeholder="Type a question or click a suggested query on the left…",
            key="agent_query_text",
            label_visibility="collapsed",
        )
        run = st.button("🚀 Run Agent", key="btn_run_agent", type="primary", use_container_width=True)

        if run:
            if not user_query.strip():
                st.error("Please enter a query or select one from the left.")
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
                                prior_rec = next((r for r in co_recs if r["year"] == prior_year), None)
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

        # ── Output area ──────────────────────────────
        if "agent_report" not in st.session_state:
            st.markdown(
                """
                <div style="margin-top:1.5rem; height:380px; display:flex; flex-direction:column;
                     justify-content:center; align-items:center;
                     background:#f8f9fb; border:2px dashed #e0e3e8; border-radius:16px;">
                    <p style="font-size:2.8rem; margin:0;">📊</p>
                    <p style="font-size:1rem; color:#6b7280; margin:0.6rem 0 0 0; font-weight:500;">
                        Your report will appear here
                    </p>
                    <p style="font-size:0.82rem; color:#9ca3af; margin:0.3rem 0 0 0;">
                        Configure on the left, type a query above, then hit Run Agent
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            _display_dashboard(st.session_state["agent_report"])


def _display_dashboard(report: dict):
    company = report.get("company", "")
    year = report.get("year", "")
    query = report.get("user_query", "")
    pm = report.get("priority_matrix", {})
    enriched_risks = report.get("enriched_risks", [])
    overall = report.get("overall_risk_rating", "—")
    rc = RATING_COLORS.get(overall, "#6b7280")
    themes = report.get("risk_themes", [])

    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    # ── LAYER 1: Overview dashboard strip ────────────────────────────────────
    h_count = pm.get("high", {}).get("count", 0)
    m_count = pm.get("medium", {}).get("count", 0)
    l_count = pm.get("low", {}).get("count", 0)

    themes_html = " ".join(
        f'<span style="background:#eff6ff; color:#1e40af; padding:3px 9px; '
        f'border-radius:20px; font-size:0.75rem; margin:2px;">{t}</span>'
        for t in themes
    ) if themes else '<span style="color:#9ca3af; font-size:0.8rem;">—</span>'

    st.markdown(
        f"""
        <div style="display:grid; grid-template-columns:1fr 1.6fr 1.4fr;
             gap:0.8rem; margin-bottom:1.2rem;">
            <div style="background:{rc}15; border:1.5px solid {rc}40;
                 border-radius:14px; padding:1rem; text-align:center;">
                <p style="margin:0; font-size:0.7rem; font-weight:700;
                   color:{rc}; text-transform:uppercase; letter-spacing:0.06em;">
                   Overall Risk
                </p>
                <p style="margin:0.4rem 0 0 0; font-size:1.6rem; font-weight:800; color:{rc};">
                    {overall}
                </p>
            </div>
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:14px; padding:1rem;">
                <p style="margin:0 0 0.6rem 0; font-size:0.7rem; font-weight:700;
                   color:#9ca3af; text-transform:uppercase; letter-spacing:0.06em;">
                   Priority Breakdown
                </p>
                <div style="display:flex; gap:1rem; align-items:center; justify-content:center;">
                    <div style="text-align:center;">
                        <p style="margin:0; font-size:1.6rem; font-weight:800; color:#ef4444;">{h_count}</p>
                        <p style="margin:0; font-size:0.72rem; color:#ef4444; font-weight:600;">HIGH</p>
                    </div>
                    <div style="width:1px; height:2rem; background:#e0e3e8;"></div>
                    <div style="text-align:center;">
                        <p style="margin:0; font-size:1.6rem; font-weight:800; color:#f59e0b;">{m_count}</p>
                        <p style="margin:0; font-size:0.72rem; color:#f59e0b; font-weight:600;">MEDIUM</p>
                    </div>
                    <div style="width:1px; height:2rem; background:#e0e3e8;"></div>
                    <div style="text-align:center;">
                        <p style="margin:0; font-size:1.6rem; font-weight:800; color:#22c55e;">{l_count}</p>
                        <p style="margin:0; font-size:0.72rem; color:#22c55e; font-weight:600;">LOW</p>
                    </div>
                </div>
            </div>
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:14px; padding:1rem;">
                <p style="margin:0 0 0.5rem 0; font-size:0.7rem; font-weight:700;
                   color:#9ca3af; text-transform:uppercase; letter-spacing:0.06em;">
                   Risk Themes
                </p>
                <div style="display:flex; flex-wrap:wrap; gap:4px;">{themes_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── LAYER 2: Detail tabs ──────────────────────────────────────────────────
    tab_risks, tab_summary, tab_findings, tab_recs, tab_full = st.tabs([
        f"🔴 Top Risks ({h_count} High)",
        "📋 Executive Summary",
        "🔍 Key Findings",
        "💡 Recommendations",
        f"⚠️ Full List ({h_count + m_count + l_count})",
    ])

    # ── Tab 1: Top Risks ─────────────────────────────────────────────────────
    with tab_risks:
        high_top = pm.get("high", {}).get("top", [])
        if not high_top:
            st.info("No high-priority risks identified.")
        else:
            for r in high_top:
                score = r.get("score", 0)
                score_pct = min(int((score / 10) * 100), 100)
                st.markdown(
                    f'''
                    <div style="background:#fff; border:1px solid #fecaca;
                         border-left:5px solid #ef4444; border-radius:10px;
                         padding:0.9rem 1.1rem; margin-bottom:0.7rem;">
                        <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:1rem;">
                            <p style="margin:0; font-size:0.88rem; color:#111827;
                               font-weight:600; line-height:1.4;">{r["title"]}</p>
                            <div style="text-align:right; flex-shrink:0;">
                                {_badge("High", "#ef4444")}
                                <p style="margin:0.2rem 0 0 0; font-size:0.75rem; color:#6b7280;">
                                    score {score}
                                </p>
                            </div>
                        </div>
                        <p style="margin:0.4rem 0 0.3rem 0; font-size:0.8rem; color:#6b7280;">
                            {r.get("reasoning", "")}
                        </p>
                        <div style="background:#fee2e2; border-radius:4px; height:4px; margin-top:0.4rem;">
                            <div style="background:#ef4444; border-radius:4px;
                                 height:4px; width:{score_pct}%;"></div>
                        </div>
                        <p style="margin:0.2rem 0 0 0; font-size:0.72rem; color:#9ca3af;">
                            Category: {r.get("category", "")}
                        </p>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

    # ── Tab 2: Executive Summary ──────────────────────────────────────────────
    with tab_summary:
        summary = report.get("executive_summary", "")
        if summary:
            st.markdown(
                f'''
                <div style="background:#f8faff; border:1px solid #dbeafe;
                     border-radius:12px; padding:1.4rem 1.6rem; line-height:1.8;
                     font-size:0.95rem; color:#1f2937;">
                    {summary}
                </div>
                ''',
                unsafe_allow_html=True,
            )
        query_text = report.get("user_query", "")
        if query_text:
            st.markdown(
                f'<p style="margin-top:1rem; font-size:0.8rem; color:#9ca3af;">' +
                f'Query: "{query_text}"</p>',
                unsafe_allow_html=True,
            )

        ci = report.get("compare_insights", "")
        if ci:
            st.markdown("**📅 Year-over-Year Insights**")
            st.info(ci)

    # ── Tab 3: Key Findings ───────────────────────────────────────────────────
    with tab_findings:
        findings = report.get("key_findings", [])
        if not findings:
            st.info("No findings available.")
        else:
            for i, f in enumerate(findings, 1):
                st.markdown(
                    f'''
                    <div style="display:flex; gap:0.8rem; align-items:flex-start;
                         padding:0.8rem 0; border-bottom:1px solid #f3f4f6;">
                        <div style="background:#eff6ff; color:#1e40af; font-weight:700;
                             font-size:0.85rem; padding:0.2rem 0.6rem;
                             border-radius:8px; flex-shrink:0; min-width:1.8rem;
                             text-align:center;">{i}</div>
                        <p style="margin:0; font-size:0.9rem; color:#374151;
                           line-height:1.5;">{f}</p>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

    # ── Tab 4: Recommendations ────────────────────────────────────────────────
    with tab_recs:
        recs = report.get("recommendations", [])
        if not recs:
            st.info("No recommendations available.")
        else:
            rec_icons = ["🎯", "👁️", "📈"]
            for i, r in enumerate(recs, 1):
                icon = rec_icons[i-1] if i <= len(rec_icons) else "•"
                st.markdown(
                    f'''
                    <div style="background:#f0fdf4; border:1px solid #bbf7d0;
                         border-left:4px solid #22c55e; border-radius:10px;
                         padding:0.9rem 1.1rem; margin-bottom:0.6rem;
                         display:flex; gap:0.8rem; align-items:flex-start;">
                        <span style="font-size:1.2rem; flex-shrink:0;">{icon}</span>
                        <p style="margin:0; font-size:0.9rem; color:#374151;
                           line-height:1.5;">{r}</p>
                    </div>
                    ''',
                    unsafe_allow_html=True,
                )

    # ── Tab 5: Full Prioritized List ──────────────────────────────────────────
    with tab_full:
        if not enriched_risks:
            st.info("No risk data available.")
        else:
            priority_filter = st.segmented_control(
                "Filter",
                ["All", "🔴 High", "🟡 Medium", "🟢 Low"],
                default="All",
                key="agent_priority_filter",
            )
            filter_map = {"All": "All", "🔴 High": "High", "🟡 Medium": "Medium", "🟢 Low": "Low"}
            selected = filter_map.get(priority_filter, "All")

            for cat_block in enriched_risks:
                cat = cat_block.get("category", "Unknown")
                subs = cat_block.get("sub_risks", [])
                if not subs:
                    continue
                filtered = subs if selected == "All" else [
                    s for s in subs if isinstance(s, dict) and s.get("priority") == selected
                ]
                if not filtered:
                    continue
                with st.expander(f"**{cat}** ({len(filtered)} risks)", expanded=False):
                    for s in filtered:
                        if not isinstance(s, dict):
                            continue
                        p = s.get("priority", "Medium")
                        color = PRIORITY_COLORS.get(p, "#6b7280")
                        score = s.get("score", 5.0)
                        st.markdown(
                            f'''
                            <div style="border-left:3px solid {color};
                                 padding:0.4rem 0.8rem; margin-bottom:0.4rem;
                                 background:#fafafa; border-radius:0 6px 6px 0;">
                                <div style="display:flex; justify-content:space-between; align-items:center;">
                                    <span style="font-size:0.85rem; color:#111827;">
                                        {s.get("title","")[:150]}
                                    </span>
                                    <span style="white-space:nowrap; margin-left:0.5rem;">
                                        {_badge(p, color)}
                                        <span style="font-size:0.72rem; color:#9ca3af; margin-left:4px;">
                                            {score}
                                        </span>
                                    </span>
                                </div>
                                <p style="margin:0.15rem 0 0 0; font-size:0.75rem; color:#9ca3af;">
                                    {s.get("reasoning", "")}
                                </p>
                            </div>
                            ''',
                            unsafe_allow_html=True,
                        )

    # ── Agent trace (bottom) ────────────────────────────────────────────────
    steps = report.get("agent_steps", [])
    if steps:
        with st.expander("🔎 Agent execution trace", expanded=False):
            for s in steps:
                st.caption(f". {s}")

    # ── Download ──────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    dl_data = {k: v for k, v in report.items() if k != "enriched_risks"}
    dl_data["prioritized_risks"] = enriched_risks
    st.download_button(
        "📥 Download Full Agent Report (JSON)",
        data=json.dumps(dl_data, indent=2, ensure_ascii=False),
        file_name=f"{company}_{year}_agent_report.json".replace(" ", "_"),
        mime="application/json",
        key="dl_agent_report",
        use_container_width=True,
    )
