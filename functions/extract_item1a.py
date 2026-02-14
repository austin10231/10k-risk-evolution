import re
from bs4 import BeautifulSoup

def extract_item_1a_text(html: str):
    """
    MVP extractor:
    - Convert HTML to text
    - Try to locate "Item 1A" section by regex windows
    Returns: (item1a_text, locator_str)
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Normalize spacing
    norm = re.sub(r"[ \t]+", " ", text)

    # Common patterns in 10-K
    start_patterns = [
        r"ITEM\s+1A\.*\s+RISK\s+FACTORS",
        r"Item\s+1A\.*\s+Risk\s+Factors",
    ]
    end_patterns = [
        r"ITEM\s+1B\.*",
        r"Item\s+1B\.*",
        r"ITEM\s+2\.*",
        r"Item\s+2\.*",
    ]

    start_idx = None
    for sp in start_patterns:
        m = re.search(sp, norm, flags=re.IGNORECASE)
        if m:
            start_idx = m.start()
            break

    if start_idx is None:
        # fallback: return first N chars as a "best effort"
        return norm[:12000], "locator=FALLBACK_TOP"

    end_idx = None
    for ep in end_patterns:
        m2 = re.search(ep, norm[start_idx:], flags=re.IGNORECASE)
        if m2:
            end_idx = start_idx + m2.start()
            break

    if end_idx is None:
        end_idx = min(len(norm), start_idx + 40000)

    item1a = norm[start_idx:end_idx].strip()
    locator = f"locator=regex_window[{start_idx}:{end_idx}]"
    return item1a, locator
