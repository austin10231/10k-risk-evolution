"""Auto-bootstrap pipeline for missing 10-K data in Agent flows.

This module fetches a filing from SEC EDGAR, runs extraction + AI enrichment,
and persists the result into existing storage so later agent runs can reuse it.
"""

from __future__ import annotations

from typing import Any

from core.agent import run_agent
from core.bedrock import classify_risks, generate_summary
from core.extractor import extract_item1_overview, extract_item1a_risks
from core.sec_edgar import download_10k_html_for_company_year, build_filing_html_url
from storage.store import add_record, get_result, load_index, save_agent_report


def _safe_year(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def _industry_for_company(company: str, fallback: str = "Other") -> str:
    name = str(company or "").strip()
    if not name:
        return fallback
    recs = [r for r in load_index() if str(r.get("company", "")).strip() == name]
    if not recs:
        return fallback
    latest = sorted(recs, key=lambda r: int(r.get("year", 0) or 0), reverse=True)[0]
    return str(latest.get("industry", "") or fallback)


def _find_existing_record(company: str, year: int):
    comp = str(company or "").strip()
    yy = _safe_year(year)
    if not comp or not yy:
        return None
    for rec in load_index():
        if (
            str(rec.get("company", "")).strip() == comp
            and _safe_year(rec.get("year", 0)) == yy
            and str(rec.get("filing_type", "10-K")).upper() == "10-K"
        ):
            rid = str(rec.get("record_id", "") or "").strip()
            if not rid:
                continue
            payload = get_result(rid)
            if isinstance(payload, dict) and isinstance(payload.get("risks"), list) and payload.get("risks"):
                return rec, payload
    return None


def bootstrap_company_year_10k(
    *,
    company: str,
    year: int,
    ticker: str = "",
    industry: str = "",
    user_query: str = "",
) -> dict:
    """Ensure a company-year filing exists in local storage.

    Returns shape:
      {
        "status": "ok" | "error",
        "source": "cache" | "sec_bootstrap",
        "record": <record dict or None>,
        "result": <result dict or None>,
        "message": <string>,
        "error": <string>,
      }
    """

    comp = str(company or "").strip()
    yy = _safe_year(year)
    tk = str(ticker or "").strip().upper()
    ind = str(industry or "").strip() or _industry_for_company(comp, fallback="Other")

    if not comp or not yy:
        return {
            "status": "error",
            "source": "validation",
            "record": None,
            "result": None,
            "message": "",
            "error": "Company and year are required for auto bootstrap.",
        }

    existing = _find_existing_record(comp, yy)
    if existing:
        rec, result = existing
        return {
            "status": "ok",
            "source": "cache",
            "record": rec,
            "result": result,
            "message": f"Using cached filing data for {comp} {yy}.",
            "error": "",
        }

    html_bytes, sec_meta, sec_err = download_10k_html_for_company_year(
        company_name=comp,
        year=yy,
        ticker=tk,
    )
    if not html_bytes:
        return {
            "status": "error",
            "source": "sec_bootstrap",
            "record": None,
            "result": None,
            "message": "",
            "error": sec_err or f"Could not fetch 10-K for {comp} {yy} from SEC EDGAR.",
        }

    try:
        overview = extract_item1_overview(html_bytes, comp, ind)
        risks_raw = extract_item1a_risks(html_bytes)
    except Exception as e:
        return {
            "status": "error",
            "source": "sec_bootstrap",
            "record": None,
            "result": None,
            "message": "",
            "error": f"Extraction failed: {type(e).__name__}: {e}",
        }

    if not risks_raw:
        return {
            "status": "error",
            "source": "sec_bootstrap",
            "record": None,
            "result": None,
            "message": "",
            "error": "Could not extract Item 1A risks from fetched SEC filing.",
        }

    try:
        classified = classify_risks(risks_raw)
        ai_summary = generate_summary(comp, yy, classified)
        agent_seed_query = user_query.strip() or "Prioritize all risks and identify the top 5 most critical threats"
        agent_report = run_agent(
            user_query=agent_seed_query,
            company=comp,
            year=yy,
            risks=classified,
            compare_data=None,
        )
    except Exception as e:
        return {
            "status": "error",
            "source": "sec_bootstrap",
            "record": None,
            "result": None,
            "message": "",
            "error": f"AI pipeline failed: {type(e).__name__}: {e}",
        }

    overview["year"] = yy
    overview["filing_type"] = "10-K"

    result = {
        "company_overview": overview,
        "risks": classified,
        "ai_summary": ai_summary,
        "agent_report": agent_report,
        "source": "sec_edgar_auto_bootstrap",
        "sec_meta": {
            **(sec_meta if isinstance(sec_meta, dict) else {}),
            "auto_fetch": True,
            "ticker": tk,
            "filing_url": build_filing_html_url(sec_meta if isinstance(sec_meta, dict) else {}),
        },
    }

    try:
        rid = add_record(
            company=comp,
            industry=ind,
            year=yy,
            filing_type="10-K",
            file_bytes=html_bytes,
            file_ext="html",
            result_json=result,
        )
        record = {
            "record_id": rid,
            "company": comp,
            "industry": ind,
            "year": yy,
            "filing_type": "10-K",
            "file_ext": "html",
        }

        if isinstance(agent_report, dict):
            try:
                save_agent_report(
                    company=comp,
                    year=yy,
                    filing_type="10-K",
                    report_json=agent_report,
                )
            except Exception:
                pass

        return {
            "status": "ok",
            "source": "sec_bootstrap",
            "record": record,
            "result": result,
            "message": f"Auto-fetched and processed SEC 10-K for {comp} {yy}.",
            "error": "",
        }
    except Exception as e:
        return {
            "status": "error",
            "source": "sec_bootstrap",
            "record": None,
            "result": None,
            "message": "",
            "error": f"Failed to persist bootstrapped filing: {type(e).__name__}: {e}",
        }
