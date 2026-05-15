"""Domain knowledge tables used by the Compare canonicalizer.

Three pieces:
1. `BOILERPLATE_PREFIXES`   — SEC risk-factor preambles to strip before scoring.
2. `STOP_WORDS`             — connective words that add no signal to token sets.
3. `SYNONYM_GROUPS`         — clusters of surface forms collapsed to a canonical
                              token (used by `compare_text._replace_synonyms`).

Keep entries lowercased; canonicalisation lowercases its input first.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


# Phrases that frequently open a risk-factor heading and carry no
# discriminative meaning. The canonicalizer strips at most one match per
# title (the longest one), so order longer phrases earlier in each list.
BOILERPLATE_PREFIXES: List[str] = [
    "risks related to our",
    "risks relating to our",
    "risks associated with our",
    "risks related to the",
    "risks relating to the",
    "risks associated with the",
    "risks related to",
    "risks relating to",
    "risks associated with",
    "risk factors related to",
    "risk factors relating to",
    "we may not be able to",
    "we have not been able to",
    "we are unable to",
    "we may be unable to",
    "we may fail to",
    "we are subject to",
    "we are exposed to",
    "we are dependent on",
    "we depend on",
    "we rely on",
    "we operate in",
    "we may experience",
    "we may incur",
    "we could be",
    "we are not",
    "we have",
    "we may",
    "we are",
    "our ability to",
    "our failure to",
    "our inability to",
    "our business depends on",
    "our business is",
    "our business may",
    "our future",
    "our",
    "the company is",
    "the company may",
    "the company has",
    "the company's",
    "the company",
    "any failure to",
    "any inability to",
    "failure to comply with",
    "failure to attract",
    "failure to retain",
    "failure to",
    "inability to",
    "if we are unable to",
    "if we fail to",
    "if we cannot",
    "if we do not",
    "if our",
    "if we",
    "because we",
    "changes in",
    "adverse changes in",
    "a failure of",
    "a failure to",
]


# Tokens that survive canonicalisation but should not be counted in
# similarity overlap (Jaccard, token-set, label-overlap). English
# function words plus a few SEC-doc connectives.
STOP_WORDS: set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "of", "in", "on", "at",
    "to", "for", "by", "with", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "may",
    "might", "must", "shall", "should", "would", "could", "can", "will",
    "not", "no", "nor", "so", "than", "that", "this", "these", "those",
    "we", "us", "our", "ours", "you", "your", "they", "them", "their",
    "it", "its", "any", "all", "such", "other", "others", "some",
    "from", "into", "onto", "upon", "about", "over", "under", "out",
    "up", "down", "off", "during", "while", "when", "where", "which",
    "who", "whom", "what", "how", "also", "very", "more", "most",
    "less", "least", "many", "much", "few", "fewer", "etc",
    "company", "companies", "business", "businesses",
    "operation", "operations", "operating", "operate",
    "result", "results", "resulting", "resulted",
    "affect", "affects", "affected", "affecting",
    "adverse", "adversely",
    "material", "materially",
    "significant", "significantly",
    "potential", "potentially",
}


# Each tuple is `(canonical_token, list_of_surface_forms)`. The
# canonicalizer replaces every multi-word surface form first (longest
# match wins per group), then each single-word variant. The canonical
# token itself is what ends up in the token bag.
#
# Coverage targets: cyber/IT, supplier/vendor, FX/currency, litigation,
# talent, regulation, IP, M&A, supply chain, climate, pandemic,
# competition, demand, inflation, debt/leverage, R&D, geopolitics.
SYNONYM_GROUPS: List[Tuple[str, List[str]]] = [
    ("infosec", [
        "information security", "information technology security",
        "cyber security", "cybersecurity", "cyber attack", "cyber attacks",
        "cyber incident", "cyber incidents", "cyber threat", "cyber threats",
        "data breach", "data breaches", "security breach", "security breaches",
        "ransomware", "phishing", "malware", "hacker", "hackers",
        "information system breach", "it security",
    ]),
    ("itsystem", [
        "information technology system", "information technology systems",
        "it systems", "it system", "it infrastructure", "computer systems",
        "computer system", "technology infrastructure",
    ]),
    ("dataprivacy", [
        "data privacy", "data protection", "personal data", "personal information",
        "privacy law", "privacy laws", "privacy regulation", "privacy regulations",
        "gdpr", "ccpa", "consumer privacy",
    ]),
    ("supplier", [
        "third party", "third parties", "third-party", "third-parties",
        "supplier", "suppliers", "vendor", "vendors",
        "subcontractor", "subcontractors", "outsourced provider",
        "outsourcing partner", "service provider", "service providers",
    ]),
    ("supplychain", [
        "supply chain", "supply chains", "supply-chain", "logistics network",
        "distribution network", "raw material", "raw materials",
    ]),
    ("currency", [
        "foreign exchange", "foreign currency", "currency exchange",
        "exchange rate", "exchange rates", "fx rate", "fx rates", "fx",
        "currency fluctuation", "currency fluctuations",
    ]),
    ("interestrate", [
        "interest rate", "interest rates", "rising rates",
        "benchmark rate", "benchmark rates",
    ]),
    ("inflation", [
        "inflation", "inflationary", "rising prices", "price increase",
        "price increases", "cost inflation",
    ]),
    ("liquidity", [
        "liquidity", "cash flow", "cash flows", "working capital",
        "access to capital", "capital resources",
    ]),
    ("debt", [
        "indebtedness", "leverage", "leveraged", "outstanding debt",
        "debt obligation", "debt obligations", "credit facility",
        "credit facilities", "refinancing", "refinance",
    ]),
    ("litigation", [
        "lawsuit", "lawsuits", "litigation", "legal proceeding",
        "legal proceedings", "claims", "class action", "class actions",
        "regulatory investigation", "regulatory investigations",
    ]),
    ("regulation", [
        "regulation", "regulations", "regulatory requirement",
        "regulatory requirements", "regulatory change", "regulatory changes",
        "compliance with law", "compliance with laws",
        "applicable law", "applicable laws", "government regulation",
        "government regulations",
    ]),
    ("antitrust", [
        "antitrust", "anti trust", "competition law", "competition laws",
    ]),
    ("anticorruption", [
        "anti corruption", "anti-corruption", "bribery", "fcpa",
        "foreign corrupt practices act",
    ]),
    ("sanctions", [
        "sanction", "sanctions", "export control", "export controls",
        "trade restriction", "trade restrictions", "embargo", "embargoes",
    ]),
    ("ip", [
        "intellectual property", "patent", "patents", "trademark",
        "trademarks", "copyright", "copyrights", "trade secret",
        "trade secrets", "ip right", "ip rights",
    ]),
    ("talent", [
        "key personnel", "key employee", "key employees", "key talent",
        "skilled employee", "skilled employees", "skilled workforce",
        "qualified personnel", "attract and retain", "retain and attract",
        "labor shortage", "labor shortages", "talent",
    ]),
    ("laborrelations", [
        "union", "unions", "collective bargaining", "labor relation",
        "labor relations", "work stoppage", "work stoppages", "strike",
        "strikes",
    ]),
    ("climate", [
        "climate change", "climate-related", "climate related",
        "extreme weather", "natural disaster", "natural disasters",
        "global warming", "greenhouse gas", "greenhouse gases",
    ]),
    ("esg", [
        "esg", "sustainability", "environmental social governance",
        "carbon emission", "carbon emissions", "carbon footprint",
        "net zero", "net-zero", "decarbonization",
    ]),
    ("pandemic", [
        "covid", "covid-19", "coronavirus", "pandemic", "epidemic",
        "public health emergency",
    ]),
    ("geopolitics", [
        "geopolitical", "geopolitics", "political instability",
        "armed conflict", "war", "russia ukraine", "israel hamas",
        "taiwan strait", "trade war", "tariff", "tariffs",
    ]),
    ("competition", [
        "competition", "competitor", "competitors", "competitive pressure",
        "competitive pressures", "competitive landscape", "market share",
    ]),
    ("demand", [
        "demand for our product", "demand for our products",
        "demand for our service", "demand for our services",
        "consumer demand", "customer demand", "market demand",
    ]),
    ("rnd", [
        "research and development", "r&d", "product development",
        "new product introduction", "innovation",
    ]),
    ("ma", [
        "acquisition", "acquisitions", "merger", "mergers",
        "business combination", "business combinations", "divestiture",
        "divestitures", "joint venture", "joint ventures",
    ]),
    ("dilution", [
        "dilution", "issuance of additional shares", "additional issuance",
        "follow on offering", "follow-on offering", "secondary offering",
    ]),
    ("stockprice", [
        "stock price", "share price", "market price of our common stock",
        "trading price", "price volatility",
    ]),
    ("internalcontrol", [
        "internal control", "internal controls", "material weakness",
        "material weaknesses", "sarbanes oxley", "sarbanes-oxley", "sox",
        "disclosure control", "disclosure controls",
    ]),
    ("tax", [
        "tax law", "tax laws", "tax legislation", "tax rate", "tax rates",
        "tax authority", "tax authorities", "transfer pricing",
    ]),
    ("insurance", [
        "insurance coverage", "insurance policy", "insurance policies",
        "self insurance", "self-insurance", "reinsurance",
    ]),
    ("environmental", [
        "environmental liability", "environmental liabilities",
        "environmental remediation", "hazardous material",
        "hazardous materials", "pollution", "spill", "spills",
    ]),
    ("realestate", [
        "lease", "leases", "real estate", "property", "properties",
        "facility", "facilities",
    ]),
    ("productsafety", [
        "product liability", "product recall", "product recalls",
        "product safety", "product defect", "product defects",
    ]),
]


def synonym_lookup() -> Dict[str, str]:
    """Flatten SYNONYM_GROUPS into surface -> canonical map. Multi-word
    surface forms keep their internal spaces; the text canonicalizer
    walks the longer entries first.
    """
    out: Dict[str, str] = {}
    for canonical, surfaces in SYNONYM_GROUPS:
        for s in surfaces:
            key = s.strip().lower()
            if not key:
                continue
            out[key] = canonical
    return out
