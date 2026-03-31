"""SEC EDGAR helpers used by financial table auto-extraction flows."""

from __future__ import annotations

import json
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

SEC_USER_AGENT = "RiskLens App contact@risklens.com"
SEC_REQUEST_DELAY_SEC = 0.5


def _sec_headers():
    return {"User-Agent": SEC_USER_AGENT}


def _sec_ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _sec_get_json(url: str):
    req = Request(url, headers=_sec_headers(), method="GET")
    try:
        with urlopen(req, timeout=30, context=_sec_ssl_context()) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    finally:
        time.sleep(SEC_REQUEST_DELAY_SEC)


def _sec_get_bytes(url: str):
    req = Request(url, headers=_sec_headers(), method="GET")
    try:
        with urlopen(req, timeout=30, context=_sec_ssl_context()) as resp:
            return resp.read()
    finally:
        time.sleep(SEC_REQUEST_DELAY_SEC)


def _extract_cik_from_search_payload(payload: dict) -> str:
    candidates = []
    hits = payload.get("hits", {}).get("hits", [])
    for hit in hits:
        src = hit.get("_source", {}) if isinstance(hit, dict) else {}
        for key in ("ciks", "cik", "entityCik"):
            val = src.get(key)
            if isinstance(val, list):
                for item in val:
                    s = str(item).strip()
                    if s.isdigit():
                        candidates.append(s)
            elif val is not None:
                s = str(val).strip()
                if s.isdigit():
                    candidates.append(s)

    if not candidates:
        return ""
    return str(candidates[0]).zfill(10)


def find_cik(company_name: str, ticker: str = "") -> str:
    queries = [f'"{company_name}"']
    if ticker:
        queries.append(f'"{company_name}" {ticker}')
        queries.append(ticker)

    for q_raw in queries:
        q = quote(q_raw)
        payload = _sec_get_json(f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=10-K")
        cik = _extract_cik_from_search_payload(payload)
        if cik:
            return cik
    return ""


def _submissions_for_cik(cik_10: str) -> dict:
    return _sec_get_json(f"https://data.sec.gov/submissions/CIK{cik_10}.json")


def _select_filing_for_year(submissions: dict, year: int):
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    total = min(len(forms), len(filing_dates), len(accessions), len(primary_docs))
    matches = []
    for i in range(total):
        if str(forms[i]).upper() != "10-K":
            continue
        filing_date = str(filing_dates[i] or "")
        if len(filing_date) < 4:
            continue
        try:
            fy = int(filing_date[:4])
        except Exception:
            continue
        if int(fy) != int(year):
            continue
        matches.append(
            {
                "year": int(fy),
                "filing_date": filing_date,
                "accession_number": str(accessions[i]),
                "primary_document": str(primary_docs[i]),
            }
        )
    if not matches:
        return None
    matches.sort(key=lambda x: x.get("filing_date", ""), reverse=True)
    return matches[0]


def _is_valid_pdf_doc_name(name: str) -> bool:
    n = str(name or "").strip().lower()
    if not n.endswith(".pdf"):
        return False
    if any(k in n for k in ("xbrl", "_cal", "_def", "_lab", "_pre", ".xml", "schema")):
        return False
    return True


def _is_valid_html_doc_name(name: str) -> bool:
    n = str(name or "").strip().lower()
    if not (n.endswith(".htm") or n.endswith(".html")):
        return False
    if any(k in n for k in ("xbrl", "_cal", "_def", "_lab", "_pre", ".xml", "schema", "graphic")):
        return False
    return True


def _pick_primary_pdf_doc(primary_document: str, index_json: dict) -> str:
    primary = str(primary_document or "").strip()
    if _is_valid_pdf_doc_name(primary):
        return primary

    candidates = []
    for it in index_json.get("directory", {}).get("item", []):
        nm = str(it.get("name", "")).strip()
        if not _is_valid_pdf_doc_name(nm):
            continue
        score = 100
        low = nm.lower()
        if "10-k" in low or "10k" in low:
            score -= 40
        if "form" in low:
            score -= 20
        if "index" in low:
            score += 25
        score += min(len(nm), 80)
        candidates.append((score, nm))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def _pick_primary_html_doc(primary_document: str, index_json: dict) -> str:
    primary = str(primary_document or "").strip()
    if _is_valid_html_doc_name(primary):
        return primary

    candidates = []
    for it in index_json.get("directory", {}).get("item", []):
        nm = str(it.get("name", "")).strip()
        if not _is_valid_html_doc_name(nm):
            continue
        score = 100
        low = nm.lower()
        if "10-k" in low or "10k" in low:
            score -= 40
        if "form" in low:
            score -= 20
        if "index" in low:
            score += 25
        score += min(len(nm), 80)
        candidates.append((score, nm))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def download_filing_pdf_by_cik(cik_10: str, accession_number: str, primary_document: str):
    cik_no_leading_zero = str(int(cik_10))
    accession_no_dashes = str(accession_number).replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zero}/{accession_no_dashes}"
    try:
        index_json = _sec_get_json(f"{base}/index.json")
    except Exception:
        index_json = {}

    doc_name = _pick_primary_pdf_doc(primary_document, index_json)
    if not doc_name:
        return None, "", "No PDF main filing document found in filing index."

    try:
        pdf_bytes = _sec_get_bytes(f"{base}/{doc_name}")
    except (HTTPError, URLError, TimeoutError) as e:
        return None, doc_name, f"Failed to download filing PDF: {e}"
    except Exception as e:
        return None, doc_name, f"Failed to download filing PDF: {e}"
    return pdf_bytes, doc_name, ""


