"""Analyze page — Library + New Analysis. Readable text display."""

import streamlit as st
import json
import time
import ssl
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from storage.store import (
    load_index, add_record, get_result, filter_records, delete_record,
    _s3_write, RESULTS_PREFIX, save_agent_report,
)
from core.extractor import (
    extract_item1_overview, extract_item1a_risks,
    extract_text_from_pdf, extract_item1_overview_from_text,
    extract_item1a_risks_from_text,
    extract_item1_overview_bedrock, extract_item1a_risks_bedrock,
)
from core.bedrock import classify_risks, generate_summary
from core.comprehend import enrich_risks_with_comprehend
from core.agent import run_agent
from components.filters import library_filters

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]

SEC_USER_AGENT = "RiskLens App contact@risklens.com"
SEC_REQUEST_DELAY_SEC = 0.5


def _sec_headers():
    return {
        "User-Agent": SEC_USER_AGENT,
    }


def _sec_ssl_context():
    """Use certifi CA bundle to avoid local system certificate-chain issues."""
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

    # fallback: recursive key scan for anything named like cik
    def _walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if "cik" in str(k).lower():
                    if isinstance(v, list):
                        for x in v:
                            sx = str(x).strip()
                            if sx.isdigit():
                                candidates.append(sx)
                    else:
                        sv = str(v).strip()
                        if sv.isdigit():
                            candidates.append(sv)
                _walk(v)
        elif isinstance(obj, list):
            for it in obj:
                _walk(it)

    _walk(payload)
    if not candidates:
        return ""
    # Keep first candidate; SEC search is usually relevance-sorted.
    return str(candidates[0]).zfill(10)


def _lookup_cik(company_name: str, ticker: str = "") -> str:
    queries = [f'"{company_name}"']
    if ticker:
        queries.append(f'"{company_name}" {ticker}')
        queries.append(ticker)

    for q_raw in queries:
        q = quote(q_raw)
        url = f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=10-K"
        payload = _sec_get_json(url)
        cik = _extract_cik_from_search_payload(payload)
        if cik:
            return cik
    return ""


def _submissions_for_cik(cik_10: str) -> dict:
    url = f"https://data.sec.gov/submissions/CIK{cik_10}.json"
    return _sec_get_json(url)


def _filings_in_year_range(submissions: dict, start_year: int, end_year: int):
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    if not forms:
        return []

    out = []
    total = min(len(forms), len(filing_dates), len(accessions), len(primary_docs))
    for i in range(total):
        if str(forms[i]).upper() != "10-K":
            continue
        filing_date = str(filing_dates[i] or "")
        if len(filing_date) < 4:
            continue
        try:
            year = int(filing_date[:4])
        except Exception:
            continue
        if year < int(start_year) or year > int(end_year):
            continue
        out.append({
            "year": year,
            "filing_date": filing_date,
            "accession_number": str(accessions[i]),
            "primary_document": str(primary_docs[i]),
        })
    out.sort(key=lambda x: (x["year"], x["filing_date"]))
    return out


def _is_valid_html_doc_name(name: str) -> bool:
    n = str(name or "").strip().lower()
    if not (n.endswith(".htm") or n.endswith(".html")):
        return False
    disallow_keywords = [
        "xbrl", "_cal", "_def", "_lab", "_pre", ".xml", "schema", "exhibit", "graphic",
    ]
    if any(k in n for k in disallow_keywords):
        return False
    return True


def _pick_primary_html_doc(primary_document: str, index_json: dict) -> str:
    primary = str(primary_document or "").strip()
    if _is_valid_html_doc_name(primary):
        return primary

    items = index_json.get("directory", {}).get("item", [])
    candidates = []
    for it in items:
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


