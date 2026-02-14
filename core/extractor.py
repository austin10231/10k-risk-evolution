"""
Extract Item 1 overview and Item 1A risks from SEC 10-K filing HTML.

Handles multiple HTML styles:
  - <b>/<strong> tags
  - <span style="font-weight:bold"> or font-weight:700
  - Nested italic via <i>/<em> or font-style:italic
"""

import re
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_soup(html_bytes: bytes) -> BeautifulSoup:
    s = BeautifulSoup(html_bytes, "lxml")
    for t in s(["script", "style"]):
        t.decompose()
    return s


def _full_text(soup: BeautifulSoup) -> str:
    return soup.get_text(separator="\n")


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


def _is_bold(tag: Tag) -> bool:
    """Check if a tag renders as bold — handles <b>, <strong>, and CSS styles."""
    if tag.name in ("b", "strong"):
        return True
    style = tag.get("style", "")
    if style:
        if re.search(r"font-weight\s*:\s*(bold|[7-9]\d\d)", style, re.IGNORECASE):
            return True
    # Check parent chain (up to 3 levels)
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
    """Check if a tag renders as italic — handles <i>, <em>, and CSS styles."""
    if tag.name in ("i", "em"):
        return True
    style = tag.get("style", "")
    if style and re.search(r"font-style\s*:\s*italic", style, re.IGNORECASE):
        return True
    # Check children
    for child in tag.descendants:
        if isinstance(child, Tag):
            if child.name in ("i", "em"):
                return True
            cs = child.get("style", "")
            if cs and re.search(r"font-style\s*:\s*italic", cs, re.IGNORECASE):
                return True
    # Check parent chain
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
    """Find approximate position of snippet in full_text."""
    pos = full_text.find(snippet)
    if pos >= 0:
        return pos
    # Try with first 60 chars
    short = snippet[:60]
    pos = full_text.find(short)
    if pos >= 0:
        return pos
    # Try normalized whitespace match
    norm_snippet = re.sub(r"\s+", " ", snippet[:80]).strip()
    norm_full = re.sub(r"\s+", " ", full_text)
    pos = norm_full.find(norm_snippet)
    return pos


# ══════════════════════════════════════════════════════════════════════════════
#  ITEM 1 OVERVIEW
# ══════════════════════════════════════════════════════════════════════════════

