import re
import uuid
from typing import Dict, List

THEME_RULES = [
    ("cybersecurity", ["cyber", "security breach", "data breach", "ransomware", "privacy"]),
    ("regulatory", ["regulation", "regulatory", "compliance", "law", "antitrust"]),
    ("supply_chain", ["supply", "supplier", "manufacturing", "inventory", "logistics"]),
    ("geopolitical", ["china", "tariff", "sanction", "geopolitical", "trade"]),
    ("competition", ["competition", "competitor", "pricing pressure", "market share"]),
    ("macro", ["inflation", "interest rate", "recession", "macroeconomic"]),
]

def _infer_theme(text: str) -> str:
    t = text.lower()
    for theme, kws in THEME_RULES:
        if any(k in t for k in kws):
            return theme
    return "other"

def build_risk_blocks(item1a_text: str) -> List[Dict]:
    """
    MVP block builder:
    - Split into paragraphs
    - Merge short paras
    - Assign simple theme via keyword rules
    """
    paras = [p.strip() for p in re.split(r"\n\s*\n", item1a_text) if p.strip()]
    merged = []
    buf = ""
    for p in paras:
        if len(p) < 180:
            buf = (buf + " " + p).strip()
        else:
            if buf:
                merged.append(buf)
                buf = ""
            merged.append(p)
    if buf:
        merged.append(buf)

    blocks = []
    for idx, p in enumerate(merged):
        theme = _infer_theme(p)
        title = p[:80].replace("\n", " ")
        blocks.append({
            "block_id": str(uuid.uuid4()),
            "risk_theme": theme,
            "title": title,
            "risk_text": p,
            "evidence_pointer": f"paragraph_index={idx}",
        })
    return blocks
