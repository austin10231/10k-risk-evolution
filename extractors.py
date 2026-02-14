# extractors.py
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

import pandas as pd

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None


# -----------------------------
# Utilities
# -----------------------------
def normalize_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def read_file_to_text(file_bytes: bytes, ext: str) -> str:
    ext = ext.lower()
    if ext in ("html", "htm"):
        if BeautifulSoup is None:
            raise RuntimeError("beautifulsoup4 not installed")
        soup = BeautifulSoup(file_bytes, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
        return normalize_text(text)

    if ext == "pdf":
        if pdfplumber is None:
            raise RuntimeError("pdfplumber not installed")
        parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
        return normalize_text("\n".join(parts))

    # txt fallback
    return normalize_text(file_bytes.decode("utf-8", errors="ignore"))


def extract_section(full_text: str, start_patterns: List[str], end_patterns: List[str], min_len: int = 200) -> str:
    t = full_text
    start_idx = None
    for pat in start_patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            start_idx = m.start()
            break
    if start_idx is None:
        return ""

    sub = t[start_idx:]
    end_idx = None
    for pat in end_patterns:
        m = re.search(pat, sub, flags=re.IGNORECASE)
        if m and m.start() > min_len:
            end_idx = m.start()
            break
    return normalize_text(sub[:end_idx] if end_idx else sub)


# -----------------------------
# Item 1 (Business) extraction
# -----------------------------
def extract_item1_business(full_text: str) -> str:
    """
    Extract Item 1. Business section (rough).
    """
    start = [r"\bItem\s*1\.*\s*Business\b", r"\bITEM\s*1\.*\s*BUSINESS\b"]
    end = [
        r"\bItem\s*1A\.*\s*Risk\s*Factors\b",
        r"\bITEM\s*1A\.*\s*RISK\s*FACTORS\b",
        r"\bItem\s*1B\.*\s*Unresolved\s*Staff\s*Comments\b",
    ]
    return extract_section(full_text, start, end, min_len=300)


def summarize_company_background(item1_text: str, max_chars: int = 1800) -> str:
    """
    MVP: take the early portion of Item 1 as "background" after skipping boilerplate.
    (Later you can replace with Bedrock summarization.)
    """
    if not item1_text:
        return ""
    # remove some very generic lines
    lines = [ln.strip() for ln in item1_text.splitlines() if ln.strip()]
    filtered = []
    for ln in lines:
        low = ln.lower()
        if "forward-looking" in low:
            continue
        filtered.append(ln)
    blob = " ".join(filtered)
    blob = re.sub(r"\s+", " ", blob).strip()
    return blob[:max_chars]


# -----------------------------
# Item 1A Risk Factors extraction
# -----------------------------
def extract_item1a_risk_factors(full_text: str) -> str:
    start = [r"\bItem\s*1A\.*\s*Risk\s*Factors\b", r"\bITEM\s*1A\.*\s*RISK\s*FACTORS\b"]
    end = [
        r"\bItem\s*1B\.*\s*Unresolved\s*Staff\s*Comments\b",
        r"\bITEM\s*1B\.*\s*UNRESOLVED\s*STAFF\s*COMMENTS\b",
        r"\bItem\s*2\.*\s*Properties\b",
        r"\bITEM\s*2\.*\s*PROPERTIES\b",
        r"\bPart\s*II\b",
        r"\bPART\s*II\b",
    ]
    return extract_section(full_text, start, end, min_len=300)


BOILERPLATE_HINTS = [
    "forward-looking statements",
    "should be read in conjunction with",
    "not be considered to be a reliable indicator",
    "may be materially and adversely affected",
]


def looks_boilerplate(par: str) -> bool:
    p = par.lower()
    if len(p) < 80:
        return True
    return any(h in p for h in BOILERPLATE_HINTS)


def segment_risk_blocks(risk_text: str) -> List[Dict[str, str]]:
    """
    Segment risk section into blocks based on subheadings.
    Heuristic heading detection works best on HTML->text.
    Output: [{"title":..., "content":...}, ...]
    """
    if not risk_text:
        return []

    lines = [ln.strip() for ln in risk_text.splitlines() if ln.strip()]

    # drop the first line if it is "Item 1A..."
    if lines and re.search(r"\bItem\s*1A\b", lines[0], flags=re.IGNORECASE):
        lines = lines[1:]

    def is_heading(line: str) -> bool:
        if len(line) < 6 or len(line) > 140:
            return False
        if line.endswith("."):
            return False
        if sum(ch.isdigit() for ch in line) > 4:
            return False
        all_caps = (line.upper() == line) and (sum(ch.isalpha() for ch in line) >= 8)
        titleish = sum(ch.isupper() for ch in line) >= 3 and "  " not in line
        if "forward-looking" in line.lower():
            return False
        return all_caps or titleish

    blocks: List[Dict[str, str]] = []
    title = "General Risk Factors"
    body: List[str] = []

    def flush():
        nonlocal title, body, blocks
        raw = normalize_text("\n".join(body))
        if not raw:
            return
        paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
        paras = [p for p in paras if not looks_boilerplate(p)]
        cleaned = normalize_text("\n\n".join(paras))
        if cleaned:
            blocks.append({"title": title, "content": cleaned})

    for ln in lines:
        if is_heading(ln):
            flush()
            title = ln
            body = []
        else:
            body.append(ln)

    flush()
    return blocks


# -----------------------------
# Financial tables extraction (HTML best)
# -----------------------------
def extract_financial_tables_from_html(file_bytes: bytes, max_tables: int = 40) -> Dict[str, Any]:
    """
    For HTML: use pandas.read_html to extract tables then classify by keyword.
    Returns a dict:
      {
        "balance_sheet": [table_json...],
        "income_statement": [...],
        "cash_flow": [...],
        "other_tables": [...]
      }
    """
    # read_html can be heavy; limit count by slicing
    tables = pd.read_html(io.BytesIO(file_bytes), flavor="lxml")
    tables = tables[:max_tables]

    out = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow": [],
        "other_tables": [],
    }

    def table_to_json(df: pd.DataFrame) -> Dict[str, Any]:
        df = df.copy()
        df.columns = [str(c) for c in df.columns]
        return {
            "shape": [int(df.shape[0]), int(df.shape[1])],
            "columns": df.columns.tolist(),
            "data": df.fillna("").astype(str).values.tolist(),
        }

    def classify(df: pd.DataFrame) -> str:
        text = " ".join(df.fillna("").astype(str).values.flatten()).lower()
        if "total assets" in text or "total liabilities" in text or "shareholders" in text:
            return "balance_sheet"
        if "net income" in text or "revenue" in text or "operating income" in text or "gross profit" in text:
            return "income_statement"
        if "cash flows" in text or "operating activities" in text or "investing activities" in text or "financing activities" in text:
            return "cash_flow"
        return "other_tables"

    for df in tables:
        kind = classify(df)
        out[kind].append(table_to_json(df))

    return out


