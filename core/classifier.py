"""

#Split Item 1A text into risk blocks and assign keyword-based themes.


import re
import uuid

# ── Theme keyword map ─────────────────────────────────────────────────────────
THEME_KEYWORDS: dict[str, list[str]] = {
    "cybersecurity": [
        "cyber", "data breach", "information security", "hacking",
        "ransomware", "data protection", "phishing", "malware",
    ],
    "regulatory": [
        "regulat", "compliance", "government", "legislation",
        "law ", " legal", "SEC ", "FDA ", "antitrust", "enforcement",
    ],
    "supply_chain": [
        "supply chain", "supplier", "logistics", "procurement",
        "shortage", "inventory", "raw material",
    ],
    "geopolitical": [
        "geopolit", "sanction", "tariff", "trade war",
        "international conflict", "foreign government", "political instability",
    ],
    "competition": [
        "competi", "market share", "rival", "pricing pressure",
        "new entrant", "disrupt",
    ],
    "macro": [
        "macroeconom", "recession", "inflation", "interest rate",
        "economic downturn", "GDP", "unemployment", "monetary policy",
    ],
    "financial": [
        "liquidity", "credit risk", "debt", "capital adequacy",
        "financial condition", "cash flow", "impairment", "goodwill",
    ],
    "technology": [
        "technolog", "innovation", "obsolescence", "digital transformation",
        "artificial intelligence", " AI ", "cloud computing",
    ],
    "environmental": [
        "climate", "environmental", "sustainability", "emission",
        "carbon", " ESG", "natural disaster", "weather",
    ],
    "talent": [
        "talent", "employee", "workforce", "labor",
        "retention", "hiring", "key personnel", "human capital",
    ],
    "litigation": [
        "litigation", "lawsuit", "legal proceeding", "class action",
        "patent", "intellectual property",
    ],
    "reputational": [
        "reputation", "brand", "public perception", "media",
        "social media", "consumer trust",
    ],
}


def _classify_theme(text: str) -> str:
    lower = text.lower()
    scores: dict[str, int] = {}
    for theme, keywords in THEME_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in lower)
        if score > 0:
            scores[theme] = score
    if not scores:
        return "other"
    return max(scores, key=scores.get)


def build_risk_blocks(item1a_text: str) -> list[dict]:
    
    #Split item1a_text into risk blocks and classify each.

   # Heuristic:
      #1. Split on double-newline boundaries.
     # 2. Drop very short fragments (< 40 chars).
      #3. Merge consecutive tiny paragraphs into one block.
    
    raw = re.split(r"\n\s*\n", item1a_text)
    paragraphs = [p.strip() for p in raw if len(p.strip()) > 40]

    # Merge short consecutive paragraphs (< 200 chars)
    merged: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) < 300 and buf:
            buf += "\n\n" + p
        else:
            if buf:
                merged.append(buf)
            buf = p
    if buf:
        merged.append(buf)

    blocks: list[dict] = []
    for i, text in enumerate(merged):
        theme = _classify_theme(text)
        title = text[:80].replace("\n", " ").strip()
        if len(text) > 80:
            title += " …"
        blocks.append(
            {
                "block_id": str(uuid.uuid4()),
                "block_index": i,
                "risk_theme": theme,
                "title": title,
                "risk_text": text,
                "evidence_pointer": f"paragraph_{i}",
            }
        )
    return blocks


"""