def download_filing_html_by_cik(cik_10: str, accession_number: str, primary_document: str):
    cik_no_leading_zero = str(int(cik_10))
    accession_no_dashes = str(accession_number).replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zero}/{accession_no_dashes}"
    try:
        index_json = _sec_get_json(f"{base}/index.json")
    except Exception:
        index_json = {}

    doc_name = _pick_primary_html_doc(primary_document, index_json)
    if not doc_name:
        return None, "", "No HTML main filing document found in filing index."

    try:
        html_bytes = _sec_get_bytes(f"{base}/{doc_name}")
    except (HTTPError, URLError, TimeoutError) as e:
        return None, doc_name, f"Failed to download filing HTML: {e}"
    except Exception as e:
        return None, doc_name, f"Failed to download filing HTML: {e}"
    return html_bytes, doc_name, ""


def download_10k_pdf_for_company_year(company_name: str, year: int, ticker: str = ""):
    cik = find_cik(company_name, ticker)
    if not cik:
        return None, {}, "Could not find CIK from SEC EDGAR."

    try:
        submissions = _submissions_for_cik(cik)
    except Exception as e:
        return None, {"cik": cik}, f"Failed to fetch SEC submissions for CIK {cik}: {e}"

    filing = _select_filing_for_year(submissions, int(year))
    if not filing:
        return None, {"cik": cik}, f"No 10-K filing found for {company_name} in {year}."

    pdf_bytes, doc_name, err = download_filing_pdf_by_cik(
        cik_10=cik,
        accession_number=filing.get("accession_number", ""),
        primary_document=filing.get("primary_document", ""),
    )
    meta = {
        "cik": cik,
        "ticker": str(ticker or "").upper(),
        "filing_date": filing.get("filing_date", ""),
        "accession_number": filing.get("accession_number", ""),
        "primary_document": filing.get("primary_document", ""),
        "downloaded_document": doc_name,
        "year": int(year),
    }
    if not pdf_bytes:
        if err and "No PDF main filing document found" in err:
            err = (
                "No PDF main filing document found in filing index. "
                "Some SEC 10-K filings are HTML-only; please use manual PDF upload for this filing."
            )
        return None, meta, err or "Failed to download 10-K PDF from SEC."
    return pdf_bytes, meta, ""


def build_filing_html_url(meta: dict) -> str:
    """Build SEC filing document URL from metadata."""
    try:
        cik = str(meta.get("cik", "") or "").strip()
        accession = str(meta.get("accession_number", "") or "").strip()
        doc = str(meta.get("primary_document", "") or meta.get("downloaded_document", "") or "").strip()
        if not cik or not accession or not doc:
            return ""
        cik_no_leading_zero = str(int(cik))
        accession_no_dashes = accession.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zero}/{accession_no_dashes}/{doc}"
    except Exception:
        return ""


def download_10k_html_for_company_year(company_name: str, year: int, ticker: str = ""):
    cik = find_cik(company_name, ticker)
    if not cik:
        return None, {}, "Could not find CIK from SEC EDGAR."

    try:
        submissions = _submissions_for_cik(cik)
    except Exception as e:
        return None, {"cik": cik}, f"Failed to fetch SEC submissions for CIK {cik}: {e}"

    filing = _select_filing_for_year(submissions, int(year))
    if not filing:
        return None, {"cik": cik}, f"No 10-K filing found for {company_name} in {year}."

    html_bytes, doc_name, err = download_filing_html_by_cik(
        cik_10=cik,
        accession_number=filing.get("accession_number", ""),
        primary_document=filing.get("primary_document", ""),
    )
    meta = {
        "cik": cik,
        "ticker": str(ticker or "").upper(),
        "filing_date": filing.get("filing_date", ""),
        "accession_number": filing.get("accession_number", ""),
        "primary_document": filing.get("primary_document", ""),
        "downloaded_document": doc_name,
        "year": int(year),
    }
    if not html_bytes:
        return None, meta, err or "Failed to download 10-K HTML from SEC."
    return html_bytes, meta, ""
