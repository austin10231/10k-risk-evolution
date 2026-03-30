"""Dashboard page — Risk heatmap and category ranking visualizations."""

import streamlit as st
import plotly.graph_objects as go

from storage.store import load_index, get_result, load_agent_reports
from core.bedrock import RISK_CATEGORIES

try:
    # Keep industry options aligned with Upload page.
    from views.upload import INDUSTRIES as _UPLOAD_INDUSTRIES
except Exception:
    _UPLOAD_INDUSTRIES = [
        "Technology", "Healthcare", "Financials", "Energy",
        "Consumer Discretionary", "Consumer Staples", "Industrials",
        "Materials", "Utilities", "Real Estate", "Telecom", "Other",
    ]


# ── Color palette (matches app design system) ────────────────────────────────
_INDIGO = "#6366f1"
_DARK = "#0f172a"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"
_BG = "#ffffff"

# 5-level discrete heatmap: 0=no data, 1=Low, 2=Medium-Low, 3=Medium, 4=Medium-High, 5=High
_RISK_HEATMAP_SCALE = [
    [0.0, "#f1f5f9"],    # 0 — no data (light gray)
    [0.2, "#22c55e"],    # 1 — Low (green)
    [0.4, "#84cc16"],    # 2 — Medium-Low (light green)
    [0.6, "#f59e0b"],    # 3 — Medium (yellow/amber)
    [0.8, "#f97316"],    # 4 — Medium-High (orange)
    [1.0, "#ef4444"],    # 5 — High (red)
]

_LEVEL_NUM = {
    "Low": 1, "Medium-Low": 2, "Medium": 3, "Medium-High": 4, "High": 5,
}
_LEVEL_DISPLAY = {
    1: "Low", 2: "Medium-Low", 3: "Medium", 4: "Medium-High", 5: "High",
}
_LEVEL_ABBREV = {
    1: "L", 2: "ML", 3: "M", 4: "MH", 5: "H",
}

# Plotly layout defaults matching the app style
_LAYOUT_DEFAULTS = dict(
    font=dict(family="Inter, -apple-system, sans-serif", color=_DARK),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor=_BG,
    margin=dict(l=20, r=20, t=40, b=20),
)


def _load_all_results():
    """Load index + all result JSONs. Returns (index, {record_id: result})."""
    index = load_index()
    results = {}
    for rec in index:
        rid = rec["record_id"]
        res = get_result(rid)
        if res:
            results[rid] = res
    return index, results


def _count_sub_risks(result):
    """Count total sub-risk items in a result."""
    total = 0
    for cat in result.get("risks", []):
        total += len(cat.get("sub_risks", []))
    return total


def _build_agent_rating_map(agent_reports):
    """Build a {(company, year): overall_risk_rating} map from agent reports.
    If multiple reports exist for the same company/year, keep the latest."""
    ratings = {}
    for report in agent_reports:
        company = report.get("company", "")
        year = report.get("year")
        rating = report.get("overall_risk_rating", "")
        if company and year and rating in _LEVEL_NUM:
            ratings[(company, year)] = rating
    return ratings


def _extract_all_labels(results):
    """
    Extract risk label counts from all result JSONs in risk_analysis_results/.
    Handles both classified (dict sub_risks with 'labels') and
    unclassified (string sub_risks) formats.
    Returns dict of {label: count}.
    """
    label_counts = {}
    category_counts = {}

    for res in results.values():
        for cat_block in res.get("risks", []):
            cat_name = cat_block.get("category", "")
            subs = cat_block.get("sub_risks", [])

            for sub in subs:
                if isinstance(sub, dict):
                    # Classified sub-risk — extract AI labels
                    labels = sub.get("labels", [])
                    if labels:
                        for label in labels:
                            label_counts[label] = label_counts.get(label, 0) + 1
                    else:
                        # Classified but no labels — count under category
                        if cat_name:
                            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
                else:
                    # Unclassified string sub-risk — count under category
                    if cat_name:
                        category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

    # If we got AI labels, use those; merge in category counts for unclassified items
    if label_counts:
        for cat, cnt in category_counts.items():
            mapped = _map_category_to_label(cat)
            label_counts[mapped] = label_counts.get(mapped, 0) + cnt
        return label_counts

    # No AI labels at all — use category names mapped to standard labels
    if category_counts:
        mapped_counts = {}
        for cat, cnt in category_counts.items():
            mapped = _map_category_to_label(cat)
            mapped_counts[mapped] = mapped_counts.get(mapped, 0) + cnt
        return mapped_counts

    return {}


