"""
Extract and classify financial tables from PDF using AWS Textract.

Two-phase approach:
  Phase 1: Extract ALL tables via Textract StartDocumentAnalysis(TABLES)
  Phase 2: Classify & filter into 6 core financial statement categories

Output format:
{
  "income_statement":      { "found": bool, "tables": [...] },
  "balance_sheet":         { "found": bool, "tables": [...] },
  "cash_flow":             { "found": bool, "tables": [...] },
  "shareholders_equity":   { "found": bool, "tables": [...] },
  "segment_revenue":       { "found": bool, "tables": [...] },
  "debt_maturity":         { "found": bool, "tables": [...] },
}
"""

import time
import uuid
import re
import streamlit as st
import boto3


# ══════════════════════════════════════════════════════════════════════════════
#  CLASSIFICATION KEYWORD DICTIONARIES
# ══════════════════════════════════════════════════════════════════════════════

# Each category: list of (keyword_group, weight)
# Higher weight = stronger signal. Final score = sum of matched weights.

CATEGORY_KEYWORDS = {
    "income_statement": [
        # Primary identifiers
        ("statement of operations", 5.0),
        ("statements of operations", 5.0),
        ("income statement", 5.0),
        ("statements of income", 5.0),
        ("statement of income", 5.0),
        ("statement of earnings", 5.0),
        ("results of operations", 4.0),
        ("profit and loss", 4.0),
        # Column/row keywords (secondary)
        ("net sales", 2.0),
        ("net revenue", 2.0),
        ("total net sales", 2.0),
        ("cost of sales", 2.0),
        ("cost of goods sold", 2.0),
        ("gross margin", 2.0),
        ("gross profit", 2.0),
        ("operating income", 1.5),
        ("operating expenses", 1.5),
        ("earnings per share", 2.0),
        ("diluted earnings", 1.5),
        ("income tax", 1.0),
        ("net income", 1.5),
        ("income before", 1.0),
    ],
    "balance_sheet": [
        ("balance sheet", 5.0),
        ("balance sheets", 5.0),
        ("statement of financial position", 5.0),
        ("statements of financial position", 5.0),
        ("financial position", 4.0),
        # Row keywords
        ("total assets", 3.0),
        ("total liabilities", 3.0),
        ("current assets", 2.0),
        ("current liabilities", 2.0),
        ("stockholders equity", 2.5),
        ("shareholders equity", 2.5),
        ("accounts receivable", 1.5),
        ("accounts payable", 1.5),
        ("retained earnings", 1.5),
        ("goodwill", 1.0),
        ("total equity", 2.0),
        ("property plant and equipment", 1.5),
    ],
    "cash_flow": [
        ("statement of cash flows", 5.0),
        ("statements of cash flows", 5.0),
        ("cash flow statement", 5.0),
        ("cash flows", 4.0),
        # Row keywords
        ("operating activities", 3.0),
        ("investing activities", 3.0),
        ("financing activities", 3.0),
        ("cash and cash equivalents", 2.0),
        ("depreciation and amortization", 1.5),
        ("capital expenditures", 1.5),
        ("purchase of property", 1.0),
        ("repurchase of common stock", 1.0),
        ("dividends paid", 1.0),
        ("net cash", 2.0),
        ("free cash flow", 2.0),
    ],
    "shareholders_equity": [
        ("shareholders equity", 5.0),
        ("stockholders equity", 5.0),
        ("statement of equity", 5.0),
        ("statements of equity", 5.0),
        ("changes in equity", 4.0),
        ("changes in stockholders", 4.0),
        ("changes in shareholders", 4.0),
        # Column/row keywords
        ("common stock", 2.0),
        ("additional paid-in capital", 2.0),
        ("accumulated other comprehensive", 2.5),
        ("retained earnings", 1.5),
        ("treasury stock", 2.0),
        ("total stockholders", 2.0),
        ("total shareholders", 2.0),
        ("share repurchase", 1.0),
        ("dividends declared", 1.0),
    ],
    "segment_revenue": [
        ("segment information", 5.0),
        ("segment reporting", 5.0),
        ("segment revenue", 5.0),
        ("reportable segments", 4.0),
        ("operating segments", 4.0),
        ("business segments", 4.0),
        ("products and services", 3.0),
        ("revenue by product", 3.0),
        ("revenue by segment", 3.0),
        ("revenue by geography", 3.0),
        ("geographic information", 3.0),
        ("net sales by product", 3.0),
        ("net sales by reportable segment", 3.0),
        ("americas", 1.5),
        ("europe", 1.0),
        ("asia", 1.0),
        ("greater china", 1.5),
    ],
    "debt_maturity": [
        ("debt maturity", 5.0),
        ("debt schedule", 5.0),
        ("contractual obligations", 5.0),
        ("long-term debt", 4.0),
        ("long term debt", 4.0),
        ("term debt", 3.0),
        ("commercial paper", 2.5),
        ("notes payable", 2.0),
        ("bonds payable", 2.0),
        ("maturity date", 3.0),
        ("maturities of", 3.0),
        ("principal amount", 2.0),
        ("interest rate", 1.5),
        ("fixed rate", 1.5),
        ("floating rate", 1.5),
        ("due date", 2.0),
        ("2025", 0.5),
        ("2026", 0.5),
        ("2027", 0.5),
    ],
}

