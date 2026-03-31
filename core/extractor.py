"""
Extract Item 1 overview and Item 1A risks from SEC 10-K filings.

Supports:
  - HTML: BeautifulSoup parsing with bold/italic detection
  - PDF:  AWS Textract async text extraction → same regex parsing

Public API:
  HTML path:
    extract_item1_overview(html_bytes, company, industry) -> dict
    extract_item1a_risks(html_bytes) -> list[dict]
    extract_item1_overview_bedrock(html_bytes, company, industry) -> dict
    extract_item1a_risks_bedrock(html_bytes, company) -> list[dict]
  PDF path:
    extract_text_from_pdf(pdf_bytes) -> str
    extract_item1_overview_from_text(text, company, industry) -> dict
    extract_item1a_risks_from_text(text) -> list[dict]
"""

import json
import re
import time
import copy
import hashlib
import streamlit as st
import boto3
from bs4 import BeautifulSoup, Tag
from core.bedrock import _invoke

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

_AI_OVERVIEW_CACHE: dict[str, dict] = {}
_AI_RISKS_CACHE: dict[str, list[dict]] = {}


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


def _extract_json_obj_or_array(text: str):
    s = re.sub(r"```json|```", "", str(text or "")).strip()
    try:
        return json.loads(s)
    except Exception:
        pass

    arr_l = s.find("[")
    arr_r = s.rfind("]")
    if arr_l >= 0 and arr_r > arr_l:
        try:
            return json.loads(s[arr_l:arr_r + 1])
        except Exception:
            pass

    obj_l = s.find("{")
    obj_r = s.rfind("}")
    if obj_l >= 0 and obj_r > obj_l:
        try:
            return json.loads(s[obj_l:obj_r + 1])
        except Exception:
            return None
    return None


def _normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _normalize_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _normalize_space(s).lower()).strip()


def _count_risk_items(blocks: list[dict]) -> int:
    return sum(len(b.get("sub_risks", [])) for b in blocks if isinstance(b, dict))


def _looks_like_non_risk_title(text: str) -> bool:
    s = _normalize_space(text)
    if not s:
        return True
    if len(s) < 28:
        return True
    if len(re.findall(r"[A-Za-z]", s)) < 8:
        return True
    if len(s.split()) < 6:
        return True
    low = s.lower()
    if re.match(r"^item\s*\d+[a-z]?\b", low):
        return True
    if low in {"risk factors", "table of contents", "forward-looking statements"}:
        return True
    return False


def _evidence_ratio(ai_blocks: list[dict], source_text: str) -> float:
    if not ai_blocks:
        return 0.0
    src = _normalize_key(source_text)
    if not src:
        return 0.0
    total = 0
    hits = 0
    for blk in ai_blocks:
        for title in blk.get("sub_risks", []):
            total += 1
            norm_t = _normalize_key(title)
            if not norm_t:
                continue
            probe = " ".join(norm_t.split()[:10])
            if probe and probe in src:
                hits += 1
    return hits / max(1, total)


def _normalize_ai_risk_blocks(payload) -> list[dict]:
    if not isinstance(payload, list):
        return []
    out = []
    for block in payload:
        if not isinstance(block, dict):
            continue
        category = str(block.get("category", "") or "").strip()
        sub_risks = block.get("sub_risks", [])
        if not category:
            continue
        normalized_subs = []
        if isinstance(sub_risks, list):
            for s in sub_risks:
                if isinstance(s, str):
                    text = s.strip()
                elif isinstance(s, dict):
                    text = str(s.get("title", "") or "").strip()
                else:
                    text = str(s or "").strip()
                if text:
                    normalized_subs.append(text)
        if normalized_subs:
            out.append({"category": category, "sub_risks": normalized_subs})
    return out


def _clean_and_dedupe_ai_risk_blocks(payload: list[dict]) -> list[dict]:
    out = []
    global_seen = set()
    for block in payload:
        category = _normalize_space(block.get("category", "")) or "Risk Factors"
        subs = []
        local_seen = set()
        for title in block.get("sub_risks", []):
            t = _normalize_space(title)
            if _looks_like_non_risk_title(t):
                continue
            k = _normalize_key(t)
            if not k or k in local_seen or k in global_seen:
                continue
            local_seen.add(k)
            global_seen.add(k)
            subs.append(t)
        if subs:
            out.append({"category": category, "sub_risks": subs})
    return out


def _locate_item1_text_block(text: str) -> str:
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
    return _clean_text(raw)