def _map_category_to_label(category_name):
    """
    Try to map a freeform category name to one of the standard RISK_CATEGORIES labels.
    Falls back to the original name if no match.
    """
    name_lower = category_name.lower()
    for label in RISK_CATEGORIES:
        if label in name_lower:
            return label
    keyword_map = {
        "cyber": "cybersecurity",
        "regulat": "regulatory",
        "legal": "litigation",
        "law": "litigation",
        "supply": "supply_chain",
        "geopolit": "geopolitical",
        "compet": "competition",
        "macro": "macroeconomic",
        "econom": "macroeconomic",
        "financ": "financial",
        "environ": "environmental",
        "climate": "environmental",
        "litigat": "litigation",
        "talent": "talent",
        "employ": "talent",
        "workforce": "talent",
        "techno": "technology",
        "innovat": "technology",
        "reputat": "reputational",
        "brand": "reputational",
        "operat": "operational",
    }
    for keyword, label in keyword_map.items():
        if keyword in name_lower:
            return label
    return category_name


def _industry_options(index):
    present = {str(r.get("industry", "")).strip() for r in index if str(r.get("industry", "")).strip()}
    ordered_known = [i for i in _UPLOAD_INDUSTRIES if i in present]
    extras = sorted(present - set(_UPLOAD_INDUSTRIES))
    return ["All Industries", *ordered_known, *extras]


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="page-header">
            <div class="page-header-left">
                <span class="page-icon">📈</span>
                <div>
                    <p class="page-title">Dashboard</p>
                    <p class="page-subtitle">Risk heatmap and category ranking across all filings</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading filing data…"):
        index, results = _load_all_results()
        agent_reports = load_agent_reports()

    if not index or not results:
        st.markdown(
            """
            <div class="empty-state">
                <p class="empty-state-icon">📈</p>
                <p class="empty-state-title">No filings to visualize</p>
                <p class="empty-state-sub">Upload at least one 10-K filing to see the dashboard.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("Go to Upload →", key="dash_to_upload", type="primary"):
            st.session_state["current_page"] = "upload"
            st.rerun()
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    companies = sorted(set(r["company"] for r in index))
    years = sorted(set(r["year"] for r in index))
    total_risks = sum(_count_sub_risks(r) for r in results.values())

    m1, m2, m3, m4 = st.columns(4)
    for col, label, value, color in [
        (m1, "COMPANIES", str(len(companies)), "#1e40af"),
        (m2, "YEARS COVERED", f"{min(years)}–{max(years)}" if years else "—", "#1e40af"),
        (m3, "TOTAL FILINGS", str(len(index)), _INDIGO),
        (m4, "TOTAL RISK ITEMS", str(total_risks), "#dc2626"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<p class="metric-label">{label}</p>'
                f'<p class="metric-value" style="color:{color};">{value}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ══════════════════════════════════════════════════════════════════════════
    #  1. Risk Heatmap — companies × years, colored by agent overall_risk_rating
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1rem;">
            <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                 border-radius:2px; flex-shrink:0;"></div>
            <div>
                <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                   letter-spacing:-0.02em; line-height:1.2;">Risk Heatmap</p>
                <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                    Overall risk level from Agent analysis — cells without an Agent report are grey
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Build agent rating map from S3-persisted agent reports
    agent_ratings = _build_agent_rating_map(agent_reports)

    # Build matrix
    company_list = sorted(companies)
    year_list = sorted(years)

    z_data = []
    hover_texts = []
    annotation_texts = []

    for company in company_list:
        row_z = []
        row_hover = []
        row_annot = []
        for year in year_list:
            rating = agent_ratings.get((company, year))
            if rating:
                level_num = _LEVEL_NUM.get(rating, 0)
                row_z.append(level_num)
                row_hover.append(
                    f"<b>{company}</b><br>Year: {year}<br>"
                    f"Risk level: <b>{rating}</b>"
                )
                row_annot.append(_LEVEL_ABBREV.get(level_num, ""))
            else:
                row_z.append(0)
                row_hover.append(
                    f"<b>{company}</b><br>Year: {year}<br>No Agent report"
                )
                row_annot.append("")
        z_data.append(row_z)
        hover_texts.append(row_hover)
        annotation_texts.append(row_annot)

    fig_heatmap = go.Figure(data=go.Heatmap(
        z=z_data,
        x=[str(y) for y in year_list],
        y=company_list,
        hovertext=hover_texts,
        hoverinfo="text",
        colorscale=_RISK_HEATMAP_SCALE,
        zmin=0,
        zmax=5,
        showscale=False,
        xgap=3,
        ygap=3,
    ))

    # Add text annotations on each cell
    for i, company in enumerate(company_list):
        for j, year in enumerate(year_list):
            text = annotation_texts[i][j]
            if text:
                fig_heatmap.add_annotation(
                    x=str(year), y=company,
                    text=text,
                    showarrow=False,
                    font=dict(size=11, color="white", family="Inter, sans-serif"),
                )

    heatmap_height = max(300, len(company_list) * 50 + 100)

    fig_heatmap.update_layout(
        **_LAYOUT_DEFAULTS,
        height=heatmap_height,
        xaxis=dict(
            title=dict(text="Filing Year", font=dict(size=11, color=_MUTED)),
            tickfont=dict(size=11, color=_DARK),
            side="bottom",
            gridcolor=_BORDER,
            dtick=1,
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=11, color=_DARK),
            autorange="reversed",
        ),
    )

    st.plotly_chart(fig_heatmap, use_container_width=True, key="dash_heatmap")

    # Legend
    st.markdown(
        '<div style="display:flex; gap:1.2rem; justify-content:center; flex-wrap:wrap; margin:-0.5rem 0 1.5rem;">'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#64748b;">'
        '<span style="width:14px; height:14px; background:#22c55e; border-radius:3px; display:inline-block;"></span>Low</span>'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#64748b;">'
        '<span style="width:14px; height:14px; background:#84cc16; border-radius:3px; display:inline-block;"></span>Medium-Low</span>'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#64748b;">'
        '<span style="width:14px; height:14px; background:#f59e0b; border-radius:3px; display:inline-block;"></span>Medium</span>'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#64748b;">'
        '<span style="width:14px; height:14px; background:#f97316; border-radius:3px; display:inline-block;"></span>Medium-High</span>'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#64748b;">'
        '<span style="width:14px; height:14px; background:#ef4444; border-radius:3px; display:inline-block;"></span>High</span>'
        '<span style="display:flex; align-items:center; gap:5px; font-size:0.75rem; color:#94a3b8;">'
        '<span style="width:14px; height:14px; background:#f1f5f9; border-radius:3px; border:1px solid #e2e8f0; display:inline-block;"></span>No Agent report</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ══════════════════════════════════════════════════════════════════════════
    #  2. Risk Category Ranking
    # ══════════════════════════════════════════════════════════════════════════
    industry_options = _industry_options(index)
    selected_industry = st.selectbox(
        "Industry Group",
        industry_options,
        key="dash_risk_rank_industry",
        help="Filter the risk category ranking by selected industry.",
    )

    ranking_scope = "all companies and years"
    if selected_industry != "All Industries":
        ranking_scope = f"{selected_industry} filings"

    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1rem;">
            <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                 border-radius:2px; flex-shrink:0;"></div>
            <div>
                <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                   letter-spacing:-0.02em; line-height:1.2;">Risk Category Ranking</p>
                <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                    Most frequent risk categories across {ranking_scope}
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if selected_industry == "All Industries":
        ranking_results = results
    else:
        scoped_ids = {r["record_id"] for r in index if r.get("industry") == selected_industry}
        ranking_results = {rid: res for rid, res in results.items() if rid in scoped_ids}

    label_counts = _extract_all_labels(ranking_results)

    if not label_counts:
        st.info("No risk category data available yet.")
        return

    # Sort descending, filter out "other" unless it's the only category
    sorted_labels = sorted(label_counts.items(), key=lambda x: x[1], reverse=True)
    if len(sorted_labels) > 1:
        sorted_labels = [(k, v) for k, v in sorted_labels if k.lower() != "other"]

    if not sorted_labels:
        st.info("No risk category data available yet.")
        return

    # Format label names for display
    categories = [item[0].replace("_", " ").title() for item in sorted_labels]
    counts = [item[1] for item in sorted_labels]

    # Color gradient: top items get deeper indigo
    max_count = max(counts) if counts else 1
    bar_colors = []
    for c in counts:
        ratio = c / max_count
        if ratio > 0.75:
            bar_colors.append("#4338ca")
        elif ratio > 0.5:
            bar_colors.append("#6366f1")
        elif ratio > 0.25:
            bar_colors.append("#818cf8")
        else:
            bar_colors.append("#a5b4fc")

    fig_bar = go.Figure(data=go.Bar(
        x=counts[::-1],
        y=categories[::-1],
        orientation="h",
        marker=dict(
            color=bar_colors[::-1],
            line=dict(width=0),
            cornerradius=4,
        ),
        hovertemplate="<b>%{y}</b><br>Occurrences: %{x}<extra></extra>",
    ))

    bar_height = max(350, len(categories) * 32 + 80)

    fig_bar.update_layout(
        **_LAYOUT_DEFAULTS,
        height=bar_height,
        xaxis=dict(
            title=dict(text="Number of Occurrences", font=dict(size=11, color=_MUTED)),
            tickfont=dict(size=10, color=_MUTED),
            gridcolor="#f1f5f9",
            zeroline=False,
        ),
        yaxis=dict(
            title="",
            tickfont=dict(size=11, color=_DARK),
            automargin=True,
        ),
        bargap=0.25,
    )

    st.plotly_chart(fig_bar, use_container_width=True, key="dash_bar")