def extract_item1_overview(
    html_bytes: bytes,
    company_name: str = "",
    industry: str = "",
) -> dict:
    text = _full_text(_make_soup(html_bytes))

    starts = list(_ITEM1_START.finditer(text))
    ends = list(_ITEM1A_START.finditer(text))

    background = ""
    if starts and ends:
        for s in starts:
            for e in ends:
                if e.start() > s.start() + 200:
                    candidate = text[s.start():e.start()]
                    if not _is_toc_region(candidate):
                        background = _clean_text(candidate)
                        break
            if background:
                break
        if not background:
            background = _clean_text(text[starts[-1].start():ends[-1].start()])

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
      { "category": "Macroeconomic and Industry Risks",
        "sub_risks": ["title1", "title2", ...] },
      ...
    ]
    """
    soup = _make_soup(html_bytes)
    full = _full_text(soup)

    # ── 1. Locate Item 1A text range ──────────────────────────────────────────
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

    # ── 2. Walk ALL elements and collect bold text in Item 1A range ───────────
    #    We check every <p>, <div>, <span>, <b>, <strong>, <font>, etc.

    bold_items: list[dict] = []

    # Candidate tags: anything that could contain visible text
    for tag in soup.find_all(["p", "div", "span", "b", "strong", "font", "td", "a"]):
        # Get direct text (avoid double-counting nested elements)
        txt = tag.get_text(strip=True)
        if len(txt) < 12 or len(txt) > 500:
            continue

        if not _is_bold(tag):
            continue

        # Check position in full text
        pos = _find_text_pos(full, txt)
        if pos < 0:
            continue
        if not (start_pos <= pos <= end_pos):
            continue

        italic = _is_italic(tag)

        bold_items.append({
            "text": txt,
            "is_italic": italic,
            "pos": pos,
        })

    # ── 3. Deduplicate ───────────────────────────────────────────────────────
    # Prefer shorter (more specific) entries when texts overlap
    bold_items.sort(key=lambda x: x["pos"])

    unique: list[dict] = []
    seen_texts: set[str] = set()
    seen_positions: list[tuple[int, int]] = []  # (start, end) ranges

    for b in bold_items:
        key = b["text"].strip().lower()
        # Skip if this exact text was already added
        if key in seen_texts:
            continue
        # Skip if a substring/superset of an already-seen item at same position
        overlaps = False
        for sp, ep in seen_positions:
            if sp <= b["pos"] <= ep or b["pos"] <= sp <= b["pos"] + len(b["text"]):
                # Check if one text contains the other
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

    # ── 4. Classify: category headers vs sub-risk titles ─────────────────────
    #  Category headers: bold, NOT italic, typically shorter
    #  Sub-risk titles:  bold + italic, typically longer, sentence-like

    categories = [b for b in unique if not b["is_italic"]]
    subrisk_titles = [b for b in unique if b["is_italic"]]

    # If we have both, build hierarchy
    if categories and subrisk_titles:
        result = _group_hierarchical(categories, subrisk_titles)
        if result:
            return result

    # If only italic (no separate category headers): all under one category
    if subrisk_titles and not categories:
        return [{
            "category": "Risk Factors",
            "sub_risks": [b["text"] for b in subrisk_titles],
        }]

    # If only non-italic bold: might be that filing uses bold-only for sub-risks
    # Separate short ones (< 60 chars, no period) as categories, rest as sub-risks
    if categories and not subrisk_titles:
        cats = [b for b in categories if len(b["text"]) < 60 and "." not in b["text"][:50]]
        subs = [b for b in categories if b not in cats]
        if cats and subs:
            return _group_hierarchical(cats, subs)
        # All similar length — treat all as sub-risks
        return [{
            "category": "Risk Factors",
            "sub_risks": [b["text"] for b in categories],
        }]

    # ── 5. Final fallback: paragraph-based ────────────────────────────────────
    return _fallback_paragraph_split(full[start_pos:end_pos])


def _group_hierarchical(
    categories: list[dict],
    subrisk_items: list[dict],
) -> list[dict]:
    """Group sub-risk titles under their nearest preceding category header."""
    result: list[dict] = []

    # Any sub-risks before the first category
    if categories:
        first_cat_pos = categories[0]["pos"]
        orphans = [sr["text"] for sr in subrisk_items if sr["pos"] < first_cat_pos]
        if orphans:
            result.append({"category": "General Risks", "sub_risks": orphans})

    for i, cat in enumerate(categories):
        cat_start = cat["pos"]
        cat_end = categories[i + 1]["pos"] if i + 1 < len(categories) else float("inf")

        subs = [
            sr["text"]
            for sr in subrisk_items
            if cat_start <= sr["pos"] < cat_end
        ]

        if subs:
            result.append({"category": cat["text"], "sub_risks": subs})
        else:
            # Category with no italic sub-risks — include it anyway
            result.append({"category": cat["text"], "sub_risks": []})

    # Remove empty categories
    result = [r for r in result if r["sub_risks"]]
    return result


def _fallback_paragraph_split(raw_text: str) -> list[dict]:
    """If no bold structure found, split by paragraphs as last resort."""
    cleaned = _clean_text(raw_text)
    parts = re.split(r"\n\s*\n", cleaned)
    paras = [p.strip() for p in parts if len(p.strip()) > 40]

    if not paras:
        return []

    # Treat short paragraphs (< 150 chars) as potential titles
    risks: list[dict] = []
    current_cat = "Risk Factors"
    current_subs: list[str] = []

    for p in paras:
        if len(p) < 150 and not p.endswith("."):
            # Looks like a header
            if current_subs:
                risks.append({"category": current_cat, "sub_risks": current_subs})
                current_subs = []
            current_cat = p
        elif len(p) < 300:
            current_subs.append(p)

    if current_subs:
        risks.append({"category": current_cat, "sub_risks": current_subs})

    if not risks and paras:
        # Just dump first 30 paragraphs
        return [{"category": "Risk Factors", "sub_risks": [p for p in paras[:30] if len(p) < 400]}]

    return risks