def _download_filing_html_by_cik(cik_10: str, accession_number: str, primary_document: str):
    cik_no_leading_zero = str(int(cik_10))
    accession_no_dashes = str(accession_number).replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zero}/{accession_no_dashes}"
    index_url = f"{base}/index.json"
    try:
        idx = _sec_get_json(index_url)
    except Exception:
        idx = {}
    doc_name = _pick_primary_html_doc(primary_document, idx)
    if not doc_name:
        return None, "", "No HTML main filing document found in filing index."

    html_url = f"{base}/{doc_name}"
    try:
        html_bytes = _sec_get_bytes(html_url)
    except (HTTPError, URLError, TimeoutError) as e:
        return None, doc_name, f"Failed to download filing HTML: {e}"
    except Exception as e:
        return None, doc_name, f"Failed to download filing HTML: {e}"
    return html_bytes, doc_name, ""


def _auto_pipeline_for_html(company: str, industry: str, year: int, html_bytes: bytes):
    overview = extract_item1_overview(html_bytes, company.strip(), industry)
    risks = extract_item1a_risks(html_bytes)
    if not risks:
        return None, "Could not extract risks from Item 1A."

    classified = classify_risks(risks)
    summary = generate_summary(company.strip(), int(year), classified)
    agent_query = "Prioritize all risks and identify the top 5 most critical threats"
    agent_report = run_agent(
        user_query=agent_query,
        company=company.strip(),
        year=int(year),
        risks=classified,
        compare_data=None,
    )

    overview["year"] = int(year)
    overview["filing_type"] = "10-K"
    result = {
        "company_overview": overview,
        "risks": classified,
        "ai_summary": summary,
        "agent_report": agent_report,
        "source": "sec_edgar_auto_fetch",
    }
    return result, ""


def _count_sub_risks(risks):
    return sum(len(c.get("sub_risks", [])) for c in risks)


def _show_output(result, key):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")
    comprehend_meta = result.get("comprehend_meta", {})

    st.markdown(
        f"**{ov.get('company', '—')}** · {ov.get('year', '—')} · "
        f"**{len(risks)}** risk categories · "
        f"**{_count_sub_risks(risks)}** risk items"
    )

    # AI Summary at top
    if ai_summary:
        st.markdown('<div class="section-header">🤖 AI Executive Summary</div>', unsafe_allow_html=True)
        st.info(ai_summary)
        if comprehend_meta:
            if comprehend_meta.get("enabled"):
                st.caption(
                    "Comprehend enriched "
                    f"{comprehend_meta.get('enriched', 0)}/{comprehend_meta.get('processed', 0)} risk items."
                )
            else:
                st.caption(f"Comprehend skipped: {comprehend_meta.get('error', 'unknown reason')}")

    # Company Overview
    st.markdown('<div class="section-header">🏢 Company Overview</div>', unsafe_allow_html=True)
    st.markdown(f"**Company:** {ov.get('company', '—')}")
    st.markdown(f"**Industry:** {ov.get('industry', '—')}")
    st.markdown(f"**Year:** {ov.get('year', '—')} · **Filing:** {ov.get('filing_type', '—')}")
    bg = ov.get("background", "")
    if bg:
        st.markdown(f"**Background:** {bg}")

    # Risk Categories
    # Risk Categories
    st.markdown(f'<div class="section-header">⚠️ Risk Categories ({len(risks)})</div>', unsafe_allow_html=True)
    for cat_block in risks:
        cat_name = cat_block.get("category", "Unknown")
        subs = cat_block.get("sub_risks", [])
        sub_count = len(subs)

        if subs and isinstance(subs[0], dict):
            with st.expander(f"**{cat_name}** ({sub_count} risks)", expanded=False):
                for s in subs:
                    labels = s.get("labels", [])
                    tags = s.get("tags", [])
                    label_str = " · ".join(f"`{l}`" for l in labels) if labels else ""
                    tag_str = " · ".join(f"`{t}`" for t in tags[:6]) if tags else ""
                    title = s.get("title", "")
                    st.markdown(f"- {title}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
                    if tag_str:
                        st.caption(f"   Tags: {tag_str}")
        else:
            if subs:
                with st.expander(f"**{cat_name}** ({sub_count} risks)", expanded=False):
                    for s in subs:
                        title = str(s or "").strip()
                        if title:
                            st.markdown(f"- {title}")
            else:
                st.markdown(f"- **{cat_name}** — 0 risk items")

    # Download at bottom
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"{ov.get('company','export')}_{ov.get('year','')}.json",
        mime="application/json",
        key=f"dl_{key}",
        use_container_width=True,
    )


