"""
Extract Item 1 overview and Item 1A risks from SEC 10-K filing HTML.

Output structure for risks:
[
  {
    "category": "Macroeconomic and Industry Risks",
    "sub_risks": [
      "The Company's operations and performance depend ...",
      "The Company's business can be impacted by ..."
    ]
  },
  ...
]
"""

import re
from bs4 import BeautifulSoup, NavigableString, Tag

# ── Regex patterns ────────────────────────────────────────────────────────────
_ITEM1_START = re.compile(
    r"\bitem\s*1[\.\:\s\—\-–]+\s*bus(?:iness)?", re.IGNORECASE,
)
_ITEM1A_START = re.compile(
    r"\bitem\s*1\s*a[\.\:\s\—\-–]+\s*risk\s+factors", re.IGNORECASE,
)
_ITEM1A_END = [
    re.compile(r"\bitem\s*1\s*b[\.\:\s\—\-–]", re.IGNORECASE),
    re.compile(r"\bitem\s*2[\.\:\s\—\-–]", re.IGNORECASE),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _soup(html_bytes: bytes) -> BeautifulSoup:
    s = BeautifulSoup(html_bytes, "lxml")
    for t in s(["script", "style"]):
        t.decompose()
    return s


def _full_text(soup: BeautifulSoup) -> str:
    return soup.get_text(separator="\n")


def _is_toc_region(text: str) -> bool:
    """If a 2000-char block has >5 'Item X' hits it's likely a table of contents."""
    return len(re.findall(r"\bitem\s*\d", text[:2000], re.IGNORECASE)) > 5


def _clean_text(text: str) -> str:
    lines = text.split("\n")
    out = []
    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue
        # skip page numbers like "42", "F-3"
        if re.match(r"^[\dF][\d\-]*$", s):
            continue
        # skip standalone short Item references (TOC lines)
        if re.match(r"^item\s*\d", s, re.IGNORECASE) and len(s) < 60:
            continue
        # skip dot leaders
        if re.match(r"^[\.\s_\-–—]{5,}$", s):
            continue
        out.append(s)
    result = "\n".join(out)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ══════════════════════════════════════════════════════════════════════════════
#  ITEM 1 OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

def extract_item1_overview(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    """
    Returns structured overview dict:
    {
      "company": "...",
      "industry": "...",
      "background": "..."
    }
    """
    text = _full_text(_soup(html_bytes))

    starts = list(_ITEM1_START.finditer(text))
    ends = list(_ITEM1A_START.finditer(text))

    background = ""
    if starts and ends:
        # Pick a start→end pair that isn't inside a TOC
        for s in starts:
            for e in ends:
                if e.start() > s.start() + 200:
                    candidate = text[s.start():e.start()]
                    if not _is_toc_region(candidate):
                        background = _clean_text(candidate)
                        break
            if background:
                break

        # fallback
        if not background and starts and ends:
            background = _clean_text(text[starts[-1].start():ends[-1].start()])

    # Trim to reasonable length
    if len(background) > 2000:
        cut = background[:2000]
        lp = cut.rfind(".")
        if lp > 500:
            background = cut[:lp + 1]

    return {
        "company": company_name,
        "industry": industry,
        "background": background if background else "(Could not extract Item 1 overview.)",
    }


# ══════════════════════════════════════════════════════════════════════════════
#  ITEM 1A RISKS — hierarchical extraction
# ══════════════════════════════════════════════════════════════════════════════

def extract_item1a_risks(html_bytes: bytes) -> list[dict]:
    """
    Returns:
    [
      {
        "category": "Macroeconomic and Industry Risks",
        "sub_risks": ["title1", "title2", ...]
      },
      ...
    ]
    """
    soup = _soup(html_bytes)
    full = _full_text(soup)

    # ── 1. Locate Item 1A text boundaries ─────────────────────────────────────
    matches_1a = list(_ITEM1A_START.finditer(full))
    if not matches_1a:
        return []

    start_pos = None
    for m in matches_1a:
        region = full[m.start():m.start() + 2000]
        if not _is_toc_region(region):
            start_pos = m.end()
            break
    if start_pos is None:
        start_pos = matches_1a[-1].end()

    end_pos = len(full)
    for pat in _ITEM1A_END:
        for m in pat.finditer(full):
            if m.start() > start_pos + 500:
                pre = full[max(0, m.start() - 200):m.start()]
                if not _is_toc_region(pre):
                    end_pos = min(end_pos, m.start())
                    break

    # ── 2. Collect bold/strong elements from HTML within that range ───────────
    # We'll walk the soup and classify bold elements as:
    #   - "category header": bold but NOT italic, typically short (< 80 chars),
    #     looks like "Macroeconomic and Industry Risks"
    #   - "sub-risk title": bold+italic, longer, starts with "The Company..."
    #     or similar phrasing

    bold_items: list[dict] = []  # {text, is_italic, char_pos_approx}

    for tag in soup.find_all(["b", "strong"]):
        txt = tag.get_text(strip=True)
        if len(txt) < 10 or len(txt) > 500:
            continue

        # Check if italic (tag itself is <i>/<em>, or contains one, or parent is)
        is_italic = False
        if tag.find(["i", "em"]):
            is_italic = True
        if tag.parent and tag.parent.name in ("i", "em"):
            is_italic = True
        # Also check if the tag name itself is inside an italic wrapper
        for p in tag.parents:
            if p.name in ("i", "em"):
                is_italic = True
                break

        # Approximate position in full text
        pos = full.find(txt)
        if pos == -1:
            pos = full.find(txt[:50])
        if pos == -1:
            continue

        # Only keep if within Item 1A range
        if start_pos <= pos <= end_pos:
            bold_items.append({
                "text": txt,
                "is_italic": is_italic,
                "pos": pos,
            })

    # Deduplicate by text (keep first occurrence)
    seen = set()
    unique_bold: list[dict] = []
    for b in bold_items:
        key = b["text"].strip().lower()
        if key not in seen:
            seen.add(key)
            unique_bold.append(b)

    # Sort by position
    unique_bold.sort(key=lambda x: x["pos"])

    # ── 3. Build hierarchical structure ───────────────────────────────────────
    # Heuristic: non-italic bold → category header
    #            italic bold     → sub-risk title
    # If ALL bolds are italic (no separate category headers), fall back to
    # a single "General Risks" category.

    categories_found = [b for b in unique_bold if not b["is_italic"]]
    subrisk_found = [b for b in unique_bold if b["is_italic"]]

    # If we have clear categories + sub-risks, group them
    if categories_found and subrisk_found:
        return _group_hierarchical(categories_found, subrisk_found)

    # Fallback: if all bold items look the same (all italic or all non-italic),
    # treat them all as sub-risk titles under one category
    if unique_bold:
        return [{
            "category": "Risk Factors",
            "sub_risks": [b["text"] for b in unique_bold],
        }]

    # ── 4. Final fallback: paragraph-based splitting ──────────────────────────
    return _fallback_paragraph_split(full[start_pos:end_pos])


def _group_hierarchical(
    categories: list[dict],
    subrisk_items: list[dict],
) -> list[dict]:
    """Group sub-risk titles under their nearest preceding category header."""
    result: list[dict] = []

    for i, cat in enumerate(categories):
        cat_start = cat["pos"]
        # Category range ends at next category or at end
        cat_end = categories[i + 1]["pos"] if i + 1 < len(categories) else float("inf")

        subs = [
            sr["text"]
            for sr in subrisk_items
            if cat_start <= sr["pos"] < cat_end
        ]

        if subs:
            result.append({
                "category": cat["text"],
                "sub_risks": subs,
            })

    # Any sub-risks before the first category?
    if categories:
        first_cat_pos = categories[0]["pos"]
        orphans = [sr["text"] for sr in subrisk_items if sr["pos"] < first_cat_pos]
        if orphans:
            result.insert(0, {
                "category": "General Risks",
                "sub_risks": orphans,
            })

    return result


def _fallback_paragraph_split(raw_text: str) -> list[dict]:
    """If no bold structure found, split by paragraphs."""
    cleaned = _clean_text(raw_text)
    parts = re.split(r"\n\s*\n", cleaned)
    titles = [p.strip() for p in parts if 20 < len(p.strip()) < 300]
    if titles:
        return [{"category": "Risk Factors", "sub_risks": titles[:30]}]
    return []