# -----------------------------
# Industry / sector inference (lightweight)
# -----------------------------
def infer_sector_from_text(full_text: str) -> str:
    """
    MVP heuristic: try to find SIC code and map to rough sector.
    If missing, return Unknown.
    """
    m = re.search(r"\bSIC\b.*?(\d{4})", full_text, flags=re.IGNORECASE | re.DOTALL)
    sic = None
    if m:
        sic = int(m.group(1))

    if sic is None:
        return "Unknown"

    # Very rough mapping (you can refine later)
    if 3570 <= sic <= 3579 or 7370 <= sic <= 7379:
        return "Technology"
    if 2000 <= sic <= 3999:
        return "Manufacturing"
    if 5200 <= sic <= 5999:
        return "Retail"
    if 4900 <= sic <= 4999:
        return "Utilities"
    if 1300 <= sic <= 1399:
        return "Energy"
    return "Other"


# -----------------------------
# Main extraction pipeline
# -----------------------------
def extract_10k(file_bytes: bytes, ext: str) -> Dict[str, Any]:
    """
    Returns extracted payload:
      - item1_business_text
      - company_background
      - item1a_risk_text
      - risk_blocks (list)
      - financial_tables (dict; html only, else empty)
      - sector_inferred
    """
    full_text = read_file_to_text(file_bytes, ext)

    item1 = extract_item1_business(full_text)
    background = summarize_company_background(item1)

    item1a = extract_item1a_risk_factors(full_text)
    risk_blocks = segment_risk_blocks(item1a)

    financial_tables: Dict[str, Any] = {
        "balance_sheet": [],
        "income_statement": [],
        "cash_flow": [],
        "other_tables": [],
        "note": "HTML extraction works best. PDF tables are not extracted in this MVP.",
    }
    if ext.lower() in ("html", "htm"):
        try:
            financial_tables = extract_financial_tables_from_html(file_bytes)
            financial_tables["note"] = "Extracted from HTML via pandas.read_html."
        except Exception as e:
            financial_tables["note"] = f"Failed to extract tables from HTML: {e}"

    sector = infer_sector_from_text(full_text)

    return {
        "sector_inferred": sector,
        "item1_business_text": item1,
        "company_background": background,
        "item1a_risk_text": item1a,
        "risk_blocks": risk_blocks,
        "financial_tables": financial_tables,
    }