def _run_ai(result, record_id):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])

    with st.spinner("🤖 Classifying risks with AI …"):
        classified = classify_risks(risks)
    with st.spinner("🤖 Extracting entities and key phrases with Comprehend …"):
        enriched_risks, comprehend_meta = enrich_risks_with_comprehend(classified)
    result["risks"] = enriched_risks
    result["comprehend_meta"] = comprehend_meta

    with st.spinner("🤖 Generating executive summary …"):
        summary = generate_summary(
            ov.get("company", ""), ov.get("year", 0), enriched_risks
        )
    result["ai_summary"] = summary

    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )

    st.session_state["last_analyze_result"] = result
    st.rerun()


def render():
    tab_lib, tab_new = st.tabs(["📚 Library", "➕ New Analysis"])

    with tab_lib:
        index = load_index()
        if not index:
            st.info("No records yet. Switch to **New Analysis** to upload a filing.")
        else:
            flt = library_filters(index, key_prefix="lib")
            filtered = filter_records(
                industry=flt["industry"],
                company=flt["company"],
                year=flt["year"],
                filing_type=flt["filing_type"],
                fmt=flt["format"],
            )
            if not filtered:
                st.warning("No records match the current filters.")
            else:
                labels = [
                    f"{r['company']} | {r['year']} | {r['filing_type']} | {r['industry']} | ({r.get('file_ext', 'html').upper()})"
                    for r in filtered
                ]
                sel = st.selectbox(
                    "Select a record", range(len(labels)),
                    format_func=lambda i: labels[i], key="lib_select",
                )
                rec = filtered[sel]

                if st.button(
                    "🗑️ Delete this record",
                    key=f"del_{rec['record_id']}",
                    type="secondary",
                ):
                    delete_record(rec["record_id"])
                    st.success("Record deleted.")
                    st.rerun()

                result = get_result(rec["record_id"])
                if result is None:
                    st.error("Result JSON not found.")
                else:
                    st.divider()

                    # AI button at top
                    if not result.get("ai_summary"):
                        if st.button(
                            "🤖 AI Summarize",
                            key=f"ai_lib_{rec['record_id']}",
                        ):
                            _run_ai(result, rec["record_id"])

                    _show_output(result, key=f"lib_{rec['record_id']}")

    with tab_new:
        mode_upload, mode_auto = st.tabs(["📄 Upload Filing", "🛰️ Auto Fetch from SEC EDGAR"])

        with mode_upload:
            col_input, col_output = st.columns([2, 3])

            with col_input:
                st.markdown("##### Inputs")
                uploaded = st.file_uploader(
                    "Upload filing (HTML or PDF)",
                    type=["html", "htm", "pdf"],
                    key="new_upload",
                )
                year = st.selectbox(
                    "Filing Year", list(range(2025, 2009, -1)), key="new_year",
                )
                company = st.text_input("Company Name", key="new_company")
                industry = st.selectbox("Industry", INDUSTRIES, key="new_industry")
                filing_type = st.selectbox(
                    "Filing Type", ["10-K", "10-Q (coming soon)"], key="new_ftype",
                )
                extraction_mode = st.selectbox(
                    "Extraction Mode",
                    ["Standard", "AI-Enhanced"],
                    index=0,
                    key="new_extract_mode",
                    help="Standard uses existing BeautifulSoup rules. AI-Enhanced uses Bedrock with automatic fallback.",
                )
                run = st.button(
                    "🚀 Extract & Save",
                    key="btn_run_analyze", use_container_width=True,
                )
                st.caption(
                    "Tip: HTML works best for structured extraction. "
                    "PDF uses AWS Textract for text extraction."
                )

            with col_output:
                if "last_analyze_result" in st.session_state:
                    res = st.session_state["last_analyze_result"]
                    rid = st.session_state.get("last_analyze_rid", "x")

                    # AI button at top
                    if not res.get("ai_summary"):
                        if st.button(
                            "🤖 AI Summarize",
                            key=f"ai_new_{rid}",
                        ):
                            _run_ai(res, rid)

                    _show_output(res, key=f"new_{rid}")

            if run:
                if not company.strip():
                    st.error("Please enter a company name.")
                    return
                if uploaded is None:
                    st.error("Please upload a file.")
                    return
                if "coming soon" in filing_type:
                    st.warning("10-Q support is not yet available.")
                    return

                file_bytes = uploaded.read()
                file_name = uploaded.name.lower()
                is_pdf = file_name.endswith(".pdf")

                if is_pdf:
                    if extraction_mode == "AI-Enhanced":
                        st.info("AI-Enhanced mode currently targets HTML filings; PDF extraction uses the standard Textract path.")
                    with st.spinner("Extracting text from PDF via AWS Textract …"):
                        pdf_text = extract_text_from_pdf(file_bytes)
                    if not pdf_text:
                        st.error("Textract could not extract text from this PDF.")
                        return
                    with st.spinner("Parsing Item 1 overview …"):
                        overview = extract_item1_overview_from_text(
                            pdf_text, company.strip(), industry,
                        )
                    with st.spinner("Parsing Item 1A risks …"):
                        risks = extract_item1a_risks_from_text(pdf_text)
                else:
                    if extraction_mode == "AI-Enhanced":
                        with st.spinner("Extracting Item 1 overview (AI-Enhanced) …"):
                            overview = extract_item1_overview_bedrock(
                                file_bytes, company.strip(), industry,
                            )
                        with st.spinner("Extracting Item 1A risks (AI-Enhanced) …"):
                            risks = extract_item1a_risks_bedrock(
                                file_bytes, company.strip(),
                            )
                    else:
                        with st.spinner("Extracting Item 1 overview …"):
                            overview = extract_item1_overview(
                                file_bytes, company.strip(), industry,
                            )
                        with st.spinner("Extracting Item 1A risks …"):
                            risks = extract_item1a_risks(file_bytes)

                if not risks:
                    st.error(
                        "Could not extract risks from Item 1A. "
                        "Check that the file is a valid SEC 10-K filing."
                    )
                    return

                overview["year"] = int(year)
                overview["filing_type"] = filing_type

                result = {
                    "company_overview": overview,
                    "risks": risks,
                }

                rid = add_record(
                    company=company.strip(),
                    industry=industry,
                    year=int(year),
                    filing_type=filing_type,
                    file_bytes=file_bytes,
                    file_ext="pdf" if is_pdf else "html",
                    result_json=result,
                )

                st.session_state["last_analyze_result"] = result
                st.session_state["last_analyze_rid"] = rid
                st.rerun()

        with mode_auto:
            st.markdown("##### Auto Fetch from SEC EDGAR")
            c1, c2 = st.columns(2)
            with c1:
                auto_company = st.text_input("Company Name", key="auto_company_name", placeholder="e.g. Apple Inc.")
            with c2:
                auto_ticker = st.text_input("Stock Ticker (optional)", key="auto_stock_ticker", placeholder="e.g. AAPL")

            c3, c4, c5 = st.columns(3)
            with c3:
                auto_industry = st.selectbox("Industry", INDUSTRIES, key="auto_industry")
            with c4:
                auto_start_year = st.selectbox("Start Year", list(range(2025, 2009, -1)), index=5, key="auto_start_year")
            with c5:
                auto_end_year = st.selectbox("End Year", list(range(2025, 2009, -1)), index=1, key="auto_end_year")

            run_auto = st.button(
                "🚀 Auto Fetch & Analyze",
                key="btn_run_auto_fetch",
                type="primary",
                use_container_width=True,
            )

            st.caption(
                "SEC requests use required User-Agent and 0.5s delay. "
                "Only HTML main filing documents are downloaded."
            )

            if run_auto:
                company_name = auto_company.strip()
                ticker = auto_ticker.strip().upper()
                if not company_name:
                    st.error("Please enter a company name.")
                    return
                if int(auto_start_year) > int(auto_end_year):
                    st.error("Start year must be less than or equal to end year.")
                    return

                # Step 1: CIK lookup
                try:
                    cik = _lookup_cik(company_name, ticker)
                except Exception as e:
                    st.error(f"Failed to query SEC search API: {e}")
                    return

                if not cik:
                    st.error(
                        "Could not find CIK from SEC EDGAR for this company. "
                        "Please refine company name and try again."
                    )
                    return

                # Step 2: fetch submissions and filter filings
                try:
                    submissions = _submissions_for_cik(cik)
                except Exception as e:
                    st.error(f"Failed to fetch submissions for CIK {cik}: {e}")
                    return

                filings = _filings_in_year_range(
                    submissions=submissions,
                    start_year=int(auto_start_year),
                    end_year=int(auto_end_year),
                )

                if not filings:
                    st.warning(
                        f"No 10-K filings found for {company_name} in {auto_start_year}–{auto_end_year}."
                    )
                    return

                st.info(f"Found {len(filings)} 10-K filing(s) for {company_name} (CIK {cik}). Starting pipeline...")
                progress = st.progress(0.0, text="Initializing SEC auto-fetch pipeline...")
                status_box = st.empty()

                successes = []
                skipped = []
                total = len(filings)

                for idx, filing in enumerate(filings, start=1):
                    filing_year = int(filing["year"])
                    filing_date = filing.get("filing_date", "")
                    progress_text = f"正在处理 {idx}/{total}：{company_name} {filing_year}..."
                    progress.progress((idx - 1) / total, text=progress_text)
                    status_box.info(progress_text)

                    html_bytes, doc_name, err = _download_filing_html_by_cik(
                        cik_10=cik,
                        accession_number=filing.get("accession_number", ""),
                        primary_document=filing.get("primary_document", ""),
                    )
                    if not html_bytes:
                        skipped.append({
                            "year": filing_year,
                            "reason": err or "No HTML main filing document available.",
                        })
                        continue

                    with st.spinner(f"Running extraction + AI + Agent for {company_name} {filing_year}..."):
                        result, pipe_err = _auto_pipeline_for_html(
                            company=company_name,
                            industry=auto_industry,
                            year=filing_year,
                            html_bytes=html_bytes,
                        )

                    if pipe_err or not result:
                        skipped.append({
                            "year": filing_year,
                            "reason": pipe_err or "Unknown pipeline error.",
                        })
                        continue

                    result["sec_meta"] = {
                        "auto_fetch": True,
                        "cik": cik,
                        "ticker": ticker,
                        "filing_date": filing_date,
                        "accession_number": filing.get("accession_number", ""),
                        "primary_document": filing.get("primary_document", ""),
                        "downloaded_document": doc_name,
                    }

                    rid = add_record(
                        company=company_name,
                        industry=auto_industry,
                        year=filing_year,
                        filing_type="10-K",
                        file_bytes=html_bytes,
                        file_ext="html",
                        result_json=result,
                    )

                    agent_report = result.get("agent_report")
                    if isinstance(agent_report, dict):
                        try:
                            save_agent_report(
                                company=company_name,
                                year=filing_year,
                                filing_type="10-K",
                                report_json=agent_report,
                            )
                        except Exception:
                            pass

                    successes.append({
                        "year": filing_year,
                        "record_id": rid,
                        "filing_date": filing_date,
                    })
                    st.session_state["last_analyze_result"] = result
                    st.session_state["last_analyze_rid"] = rid

                progress.progress(1.0, text="SEC auto-fetch pipeline completed.")
                status_box.success("Auto fetch job completed.")

                st.success(
                    f"Completed {len(successes)}/{total} filing(s) for {company_name}. "
                    f"Skipped {len(skipped)}."
                )

                if successes:
                    st.markdown("**Successful filings**")
                    for s in successes:
                        st.markdown(f"- {s['year']} ({s.get('filing_date','')}) → `{s['record_id']}`")

                if skipped:
                    st.markdown("**Skipped filings**")
                    for s in skipped:
                        st.markdown(f"- {s['year']}: {s['reason']}")