# Minimum score to consider a table as a candidate for a category
MIN_SCORE_THRESHOLD = 4.0


# ══════════════════════════════════════════════════════════════════════════════
#  AWS CLIENTS
# ══════════════════════════════════════════════════════════════════════════════

def _get_textract():
    return boto3.client(
        "textract",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )


def _get_s3():
    return boto3.client(
        "s3",
        aws_access_key_id=st.secrets["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=st.secrets["AWS_SECRET_ACCESS_KEY"],
        region_name=st.secrets["AWS_REGION"],
    )


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 1: TEXTRACT TABLE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_tables_from_pdf(pdf_bytes: bytes) -> dict:
    """
    Extract and classify financial tables from a PDF.

    Returns classified dict with 6 categories.
    """
    bucket = st.secrets["S3_BUCKET"]
    temp_key = f"_textract_temp/{uuid.uuid4().hex}.pdf"

    s3 = _get_s3()
    textract = _get_textract()

    try:
        # 1. Upload PDF to S3
        s3.put_object(Bucket=bucket, Key=temp_key, Body=pdf_bytes)

        # 2. Start async analysis with TABLES
        response = textract.start_document_analysis(
            DocumentLocation={
                "S3Object": {"Bucket": bucket, "Name": temp_key}
            },
            FeatureTypes=["TABLES"],
        )
        job_id = response["JobId"]

        # 3. Poll until complete
        max_wait = 180
        waited = 0
        status = ""
        while waited < max_wait:
            result = textract.get_document_analysis(JobId=job_id)
            status = result["JobStatus"]
            if status in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(4)
            waited += 4

        if status != "SUCCEEDED":
            return _empty_result()

        # 4. Collect ALL blocks
        all_blocks = result.get("Blocks", [])
        next_token = result.get("NextToken")
        while next_token:
            result = textract.get_document_analysis(
                JobId=job_id, NextToken=next_token,
            )
            all_blocks.extend(result.get("Blocks", []))
            next_token = result.get("NextToken")

        # 5. Parse all raw tables
        raw_tables = _parse_all_tables(all_blocks)

        if not raw_tables:
            return _empty_result()

        # 6. Phase 2: Classify & filter
        return _classify_tables(raw_tables, all_blocks)

    finally:
        try:
            s3.delete_object(Bucket=bucket, Key=temp_key)
        except Exception:
            pass


def _empty_result() -> dict:
    """Return empty classified result."""
    return {
        cat: {"found": False, "tables": []}
        for cat in CATEGORY_KEYWORDS
    }


def _parse_all_tables(blocks: list[dict]) -> list[dict]:
    """Parse Textract blocks into raw table structures."""
    block_map = {b["Id"]: b for b in blocks}
    table_blocks = [b for b in blocks if b["BlockType"] == "TABLE"]

    tables = []
    for ti, tb in enumerate(table_blocks):
        page = tb.get("Page", 1)

        # Get CELL children
        cell_ids = []
        for rel in tb.get("Relationships", []):
            if rel["Type"] == "CHILD":
                cell_ids.extend(rel["Ids"])

        # Parse cells
        cell_map: dict[tuple[int, int], str] = {}
        max_row, max_col = 0, 0

        for cid in cell_ids:
            cell = block_map.get(cid)
            if cell is None or cell["BlockType"] != "CELL":
                continue
            ri = cell.get("RowIndex", 1)
            ci = cell.get("ColumnIndex", 1)
            max_row = max(max_row, ri)
            max_col = max(max_col, ci)
            cell_map[(ri, ci)] = _get_cell_text(cell, block_map)

        # Build rows
        rows = []
        for r in range(1, max_row + 1):
            row = [cell_map.get((r, c), "") for c in range(1, max_col + 1)]
            rows.append(row)

        # Skip tiny tables
        if max_row < 2 or max_col < 2:
            continue

        # Collect all text in the table for classification
        all_text = " ".join(
            cell_map.get((r, c), "")
            for r in range(1, max_row + 1)
            for c in range(1, max_col + 1)
        ).lower()

        tables.append({
            "table_index": ti,
            "page": page,
            "row_count": max_row,
            "col_count": max_col,
            "rows": rows,
            "all_text": all_text,
        })

    return tables


def _get_cell_text(cell: dict, block_map: dict) -> str:
    words = []
    for rel in cell.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for wid in rel["Ids"]:
                word = block_map.get(wid)
                if word and word["BlockType"] == "WORD":
                    words.append(word.get("Text", ""))
    return " ".join(words).strip()


# ══════════════════════════════════════════════════════════════════════════════
#  PHASE 2: CLASSIFICATION & FILTERING
# ══════════════════════════════════════════════════════════════════════════════

def _get_nearby_text(table: dict, all_blocks: list[dict], window: int = 5) -> str:
    """Get LINE text from nearby blocks (before the table on same page)."""
    page = table["page"]
    table_idx = table["table_index"]

    # Collect LINE blocks on same page
    page_lines = [
        b for b in all_blocks
        if b["BlockType"] == "LINE" and b.get("Page", 1) == page
    ]

    # Return last N lines before the table as context
    texts = [b.get("Text", "") for b in page_lines[:window * 2]]
    return " ".join(texts).lower()


def _score_table(table: dict, category: str, nearby_text: str) -> float:
    """Score how well a table matches a category."""
    keywords = CATEGORY_KEYWORDS[category]
    combined_text = table["all_text"] + " " + nearby_text

    score = 0.0
    for kw, weight in keywords:
        if kw.lower() in combined_text:
            score += weight

    # Bonus for table size (financial statements tend to be larger)
    if category in ("income_statement", "balance_sheet", "cash_flow", "shareholders_equity"):
        if table["row_count"] >= 10:
            score += 1.0
        if table["row_count"] >= 20:
            score += 1.0

    return score


def _classify_tables(raw_tables: list[dict], all_blocks: list[dict]) -> dict:
    """Classify tables into 6 categories. Keep top 1-2 per category."""

    # Pre-compute nearby text for each table
    for t in raw_tables:
        t["nearby_text"] = _get_nearby_text(t, all_blocks)

    result = {cat: {"found": False, "tables": []} for cat in CATEGORY_KEYWORDS}

    # Score every table for every category
    category_candidates: dict[str, list[tuple[float, dict]]] = {
        cat: [] for cat in CATEGORY_KEYWORDS
    }

    for t in raw_tables:
        for cat in CATEGORY_KEYWORDS:
            score = _score_table(t, cat, t["nearby_text"])
            if score >= MIN_SCORE_THRESHOLD:
                confidence = min(score / 15.0, 1.0)  # normalize to 0-1
                category_candidates[cat].append((confidence, t))

    # For each category, pick top 1-2 tables (highest confidence)
    # Also track which tables are already assigned to avoid duplicates
    assigned_tables: set[int] = set()

    # Process categories in priority order (big 4 first)
    priority_order = [
        "income_statement", "balance_sheet", "cash_flow",
        "shareholders_equity", "segment_revenue", "debt_maturity",
    ]

    for cat in priority_order:
        candidates = category_candidates[cat]
        # Sort by confidence descending
        candidates.sort(key=lambda x: -x[0])

        selected = []
        for conf, tbl in candidates:
            if tbl["table_index"] in assigned_tables:
                continue
            selected.append((conf, tbl))
            assigned_tables.add(tbl["table_index"])
            if len(selected) >= 2:
                break

        if selected:
            result[cat]["found"] = True
            result[cat]["tables"] = [
                {
                    "page": tbl["page"],
                    "title": _generate_title(cat, tbl),
                    "confidence": round(conf, 3),
                    "row_count": tbl["row_count"],
                    "col_count": tbl["col_count"],
                    "rows": tbl["rows"],
                }
                for conf, tbl in selected
            ]

    return result


def _generate_title(category: str, table: dict) -> str:
    """Generate a human-readable title for a classified table."""
    titles = {
        "income_statement": "Consolidated Statements of Operations",
        "balance_sheet": "Consolidated Balance Sheets",
        "cash_flow": "Consolidated Statements of Cash Flows",
        "shareholders_equity": "Consolidated Statements of Shareholders' Equity",
        "segment_revenue": "Segment Information / Revenue Breakdown",
        "debt_maturity": "Debt Maturity Schedule / Contractual Obligations",
    }
    base = titles.get(category, category)
    return f"{base} (page {table['page']})"
