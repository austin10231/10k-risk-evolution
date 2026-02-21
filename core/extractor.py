"""
Extract Item 1 overview and Item 1A risks from SEC 10-K filings.

Supports:
  - HTML: BeautifulSoup parsing with bold/italic detection
  - PDF:  AWS Textract async text extraction → same regex parsing

Public API:
  HTML path:
    extract_item1_overview(html_bytes, company, industry) -> dict
    extract_item1a_risks(html_bytes) -> list[dict]
  PDF path:
    extract_text_from_pdf(pdf_bytes) -> str
    extract_item1_overview_from_text(text, company, industry) -> dict
    extract_item1a_risks_from_text(text) -> list[dict]
"""

import re
import time
import streamlit as st
import boto3
from bs4 import BeautifulSoup, Tag

# ── Regex patterns ────────────────────────────────────────────────────────────
_ITEM1_START = re.compile(
    r"item\s*1[\.\:\s\u2014\u2013\-]+\s*bus(?:iness)?", re.IGNORECASE,
)
_ITEM1A_START = re.compile(
    r"item\s*1\s*a[\.\:\s\u2014\u2013\-]+\s*risk\s+factors", re.IGNORECASE,
)
_ITEM1A_END = [
    re.compile(r"item\s*1\s*b[\.\:\s\u2014\u2013\-]", re.IGNORECASE),
    re.compile(r"item\s*2[\.\:\s\u2014\u2013\-]", re.IGNORECASE),
]


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _is_toc_region(text: str) -> bool:
    return len(re.findall(r"item\s*\d", text[:2000], re.IGNORECASE)) > 5


def _clean_text(text: str) -> str:
    lines = text.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if re.match(r"^[\dF][\d\-]*$", s):
            continue
        if re.match(r"^item\s*\d", s, re.IGNORECASE) and len(s) < 60:
            continue
        if re.match(r"^[\.\s_\-\u2013\u2014]{5,}$", s):
            continue
        out.append(s)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return result.strip()


def _locate_item1a_range(text: str):
    """Find start and end char positions of Item 1A in text. Returns (start, end) or None."""
    matches_1a = list(_ITEM1A_START.finditer(text))
    if not matches_1a:
        return None

    start_pos = None
    for m in matches_1a:
        region = text[m.start():m.start() + 2000]
        if not _is_toc_region(region):
            start_pos = m.end()
            break
    if start_pos is None:
        start_pos = matches_1a[-1].end()

    end_pos = len(text)
    for pat in _ITEM1A_END:
        for m in pat.finditer(text):
            if m.start() > start_pos + 500:
                pre = text[max(0, m.start() - 200):m.start()]
                if not _is_toc_region(pre):
                    end_pos = min(end_pos, m.start())
                    break

    return start_pos, end_pos


