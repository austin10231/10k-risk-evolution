"""Reusable financial tables viewer UI for Tables/Library pages."""

from __future__ import annotations

import csv
import io
import json

import streamlit as st

from core.table_extractor import TABLE_CATEGORIES

DISPLAY_ORDER = [
    "income_statement",
    "comprehensive_income",
    "balance_sheet",
    "shareholders_equity",
    "cash_flow",
]

TABLE_ICONS = {
    "income_statement": "📈",
    "comprehensive_income": "📊",
    "balance_sheet": "⚖️",
    "shareholders_equity": "🏦",
    "cash_flow": "💵",
}


def classified_to_csv(data: dict) -> str:
    """Convert classified table payload to CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    for cat_key in DISPLAY_ORDER:
        cat_data = data.get(cat_key, {})
        if not cat_data.get("found"):
            continue
        name = cat_data.get("display_name", cat_key)
        unit = cat_data.get("unit", "")
        writer.writerow([f"=== {name} ==="])
        if unit:
            writer.writerow([f"({unit})"])
        writer.writerow([])
        headers = cat_data.get("headers", [])
        if headers:
            writer.writerow(headers)
        for row in cat_data.get("rows", []):
            writer.writerow(row)
        writer.writerow([])
        writer.writerow([])
    return output.getvalue()


def count_found_tables(data: dict) -> int:
    return sum(1 for k in DISPLAY_ORDER if data.get(k, {}).get("found"))


def render_table_output(result: dict, key_prefix: str, show_json_preview: bool = True) -> None:
    """Render extracted financial tables payload."""
    found = int(result.get("tables_found", 0) or 0)
    company = result.get("company", "—")
    year = result.get("year", "—")
    filing_type = result.get("filing_type", "—")

    m1, m2, m3, m4 = st.columns(4)
    for col, label, value, color in [
        (m1, "COMPANY", company, "#1e40af"),
        (m2, "YEAR", str(year), "#1e40af"),
        (m3, "TABLES FOUND", f"{found}/5", "#16a34a" if found == 5 else "#d97706"),
        (m4, "FILING TYPE", filing_type, "#1e40af"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<p class="metric-label">{label}</p>'
                f'<p class="metric-value" style="color:{color}; font-size:1rem;">{value}</p>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Download JSON",
            data=json.dumps(result, indent=2, ensure_ascii=False),
            file_name=f"{company}_{year}_tables.json",
            mime="application/json",
            key=f"dl_json_{key_prefix}",
            use_container_width=True,
        )
    with dl2:
        csv_data = classified_to_csv(result)
        st.download_button(
            "📥 Download CSV",
            data=csv_data,
            file_name=f"{company}_{year}_tables.csv",
            mime="text/csv",
            key=f"dl_csv_{key_prefix}",
            use_container_width=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.6rem;">EXTRACTED TABLES</p>',
        unsafe_allow_html=True,
    )

    for cat_key in DISPLAY_ORDER:
        cat_data = result.get(cat_key, {})
        found_flag = cat_data.get("found", False)
        name = cat_data.get("display_name", TABLE_CATEGORIES.get(cat_key, {}).get("display_name", cat_key))
        icon = TABLE_ICONS.get(cat_key, "📋")

        if not found_flag:
            st.markdown(
                f'<div style="padding:0.5rem 0.9rem; background:#f8fafc; border:1px solid #e2e8f0;'
                f'border-radius:8px; margin-bottom:0.4rem; font-size:0.81rem; color:#94a3b8;'
                f'display:flex; align-items:center; gap:6px;">'
                f'{icon} <span style="color:#64748b; font-weight:500;">{name}</span>'
                f'<span style="color:#cbd5e1;">—</span> <em>not found</em></div>',
                unsafe_allow_html=True,
            )
            continue

        unit = cat_data.get("unit", "")
        headers = cat_data.get("headers", [])
        rows = cat_data.get("rows", [])

        with st.expander(f"{icon} **{name}**", expanded=False):
            if unit:
                st.caption(f"Unit: {unit}")
            if headers and rows:
                try:
                    df_data = []
                    for row in rows:
                        row_dict = {}
                        for ci, val in enumerate(row):
                            col_name = headers[ci] if ci < len(headers) else f"Col {ci + 1}"
                            row_dict[col_name] = val
                        df_data.append(row_dict)
                    st.dataframe(df_data, use_container_width=True, hide_index=True)
                except Exception:
                    st.table([headers] + rows)
            elif rows:
                st.table(rows)
            else:
                st.info("Table found but no data rows extracted.")

    if show_json_preview:
        with st.expander("📄 Full JSON Preview", expanded=False):
            st.json(result)
