"""
Extract financial tables from PDF using AWS Textract async API.

Uses StartDocumentAnalysis with FeatureTypes=["TABLES"]
to detect and parse tabular data from multi-page 10-K PDFs.
"""

import time
import uuid
import re
import streamlit as st
import boto3


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


def extract_tables_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Extract tables from a multi-page PDF using Textract async API.

    Returns:
    [
      {
        "table_index": 0,
        "page": 1,
        "title": "Table on page 1",
        "rows": [
          ["Header1", "Header2", "Header3"],
          ["val1", "val2", "val3"],
          ...
        ]
      },
      ...
    ]
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
                "S3Object": {
                    "Bucket": bucket,
                    "Name": temp_key,
                }
            },
            FeatureTypes=["TABLES"],
        )
        job_id = response["JobId"]

        # 3. Poll until complete
        max_wait = 180  # 3 minutes for large docs
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
            return []

        # 4. Collect ALL blocks from all pages
        all_blocks = result.get("Blocks", [])
        next_token = result.get("NextToken")

        while next_token:
            result = textract.get_document_analysis(
                JobId=job_id, NextToken=next_token,
            )
            all_blocks.extend(result.get("Blocks", []))
            next_token = result.get("NextToken")

        # 5. Parse blocks into table structures
        return _parse_tables(all_blocks)

    finally:
        try:
            s3.delete_object(Bucket=bucket, Key=temp_key)
        except Exception:
            pass


def _parse_tables(blocks: list[dict]) -> list[dict]:
    """Parse Textract blocks into structured table data."""

    # Build block index
    block_map: dict[str, dict] = {}
    for b in blocks:
        block_map[b["Id"]] = b

    # Find TABLE blocks
    table_blocks = [b for b in blocks if b["BlockType"] == "TABLE"]

    tables = []
    for ti, tb in enumerate(table_blocks):
        page = tb.get("Page", 1)

        # Get all CELL blocks for this table
        cell_ids = []
        for rel in tb.get("Relationships", []):
            if rel["Type"] == "CHILD":
                cell_ids.extend(rel["Ids"])

        # Parse cells into (row, col) → text
        cell_map: dict[tuple[int, int], str] = {}
        max_row = 0
        max_col = 0

        for cid in cell_ids:
            cell = block_map.get(cid)
            if cell is None or cell["BlockType"] != "CELL":
                continue

            row_idx = cell.get("RowIndex", 1)
            col_idx = cell.get("ColumnIndex", 1)
            max_row = max(max_row, row_idx)
            max_col = max(max_col, col_idx)

            # Get text from WORD/SELECTION_ELEMENT children
            text = _get_cell_text(cell, block_map)
            cell_map[(row_idx, col_idx)] = text

        # Build rows
        rows = []
        for r in range(1, max_row + 1):
            row = []
            for c in range(1, max_col + 1):
                row.append(cell_map.get((r, c), ""))
            rows.append(row)

        # Generate title from first row or page number
        title = _guess_table_title(rows, page, ti)

        # Skip very small tables (likely not financial data)
        if max_row < 2 or max_col < 2:
            continue

        tables.append({
            "table_index": ti,
            "page": page,
            "title": title,
            "row_count": max_row,
            "col_count": max_col,
            "rows": rows,
        })

    return tables


def _get_cell_text(cell: dict, block_map: dict) -> str:
    """Extract text content from a CELL block."""
    words = []
    for rel in cell.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for wid in rel["Ids"]:
                word = block_map.get(wid)
                if word and word["BlockType"] == "WORD":
                    words.append(word.get("Text", ""))
    return " ".join(words).strip()


def _guess_table_title(rows: list[list[str]], page: int, table_index: int) -> str:
    """Try to guess a meaningful title for the table."""
    if not rows:
        return f"Table {table_index + 1} (page {page})"

    # Check first row for common financial statement headers
    first_row_text = " ".join(rows[0]).upper()

    keywords = {
        "OPERATIONS": "Consolidated Statements of Operations",
        "INCOME": "Consolidated Statements of Income",
        "BALANCE SHEET": "Consolidated Balance Sheets",
        "FINANCIAL POSITION": "Consolidated Statements of Financial Position",
        "CASH FLOW": "Consolidated Statements of Cash Flows",
        "EQUITY": "Consolidated Statements of Shareholders' Equity",
        "COMPREHENSIVE": "Consolidated Statements of Comprehensive Income",
    }

    for kw, title in keywords.items():
        if kw in first_row_text:
            return title

    # Check if any cell in first 2 rows has a recognizable pattern
    for r in rows[:2]:
        for cell in r:
            upper = cell.upper()
            for kw, title in keywords.items():
                if kw in upper:
                    return title

    return f"Table {table_index + 1} (page {page})"
