"""Tables page — Extract financial tables from PDF using AWS Textract."""

import streamlit as st
import json
import csv
import io

from core.table_extractor import extract_tables_from_pdf
from storage.store import save_table_result

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]


def _tables_to_csv(tables: list[dict]) -> str:
    """Convert all tables to a single CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    for t in tables:
        # Write table title as header row
        writer.writerow([f"=== {t.get('title', f'Table {t.get(\"table_index\", 0)}')} ==="])
        for row in t.get("rows", []):
            writer.writerow(row)
        writer.writerow([])  # blank row between tables

    return output.getvalue()


def render():
    st.markdown(
        "Upload a **10-K PDF** to extract financial statement tables "
        "using AWS Textract. Only PDF files are supported for table extraction."
    )

    col_input, col_output = st.columns([2, 3])

    with col_input:
        st.markdown("##### Inputs")
        uploaded = st.file_uploader(
            "Upload 10-K PDF",
            type=["pdf"],
            key="tbl_upload",
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
            "Textract identifies tables in the PDF and returns them as "
            "structured rows and columns. This may take 1-2 minutes for large filings."
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

        with st.spinner("Extracting tables via AWS Textract (this may take 1-2 minutes) …"):
            tables = extract_tables_from_pdf(pdf_bytes)

        if not tables:
            st.error("No tables found in this PDF.")
            return

        result = {
            "company": company.strip(),
            "industry": industry,
            "year": int(year),
            "filing_type": filing_type,
            "total_tables": len(tables),
            "tables": tables,
        }

        s3_key = save_table_result(
            company=company.strip(),
            year=int(year),
            filing_type=filing_type,
            table_json=result,
        )

        st.session_state["last_table_result"] = result
        st.session_state["last_table_rid"] = s3_key
        st.rerun()


def _show_table_output(result: dict, key: str):
    """Display extracted tables with download options."""
    tables = result.get("tables", [])

    st.markdown(
        f"**{result.get('company', '—')}** · {result.get('year', '—')} · "
        f"**{len(tables)}** tables extracted"
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
        csv_data = _tables_to_csv(tables)
        st.download_button(
            "📥 Download CSV",
            data=csv_data,
            file_name=f"{result.get('company','tables')}_{result.get('year','')}_tables.csv",
            mime="text/csv",
            key=f"dl_csv_{key}",
            use_container_width=True,
        )

    # ── Display each table ────────────────────────────────────────────
    for t in tables:
        title = t.get("title", f"Table {t.get('table_index', '?')}")
        rows = t.get("rows", [])

        with st.expander(f"📋 {title} ({len(rows)} rows)", expanded=False):
            if rows:
                # Show as dataframe for nice formatting
                try:
                    if len(rows) > 1:
                        st.dataframe(
                            data=[dict(zip(rows[0], r)) for r in rows[1:]],
                            use_container_width=True,
                        )
                    else:
                        st.table(rows)
                except Exception:
                    # Fallback: show as raw table
                    st.table(rows)

    # ── Full JSON preview ─────────────────────────────────────────────
    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)
