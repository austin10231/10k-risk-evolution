"""Tables page — Extract & classify financial tables from PDF via Textract."""

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

CATEGORY_LABELS = {
    "income_statement": "📈 Income Statement / Statement of Operations",
    "balance_sheet": "📊 Balance Sheet / Financial Position",
    "cash_flow": "💰 Cash Flow Statement",
    "shareholders_equity": "🏦 Shareholders' Equity",
    "segment_revenue": "🌍 Segment Revenue / Information",
    "debt_maturity": "📅 Debt Maturity / Contractual Obligations",
}


def _classified_to_csv(classified: dict) -> str:
    """Convert classified tables to CSV."""
    output = io.StringIO()
    writer = csv.writer(output)

    for cat_key, label in CATEGORY_LABELS.items():
        cat_data = classified.get(cat_key, {})
        if not cat_data.get("found"):
            continue

        for tbl in cat_data.get("tables", []):
            writer.writerow([f"=== {label} ==="])
            writer.writerow([f"Page: {tbl.get('page', '?')} | Confidence: {tbl.get('confidence', 0):.1%}"])
            for row in tbl.get("rows", []):
                writer.writerow(row)
            writer.writerow([])

    return output.getvalue()


def _count_found(classified: dict) -> int:
    return sum(1 for v in classified.values() if isinstance(v, dict) and v.get("found"))


def render():
    st.markdown(
        "Upload a **10-K PDF** to extract core financial statement tables "
        "using AWS Textract. Tables are automatically classified into 6 categories."
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
            "Textract extracts all tables, then classifies them into: "
            "Income Statement, Balance Sheet, Cash Flows, "
            "Shareholders' Equity, Segment Revenue, Debt Maturity."
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

        with st.spinner("Extracting & classifying tables via AWS Textract (1-2 minutes) …"):
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
    """Display classified tables."""
    found = result.get("tables_found", 0)

    st.markdown(
        f"**{result.get('company', '—')}** · {result.get('year', '—')} · "
        f"**{found}/6** financial tables identified"
    )

    # ── Download buttons ──────────────────────────────────────────────
    # Build classified-only dict for downloads
    classified_only = {
        cat: result.get(cat, {"found": False, "tables": []})
        for cat in CATEGORY_LABELS
    }

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
        csv_data = _classified_to_csv(classified_only)
        st.download_button(
            "📥 Download CSV",
            data=csv_data,
            file_name=f"{result.get('company','tables')}_{result.get('year','')}_tables.csv",
            mime="text/csv",
            key=f"dl_csv_{key}",
            use_container_width=True,
        )

    # ── Display each category ─────────────────────────────────────────
    for cat_key, label in CATEGORY_LABELS.items():
        cat_data = result.get(cat_key, {})
        found = cat_data.get("found", False)

        if found:
            tables = cat_data.get("tables", [])
            for ti, tbl in enumerate(tables):
                conf = tbl.get("confidence", 0)
                title = tbl.get("title", label)
                rows = tbl.get("rows", [])
                conf_pct = f"{conf:.0%}"

                with st.expander(
                    f"✅ {label} — {conf_pct} confidence ({len(rows)} rows)",
                    expanded=False,
                ):
                    if rows and len(rows) > 1:
                        try:
                            headers = rows[0]
                            data_rows = rows[1:]
                            st.dataframe(
                                data=[dict(zip(headers, r)) for r in data_rows],
                                use_container_width=True,
                            )
                        except Exception:
                            st.table(rows)
                    elif rows:
                        st.table(rows)
        else:
            st.markdown(f"❌ {label} — *not found*")

    # ── Full JSON ─────────────────────────────────────────────────────
    with st.expander("📄 Full JSON Preview", expanded=False):
        st.json(result)
