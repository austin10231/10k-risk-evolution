from typing import Dict, List

def build_report_payload(
    company: str,
    year: int,
    filing_type: str,
    industry: str,
    item1a_locator: str,
    risk_blocks: List[Dict],
) -> Dict:
    overview = {
        "company_name": company,
        "company_id": company,
        "industry": industry,
        "filing_type": filing_type,
        "fiscal_year": year,
        "source": "SEC EDGAR (HTML filing)",
        "scope": "Item 1A - Risk Factors (text-only MVP)",
        "item1a_locator": item1a_locator,
    }

    return {
        "company_overview": overview,
        "risk_blocks": risk_blocks,
    }
