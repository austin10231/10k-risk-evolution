"""
Extract Item 1A (Risk Factors) from SEC 10-K filing HTML.

Strategy:
  1. Parse HTML with BeautifulSoup + lxml.
  2. Flatten to text.
  3. Regex-search for "Item 1A" start and "Item 1B" / "Item 2" end.
  4. Return the windowed text and locator metadata.
"""

import re
from bs4 import BeautifulSoup


_START_PATTERNS = [
    re.compile(r"(?i)item[\s\xa0]+1a[\.\:\s\-–—]+risk\s+factors"),
    re.compile(r"(?i)item[\s\xa0]+1a[\.\s]"),
]

_END_PATTERNS = [
    re.compile(r"(?i)item[\s\xa0]+1b[\.\:\s\-–—]"),
    re.compile(r"(?i)item[\s\xa0]+2[\.\:\s\-–—]"),
]


def extract_item1a(html_bytes: bytes) -> tuple:
    """
    Returns (item1a_text, locator_dict) on success,
    or (None, error_message_str) on failure.
    """
    soup = BeautifulSoup(html_bytes, "lxml")

    # Remove script/style noise
    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    # ── Find start ────────────────────────────────────────────────────────────
    start_pos = None
    for pat in _START_PATTERNS:
        m = pat.search(text)
        if m:
            start_pos = m.start()
            break

    if start_pos is None:
        return None, (
            "Could not locate 'Item 1A – Risk Factors' in the document. "
            "Make sure you uploaded an SEC 10-K filing HTML."
        )

    # ── Find end ──────────────────────────────────────────────────────────────
    # Search after a small offset to skip the header itself
    search_from = start_pos + 80
    end_pos = len(text)

    for pat in _END_PATTERNS:
        m = pat.search(text, pos=search_from)
        if m:
            candidate = m.start()
            if candidate < end_pos:
                end_pos = candidate
            break  # take the first match of the first matching pattern

    item1a_text = text[start_pos:end_pos].strip()

    # Sanity: if text is suspiciously short, warn but still return
    locator = {
        "start_char": start_pos,
        "end_char": end_pos,
        "extracted_length": len(item1a_text),
        "method": "regex_window (Item 1A → Item 1B/2)",
    }

    return item1a_text, locator