def extract_item1_overview(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """Extract Item 1 overview from HTML."""
    text = _full_text(_make_soup(html_bytes))
    return _extract_overview_from_text(text, company_name, industry)


def extract_item1_overview_bedrock(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """
    AI-enhanced Item 1 overview extraction using Bedrock Nova Pro.
    Falls back to extract_item1_overview() on any failure.
    """
    fallback = extract_item1_overview(html_bytes, company_name, industry)
    key_raw = html_bytes + f"|{company_name}|{industry}".encode("utf-8", errors="ignore")
    cache_key = hashlib.sha256(key_raw).hexdigest()
    if cache_key in _AI_OVERVIEW_CACHE:
        return copy.deepcopy(_AI_OVERVIEW_CACHE[cache_key])
    try:
        text = _full_text(_make_soup(html_bytes))
        item1_text = _locate_item1_text_block(text)
        source_text = item1_text if item1_text else fallback.get("background", "")
        source_text = str(source_text or "").strip()
        if not source_text or len(source_text) < 120:
            _AI_OVERVIEW_CACHE[cache_key] = copy.deepcopy(fallback)
            return fallback
        source_text = source_text[:16000]

        prompt = f"""You are extracting the Item 1 Business overview from a U.S. SEC 10-K filing.

Company: {company_name or "Unknown"}
Industry: {industry or "Unknown"}

Input text (already narrowed to Item 1 region):
\"\"\"{source_text}\"\"\"

Return ONLY a JSON object with exactly this schema:
{{
  "background": "A concise 3-6 sentence business overview in plain English."
}}

Do not include markdown fences or extra keys."""

        raw = _invoke(prompt, max_tokens=1000)
        parsed = _extract_json_obj_or_array(raw)
        if isinstance(parsed, dict):
            bg = str(parsed.get("background", "") or "").strip()
            if bg:
                out = dict(fallback)
                out["background"] = bg
                _AI_OVERVIEW_CACHE[cache_key] = copy.deepcopy(out)
                return out
    except Exception:
        pass
    _AI_OVERVIEW_CACHE[cache_key] = copy.deepcopy(fallback)
    return fallback


def extract_item1a_risks_bedrock(
    html_bytes: bytes,
    company_name: str = "",
) -> list[dict]:
    """
    AI-enhanced Item 1A risk extraction using Bedrock Nova Pro.
    Returns same structure as extract_item1a_risks():
      [{"category": str, "sub_risks": [str, ...]}, ...]
    Falls back to extract_item1a_risks() on any failure.
    """
    fallback = extract_item1a_risks(html_bytes)
    key_raw = html_bytes + f"|{company_name}".encode("utf-8", errors="ignore")
    cache_key = hashlib.sha256(key_raw).hexdigest()
    if cache_key in _AI_RISKS_CACHE:
        return copy.deepcopy(_AI_RISKS_CACHE[cache_key])
    try:
        text = _full_text(_make_soup(html_bytes))
        rng = _locate_item1a_range(text)
        if rng is None:
            _AI_RISKS_CACHE[cache_key] = copy.deepcopy(fallback)
            return fallback
        start_pos, end_pos = rng
        item1a_text = _clean_text(text[start_pos:end_pos])
        if not item1a_text or len(item1a_text) < 200:
            _AI_RISKS_CACHE[cache_key] = copy.deepcopy(fallback)
            return fallback
        item1a_text = item1a_text[:36000]

        prompt = f"""You are an expert SEC 10-K parser.
Extract risk factors from Item 1A text and organize them into category blocks.
Use exact wording from source risk statements whenever possible.

Company: {company_name or "Unknown"}

Input text (Item 1A):
\"\"\"{item1a_text}\"\"\"

Return ONLY a JSON array. Each element MUST have this exact schema:
[
  {{
    "category": "Category name",
    "sub_risks": [
      "Risk statement 1",
      "Risk statement 2"
    ]
  }}
]

Rules:
- Keep sub_risks as strings only (no nested objects).
- Preserve risk meaning from source text.
- Prefer full risk statements; do not output incomplete fragments.
- Do not return markdown fences.
- Do not include any keys other than category and sub_risks."""

        raw = _invoke(prompt, max_tokens=3000)
        parsed = _extract_json_obj_or_array(raw)
        normalized = _normalize_ai_risk_blocks(parsed)
        cleaned = _clean_and_dedupe_ai_risk_blocks(normalized)
        if cleaned:
            base_cnt = _count_risk_items(fallback)
            ai_cnt = _count_risk_items(cleaned)
            coverage = (ai_cnt / base_cnt) if base_cnt > 0 else 1.0
            ev_ratio = _evidence_ratio(cleaned, item1a_text)

            # Quality gate:
            # If AI output is too sparse/noisy or weakly grounded in source text,
            # prioritize deterministic BeautifulSoup extraction.
            if ai_cnt >= 1 and 0.85 <= coverage <= 1.25 and ev_ratio >= 0.55:
                _AI_RISKS_CACHE[cache_key] = copy.deepcopy(cleaned)
                return cleaned
    except Exception:
        pass
    _AI_RISKS_CACHE[cache_key] = copy.deepcopy(fallback)
    return fallback


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