def _extract_overview_from_text(
    text: str,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """Extract Item 1 overview from plain text (shared by HTML and PDF paths)."""
    starts = list(_ITEM1_START.finditer(text))
    ends = list(_ITEM1A_START.finditer(text))

    raw = ""
    if starts and ends:
        for s in starts:
            for e in ends:
                if e.start() > s.start() + 200:
                    candidate = text[s.start():e.start()]
                    if not _is_toc_region(candidate):
                        raw = candidate
                        break
            if raw:
                break
        if not raw:
            raw = text[starts[-1].start():ends[-1].start()]

    cut_patterns = [
        re.compile(r"\n\s*Products\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Services\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Segments?\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Human Capital\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Employees\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Competition\s*\n", re.IGNORECASE),
        re.compile(r"\n\s*Seasonality\s*\n", re.IGNORECASE),
    ]
    for cp in cut_patterns:
        m = cp.search(raw)
        if m and m.start() > 100:
            raw = raw[:m.start()]
            break

    background = _clean_text(raw)

    if len(background) > 1500:
        cut = background[:1500]
        lp = cut.rfind(".")
        if lp > 200:
            background = cut[:lp + 1]

    return {
        "company": company_name,
        "industry": industry,
        "year": 0,
        "filing_type": "",
        "background": background if background else "(Could not extract Item 1 overview.)",
    }


def _extract_risks_from_text_fallback(text: str) -> list[dict]:
    """Extract risks from plain text using paragraph heuristic (for PDF or fallback)."""
    rng = _locate_item1a_range(text)
    if rng is None:
        return []

    start_pos, end_pos = rng
    raw_1a = text[start_pos:end_pos]
    cleaned = _clean_text(raw_1a)

    if len(cleaned) < 100:
        return []

    # Split by double newlines
    parts = re.split(r"\n\s*\n", cleaned)
    paras = [p.strip() for p in parts if len(p.strip()) > 40]

    if not paras:
        return []

    # Heuristic: short lines without period = category headers
    # Medium lines = sub-risk titles
    risks: list[dict] = []
    current_cat = "Risk Factors"
    current_subs: list[str] = []

    for p in paras:
        # Category header: short, no period at end, looks like a heading
        if len(p) < 80 and not p.endswith(".") and not p.endswith(","):
            if current_subs:
                risks.append({"category": current_cat, "sub_risks": current_subs})
                current_subs = []
            current_cat = p
        # Sub-risk title: medium length, italic-like (starts with "The Company" etc.)
        elif len(p) < 400 and (
            p.startswith("The Company") or
            p.startswith("The ") or
            p.startswith("Our ") or
            p.startswith("We ") or
            p.startswith("Adverse") or
            p.startswith("Changes") or
            p.startswith("Failure") or
            p.startswith("If ") or
            p.startswith("A ") or
            p.startswith("Expectations") or
            p.startswith("Future")
        ):
            current_subs.append(p)
        elif len(p) < 250:
            current_subs.append(p)

    if current_subs:
        risks.append({"category": current_cat, "sub_risks": current_subs})

    if not risks and paras:
        return [{"category": "Risk Factors", "sub_risks": [p for p in paras[:30] if len(p) < 400]}]

    return risks


# ══════════════════════════════════════════════════════════════════════════════
#  PDF PATH — AWS Textract
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


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Use Textract async API to extract text from a multi-page PDF.
    Steps:
      1. Upload PDF to S3 temp location
      2. Start async text detection
      3. Poll until complete
      4. Collect all pages of text
      5. Delete temp file
    """
    import uuid

    bucket = st.secrets["S3_BUCKET"]
    temp_key = f"_textract_temp/{uuid.uuid4().hex}.pdf"

    s3 = _get_s3()
    textract = _get_textract()

    try:
        # 1. Upload to S3
        s3.put_object(Bucket=bucket, Key=temp_key, Body=pdf_bytes)

        # 2. Start async job
        response = textract.start_document_text_detection(
            DocumentLocation={
                "S3Object": {
                    "Bucket": bucket,
                    "Name": temp_key,
                }
            }
        )
        job_id = response["JobId"]

        # 3. Poll until complete
        max_wait = 120  # seconds
        waited = 0
        while waited < max_wait:
            result = textract.get_document_text_detection(JobId=job_id)
            status = result["JobStatus"]

            if status == "SUCCEEDED":
                break
            elif status == "FAILED":
                return ""

            time.sleep(3)
            waited += 3

        if status != "SUCCEEDED":
            return ""

        # 4. Collect all pages
        lines = []
        next_token = None

        while True:
            if next_token:
                result = textract.get_document_text_detection(
                    JobId=job_id, NextToken=next_token,
                )
            # else: we already have the first result from polling

            for block in result.get("Blocks", []):
                if block["BlockType"] == "LINE":
                    lines.append(block["Text"])

            next_token = result.get("NextToken")
            if not next_token:
                break

        return "\n".join(lines)

    finally:
        # 5. Clean up temp file
        try:
            s3.delete_object(Bucket=bucket, Key=temp_key)
        except Exception:
            pass


def extract_item1_overview_from_text(
    text: str,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """Extract Item 1 overview from Textract-extracted plain text."""
    return _extract_overview_from_text(text, company_name, industry)


def extract_item1a_risks_from_text(text: str) -> list[dict]:
    """Extract Item 1A risks from Textract-extracted plain text."""
    return _extract_risks_from_text_fallback(text)


# ══════════════════════════════════════════════════════════════════════════════
#  HTML PATH — BeautifulSoup (existing logic, unchanged)
# ══════════════════════════════════════════════════════════════════════════════

def _make_soup(html_bytes: bytes) -> BeautifulSoup:
    s = BeautifulSoup(html_bytes, "lxml")
    for t in s(["script", "style"]):
        t.decompose()
    return s


def _full_text(soup: BeautifulSoup) -> str:
    return soup.get_text(separator="\n")


def _is_bold(tag: Tag) -> bool:
    if tag.name in ("b", "strong"):
        return True
    style = tag.get("style", "")
    if style:
        if re.search(r"font-weight\s*:\s*(bold|[7-9]\d\d)", style, re.IGNORECASE):
            return True
    for p in list(tag.parents)[:3]:
        if not isinstance(p, Tag):
            break
        if p.name in ("b", "strong"):
            return True
        ps = p.get("style", "")
        if ps and re.search(r"font-weight\s*:\s*(bold|[7-9]\d\d)", ps, re.IGNORECASE):
            return True
    return False


def _is_italic(tag: Tag) -> bool:
    if tag.name in ("i", "em"):
        return True
    style = tag.get("style", "")
    if style and re.search(r"font-style\s*:\s*italic", style, re.IGNORECASE):
        return True
    for child in tag.descendants:
        if isinstance(child, Tag):
            if child.name in ("i", "em"):
                return True
            cs = child.get("style", "")
            if cs and re.search(r"font-style\s*:\s*italic", cs, re.IGNORECASE):
                return True
    for p in list(tag.parents)[:3]:
        if not isinstance(p, Tag):
            break
        if p.name in ("i", "em"):
            return True
        ps = p.get("style", "")
        if ps and re.search(r"font-style\s*:\s*italic", ps, re.IGNORECASE):
            return True
    return False


def _find_text_pos(full_text: str, snippet: str) -> int:
    pos = full_text.find(snippet)
    if pos >= 0:
        return pos
    short = snippet[:60]
    pos = full_text.find(short)
    if pos >= 0:
        return pos
    norm_snippet = re.sub(r"\s+", " ", snippet[:80]).strip()
    norm_full = re.sub(r"\s+", " ", full_text)
    pos = norm_full.find(norm_snippet)
    return pos


def extract_item1_overview(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """Extract Item 1 overview from HTML."""
    text = _full_text(_make_soup(html_bytes))
    return _extract_overview_from_text(text, company_name, industry)


def extract_item1a_risks(html_bytes: bytes) -> list[dict]:
    """Extract Item 1A risks from HTML using bold/italic tag detection."""
    soup = _make_soup(html_bytes)
    full = _full_text(soup)

    rng = _locate_item1a_range(full)
    if rng is None:
        return []

    start_pos, end_pos = rng

    # Collect bold elements within Item 1A range
    bold_items: list[dict] = []

    for tag in soup.find_all(["p", "div", "span", "b", "strong", "font", "td", "a"]):
        txt = tag.get_text(strip=True)
        if len(txt) < 12 or len(txt) > 500:
            continue
        if not _is_bold(tag):
            continue

        pos = _find_text_pos(full, txt)
        if pos < 0:
            continue
        if not (start_pos <= pos <= end_pos):
            continue

        bold_items.append({
            "text": txt,
            "is_italic": _is_italic(tag),
            "pos": pos,
        })

    # Deduplicate
    bold_items.sort(key=lambda x: x["pos"])
    unique: list[dict] = []
    seen_texts: set[str] = set()
    seen_positions: list[tuple[int, int]] = []

    for b in bold_items:
        key = b["text"].strip().lower()
        if key in seen_texts:
            continue
        overlaps = False
        for sp, ep in seen_positions:
            if sp <= b["pos"] <= ep or b["pos"] <= sp <= b["pos"] + len(b["text"]):
                for existing in unique:
                    if (existing["text"].strip().lower() in key or
                            key in existing["text"].strip().lower()):
                        overlaps = True
                        break
            if overlaps:
                break
        if overlaps:
            continue
        seen_texts.add(key)
        seen_positions.append((b["pos"], b["pos"] + len(b["text"])))
        unique.append(b)

    # Classify
    categories = [b for b in unique if not b["is_italic"]]
    subrisk_titles = [b for b in unique if b["is_italic"]]

    if categories and subrisk_titles:
        result = _group_hierarchical(categories, subrisk_titles)
        if result:
            return result

    if subrisk_titles and not categories:
        return [{"category": "Risk Factors", "sub_risks": [b["text"] for b in subrisk_titles]}]

    if categories and not subrisk_titles:
        cats = [b for b in categories if len(b["text"]) < 60 and "." not in b["text"][:50]]
        subs = [b for b in categories if b not in cats]
        if cats and subs:
            return _group_hierarchical(cats, subs)
        return [{"category": "Risk Factors", "sub_risks": [b["text"] for b in categories]}]

    # Fallback to text-based
    return _extract_risks_from_text_fallback(full)


def _group_hierarchical(
    categories: list[dict],
    subrisk_items: list[dict],
) -> list[dict]:
    result: list[dict] = []

    if categories:
        first_cat_pos = categories[0]["pos"]
        orphans = [sr["text"] for sr in subrisk_items if sr["pos"] < first_cat_pos]
        if orphans:
            result.append({"category": "General Risks", "sub_risks": orphans})

    for i, cat in enumerate(categories):
        cat_start = cat["pos"]
        cat_end = categories[i + 1]["pos"] if i + 1 < len(categories) else float("inf")
        subs = [sr["text"] for sr in subrisk_items if cat_start <= sr["pos"] < cat_end]
        if subs:
            result.append({"category": cat["text"], "sub_risks": subs})

    result = [r for r in result if r["sub_risks"]]
    return result
