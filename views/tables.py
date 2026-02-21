"""Tables page — Extract 5 core financial tables from PDF via Textract."""

import streamlit as st
import json
import csv
import io

from core.table_extractor import extract_tables_from_pdf, TABLE_CATEGORIES
from storage.store import save_table_result

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]

# Display order
DISPLAY_ORDER = [
    "income_statement",
    "comprehensive_income",
    "balance_sheet",
    "shareholders_equity",
    "cash_flow",
]


def _classified_to_csv(result: dict) -> str:
    """Convert classified tables to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    for cat_key in DISPLAY_ORDER:
        cat_data = result.get(cat_key, {})
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


def _count_found(result: dict) -> int:
    return sum(
        1 for k in DISPLAY_ORDER
        if result.get(k, {}).get("found")
    )


def render():
    st.markdown(
        "Upload a **10-K PDF** to extract the 5 core financial statement tables "
        "using AWS Textract."
    )

    col_input, col_output = st.columns([2, 3])

    with col_input:
        st.markdown("##### Inputs")
        uploaded = st.file_uploader(
            "Upload 10-K PDF", type=["pdf"], key="tbl_upload",
        )
        year = st.selectbox(
            "Filing Year", list(range(2025, 2009, -1)), key="tbl_year",
        )
        company = st.text_input("Company Name", key="tbl_company")
        industry = st.selectbox("Industry", INDUSTRIES, key="tbl_industry")
        filing_type = st.selectbox(
            "Filing Type", ["10-K", "10-Q (coming soon)"], key="tbl_ftype",
        )
        run = st.button(
            "📊 Extract Tables", type="primary",
            key="btn_extract_tables", use_container_width=True,
        )
        st.caption(
            "PDF is auto-trimmed to Item 8 (Financial Statements) before extraction. "
            "Extracts: Income Statement, Comprehensive Income, "
            "Balance Sheet, Shareholders' Equity, Cash Flows."
        )

    with col_output:
        if "last_table_result" in st.session_state:
            _show_table_output(
                st.session_state["last_table_result"],
                key=f"tbl_{st.session_state.get('last_table_rid', 'x')}",
            )

    if run:
        if not company.strip():
            st.error("Please enter a company name.")
            return
        if uploaded is None:
            st.error("Please upload a PDF file.")
            return
        if "coming soon" in filing_type:
            st.warning("10-Q support is not yet available.")
            return

        pdf_bytes = uploaded.read()

        with st.spinner("Extracting tables via AWS Textract (1-2 minutes) …"):
            classified = extract_tables_from_pdf(pdf_bytes)

        found_count = _count_found(classified)
        if found_count == 0:
            st.error("No core financial tables could be identified in this PDF.")
            return

        result = {
            "company": company.strip(),
            "industry": industry,
            "year": int(year),
            "filing_type": filing_type,
            "tables_found": found_count,
            **classified,
        }

        csv_data = _classified_to_csv(classified)

        s3_key = save_table_result(
            company=company.strip(),
            year=int(year),
            filing_type=filing_type,
            table_json=result,
            csv_string=csv_data,
        )

        st.session_state["last_table_result"] = result
        st.session_state["last_table_rid"] = s3_key
        st.rerun()


def _show_table_output(result: dict, key: str):
    """Display classified financial tables."""
    found = result.get("tables_found", 0)

    st.markdown(
        f"**{result.get('company', '—')}** · {result.get('year', '—')} · "
        f"**{found}/5** financial tables identified"
    )

    # ── Download buttons ──────────────────────────────────────────────
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "📥 Download JSON",
            data=json.dumps(result, indent=2, ensure_ascii=False),
            file_name=f"{result.get('company','tables')}_{result.get('year','')}_tables.json",
            mime="application/json",
            key=f"dl_json_{key}",
            use_container_width=True,
        )
    with dl2:
        csv_data = _classified_to_csv(result)
        st.download_button(
            "📥 Download CSV",
            data=csv_data,
            file_name=f"{result.get('company','tables')}_{result.get('year','')}_tables.csv",
            mime="text/csv",
            key=f"dl_csv_{key}",
            use_container_width=True,
        )

    # ── Display each table category ───────────────────────────────────
    for cat_key in DISPLAY_ORDER:
        cat_data = result.get(cat_key, {})
        found = cat_data.get("found", False)
        name = cat_data.get("display_name", cat_key)

        if not found:
            st.markdown(f"❌ **{name}** — *not found*")
            continue

        page = cat_data.get("page", "?")
        unit = cat_data.get("unit", "")
        headers = cat_data.get("headers", [])
        rows = cat_data.get("rows", [])

        # Build expander label
        label = f"✅ {name}"

        with st.expander(label, expanded=False):
            # Title line
            st.markdown(f"**{name}**")
            if unit:
                st.caption(f"({unit})")
            st.caption(f"Page {page}")

            # Render table
            if headers and rows:
                try:
                    # Build dataframe-friendly dicts
                    df_data = []
                    for row in rows:
                        row_dict = {}
                        for ci, val in enumerate(row):
                            col_name = headers[ci] if ci < len(headers) else f"Col {ci+1}"
                            row_dict[col_name] = val
                        df_data.append(row_dict)
                    st.dataframe(df_data, use_container_width=True, hide_index=True)
                except Exception:
                    # Fallback
                    all_rows = [headers] + rows
                    st.table(all_rows)
            elif rows:
                st.table(rows)
            else:
                st.info("Table found but no data rows extracted.")

    # ── Full JSON preview ─────────────────────────────────────────────
    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)
