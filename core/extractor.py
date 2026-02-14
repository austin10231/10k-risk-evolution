"""
Extract Item 1 overview and Item 1A risks from SEC 10-K filing HTML.

Functions:
  extract_item1_overview(html_bytes)  -> str
  extract_item1a_risks(html_bytes)    -> list[dict]   [{title, content}, ...]
"""

import re
from bs4 import BeautifulSoup, Tag

# ── Regex patterns ────────────────────────────────────────────────────────────

# Item 1. (Business) — start of overview
_ITEM1_START = re.compile(
    r"(?i)\bitem\s*1[\.\:\s\—\-–]+\s*bus(?:iness)?",
)
# Item 1A. (Risk Factors) — end of overview / start of risks
_ITEM1A_START = re.compile(
    r"(?i)\bitem\s*1\s*a[\.\:\s\—\-–]+\s*risk\s+factors",
)
# Item 1B or Item 2 — end of risks
_ITEM1A_END = [
    re.compile(r"(?i)\bitem\s*1\s*b[\.\:\s\—\-–]"),
    re.compile(r"(?i)\bitem\s*2[\.\:\s\—\-–]"),
]


def _html_to_text(html_bytes: bytes) -> str:
    soup = BeautifulSoup(html_bytes, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text(separator="\n")


def _clean(text: str) -> str:
    """Remove excessive blank lines, page numbers, and table-of-contents noise."""
    lines = text.split("\n")
    cleaned = []
    for ln in lines:
        s = ln.strip()
        # skip pure page numbers like "42" or "F-3"
        if re.match(r"^[\dF][\d\-]*$", s):
            continue
        # skip short TOC-like lines ("Item 1A." alone)
        if re.match(r"^item\s*\d", s, re.IGNORECASE) and len(s) < 60:
            continue
        # skip lines that are just dots / underscores (TOC leaders)
        if re.match(r"^[\.\s_\-–—]{5,}$", s):
            continue
        cleaned.append(s)
    # collapse multiple blank lines
    out = "\n".join(cleaned)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _is_toc_region(text: str) -> bool:
    """Heuristic: if a 2000-char block has >5 'Item X' occurrences it's likely a TOC."""
    sample = text[:2000]
    return len(re.findall(r"(?i)\bitem\s*\d", sample)) > 5


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════


def extract_item1_overview(html_bytes: bytes) -> str:
    """Extract text between Item 1 (Business) and Item 1A (Risk Factors).
    Returns a trimmed overview string (target 500-1200 chars)."""
    text = _html_to_text(html_bytes)

    # Find ALL Item 1 matches, skip TOC ones
    starts = list(_ITEM1_START.finditer(text))
    ends = list(_ITEM1A_START.finditer(text))

    if not starts or not ends:
        return "(Item 1 overview could not be extracted.)"

    # Pick the last substantial Item 1 start that appears before an Item 1A
    best_start = None
    best_end = None
    for s in starts:
        for e in ends:
            if e.start() > s.start() + 200:  # must have some content between
                candidate = text[s.start():e.start()]
                if not _is_toc_region(candidate):
                    best_start = s.start()
                    best_end = e.start()
                    break
        if best_start is not None:
            break

    if best_start is None:
        # fallback: just use last match
        best_start = starts[-1].start()
        best_end = ends[-1].start()

    raw = text[best_start:best_end]
    overview = _clean(raw)

    # Trim to reasonable length (keep first ~1200 chars, break at sentence)
    if len(overview) > 1500:
        cut = overview[:1500]
        last_period = cut.rfind(".")
        if last_period > 500:
            overview = cut[: last_period + 1]

    return overview if overview else "(No overview text found.)"


def extract_item1a_risks(html_bytes: bytes) -> list[dict]:
    """Extract risk blocks from Item 1A.
    Returns list of {title: str, content: str}."""
    soup = BeautifulSoup(html_bytes, "lxml")
    for tag in soup(["script", "style"]):
        tag.decompose()
    full_text = soup.get_text(separator="\n")

    # ── Locate Item 1A boundaries ─────────────────────────────────────────────
    # Find all Item 1A matches, pick the one that starts a real section (not TOC)
    matches_1a = list(_ITEM1A_START.finditer(full_text))
    if not matches_1a:
        return []

    start_pos = None
    for m in matches_1a:
        region = full_text[m.start(): m.start() + 2000]
        if not _is_toc_region(region):
            start_pos = m.end()
            break
    if start_pos is None:
        start_pos = matches_1a[-1].end()  # fallback to last

    # Find end (Item 1B or Item 2)
    end_pos = len(full_text)
    for pat in _ITEM1A_END:
        for m in pat.finditer(full_text):
            if m.start() > start_pos + 500:
                # Make sure this isn't a TOC reference
                pre_context = full_text[max(0, m.start()-200):m.start()]
                if not _is_toc_region(pre_context):
                    end_pos = min(end_pos, m.start())
                    break

    raw_1a = full_text[start_pos:end_pos]
    cleaned_1a = _clean(raw_1a)

    if len(cleaned_1a) < 100:
        return []

    # ── Strategy 1: use <b>/<strong> tags as risk titles ──────────────────────
    risks = _split_by_bold_tags(soup, start_pos, end_pos, full_text)
    if len(risks) >= 3:
        return risks

    # ── Strategy 2: paragraph heuristic ───────────────────────────────────────
    return _split_by_paragraphs(cleaned_1a)


def _split_by_bold_tags(
    soup: BeautifulSoup,
    start_char: int,
    end_char: int,
    full_text: str,
) -> list[dict]:
    """Try to use <b>/<strong>/<i> tags as risk titles."""
    # Collect bold/strong text snippets within the Item 1A region
    bold_texts: list[str] = []
    for tag in soup.find_all(["b", "strong"]):
        t = tag.get_text(strip=True)
        if 15 < len(t) < 300:
            # Check if this bold text falls within Item 1A region
            bold_texts.append(t)

    if len(bold_texts) < 3:
        return []

    # Use bold texts as section delimiters in the cleaned text
    text = full_text[start_char:end_char]
    cleaned = _clean(text)

    risks: list[dict] = []
    for i, bt in enumerate(bold_texts):
        # Find this bold text in cleaned text
        idx = cleaned.find(bt)
        if idx == -1:
            # try fuzzy: first 40 chars
            idx = cleaned.find(bt[:40])
        if idx == -1:
            continue

        # Content is from end of title to start of next title
        content_start = idx + len(bt)
        if i + 1 < len(bold_texts):
            next_idx = cleaned.find(bold_texts[i + 1], content_start)
            if next_idx == -1:
                next_idx = cleaned.find(bold_texts[i + 1][:40], content_start)
            content_end = next_idx if next_idx > content_start else len(cleaned)
        else:
            content_end = len(cleaned)

        content = cleaned[content_start:content_end].strip()
        title = bt.strip().rstrip(".").strip()

        if len(content) > 30 and len(title) > 10:
            risks.append({"title": title, "content": content})

    return risks


def _split_by_paragraphs(cleaned_text: str) -> list[dict]:
    """Fallback: split on double-newlines, use short paragraphs as titles."""
    parts = re.split(r"\n\s*\n", cleaned_text)
    parts = [p.strip() for p in parts if len(p.strip()) > 30]

    risks: list[dict] = []
    i = 0
    while i < len(parts):
        p = parts[i]
        # If paragraph is short (< 200 chars), treat as title
        if len(p) < 200:
            title = p.rstrip(".").strip()
            # Gather following long paragraphs as content
            content_parts = []
            i += 1
            while i < len(parts) and len(parts[i]) >= 100:
                content_parts.append(parts[i])
                i += 1
            content = "\n\n".join(content_parts) if content_parts else title
            risks.append({"title": title[:150], "content": content})
        else:
            # Long paragraph with no title: use first sentence as title
            first_period = p.find(".")
            if 10 < first_period < 200:
                title = p[:first_period].strip()
                content = p
            else:
                title = p[:100].strip() + " …"
                content = p
            risks.append({"title": title, "content": content})
            i += 1

    return risks
