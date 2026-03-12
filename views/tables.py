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

DISPLAY_ORDER = [
    "income_statement",
    "comprehensive_income",
    "balance_sheet",
    "shareholders_equity",
    "cash_flow",
]


def _classified_to_csv(result):
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


def _count_found(result):
    return sum(1 for k in DISPLAY_ORDER if result.get(k, {}).get("found"))


def render():
    st.markdown(
        '''
        <div style="margin-bottom:1rem;">
            <p style="font-size:1rem; font-weight:700; color:#1e40af; margin:0 0 0.2rem 0;">
                📊 Financial Statement Extraction
            </p>
            <p style="font-size:0.85rem; color:#6b7280; margin:0;">
                Upload a 10-K PDF to extract five core financial statements using AWS Textract analysis.
                The pipeline locates Item 8 and extracts tables with complete headers and row data.
            </p>
        </div>
        ''',
        unsafe_allow_html=True,
    )

    col_input, col_output = st.columns([2, 3])

    with col_input:
        st.markdown(
            '''
            <div style="background:#ffffff; border:1px solid #e0e3e8; border-radius:12px;
                 padding:1rem 1.2rem; margin-bottom:1rem;">
                <p style="font-size:0.85rem; font-weight:700; color:#1e40af; margin:0 0 0.3rem 0;">
                    Extraction Inputs
                </p>
                <p style="font-size:0.8rem; color:#6b7280; margin:0;">
                    Upload a 10-K PDF and provide metadata.
                </p>
            </div>
            ''',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader("Upload 10-K PDF", type=["pdf"], key="tbl_upload")
        year = st.selectbox("Filing Year", list(range(2025, 2009, -1)), key="tbl_year")
        company = st.text_input("Company Name", key="tbl_company")
        industry = st.selectbox("Industry", INDUSTRIES, key="tbl_industry")
        filing_type = st.selectbox(
            "Filing Type", ["10-K", "10-Q (coming soon)"], key="tbl_ftype",
        )
        run = st.button(
            "Extract Tables",
            key="btn_extract_tables", use_container_width=True,
        )
        st.caption(
            "Extracts Income Statement, Comprehensive Income, "
            "Balance Sheet, Shareholders' Equity, and Cash Flows."
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

        with st.spinner("Locating Item 8 & extracting tables via AWS Textract …"):
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


def _show_table_output(result, key):
    found = result.get("tables_found", 0)
    company = result.get("company", "—")
    year = result.get("year", "—")
    filing_type = result.get("filing_type", "—")

    # ── Summary strip ────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="display:grid; grid-template-columns:repeat(4,1fr);
             gap:0.6rem; margin-bottom:1rem;">
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:12px; padding:0.8rem 1rem; text-align:center;">
                <p style="margin:0; font-size:0.65rem; font-weight:700; color:#9ca3af;
                   text-transform:uppercase; letter-spacing:0.06em;">Company</p>
                <p style="margin:0.2rem 0 0 0; font-size:1.2rem; font-weight:800;
                   color:#1e40af;">{company}</p>
            </div>
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:12px; padding:0.8rem 1rem; text-align:center;">
                <p style="margin:0; font-size:0.65rem; font-weight:700; color:#9ca3af;
                   text-transform:uppercase; letter-spacing:0.06em;">Year</p>
                <p style="margin:0.2rem 0 0 0; font-size:1.2rem; font-weight:800;
                   color:#1e40af;">{year}</p>
            </div>
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:12px; padding:0.8rem 1rem; text-align:center;">
                <p style="margin:0; font-size:0.65rem; font-weight:700; color:#9ca3af;
                   text-transform:uppercase; letter-spacing:0.06em;">Tables</p>
                <p style="margin:0.2rem 0 0 0; font-size:1.2rem; font-weight:800;
                   color:#1e40af;">{found}/5</p>
            </div>
            <div style="background:#ffffff; border:1.5px solid #e0e3e8;
                 border-radius:12px; padding:0.8rem 1rem; text-align:center;">
                <p style="margin:0; font-size:0.65rem; font-weight:700; color:#9ca3af;
                   text-transform:uppercase; letter-spacing:0.06em;">Filing</p>
                <p style="margin:0.2rem 0 0 0; font-size:1.2rem; font-weight:800;
                   color:#1e40af;">{filing_type}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Download buttons ─────────────────────────────────────────────────────
    dl1, dl2 = st.columns(2)
    with dl1:
        st.download_button(
            "Download JSON",
            data=json.dumps(result, indent=2, ensure_ascii=False),
            file_name=f"{company}_{year}_tables.json",
            mime="application/json",
            key=f"dl_json_{key}",
            use_container_width=True,
        )
    with dl2:
        classified_only = {k: result.get(k, {"found": False}) for k in DISPLAY_ORDER}
        csv_data = _classified_to_csv(classified_only)
        st.download_button(
            "Download CSV",
            data=csv_data,
            file_name=f"{company}_{year}_tables.csv",
            mime="text/csv",
            key=f"dl_csv_{key}",
            use_container_width=True,
        )

    # ── Tables (collapsed by default) ────────────────────────────────────────
    for cat_key in DISPLAY_ORDER:
        cat_data = result.get(cat_key, {})
        found_flag = cat_data.get("found", False)
        name = cat_data.get("display_name", TABLE_CATEGORIES.get(cat_key, {}).get("display_name", cat_key))

        if not found_flag:
            st.markdown(f"❌ **{name}** — *not found*")
            continue

        unit = cat_data.get("unit", "")
        headers = cat_data.get("headers", [])
        rows = cat_data.get("rows", [])

        with st.expander(f"**{name}**", expanded=False):
            if unit:
                st.caption(f"Unit: {unit}")
            if headers and rows:
                try:
                    df_data = []
                    for row in rows:
                        row_dict = {}
                        for ci, val in enumerate(row):
                            col_name = headers[ci] if ci < len(headers) else f"Col {ci+1}"
                            row_dict[col_name] = val
                        df_data.append(row_dict)
                    st.dataframe(df_data, use_container_width=True, hide_index=True)
                except Exception:
                    st.table([headers] + rows)
            elif rows:
                st.table(rows)
            else:
                st.info("Table found but no data rows extracted.")

    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)
