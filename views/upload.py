"""Upload page — new 10-K filing with stepper progress indicator."""

import streamlit as st
import streamlit.components.v1 as components
import json
import time
import ssl
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from storage.store import add_record, _s3_write, RESULTS_PREFIX, save_agent_report
from storage.store import upsert_company_ticker
from core.global_context import sync_widget_from_context, render_current_config_box
from core.extractor import (
    extract_item1_overview, extract_item1a_risks,
    extract_text_from_pdf, extract_item1_overview_from_text,
    extract_item1a_risks_from_text,
    extract_item1_overview_bedrock, extract_item1a_risks_bedrock,
)
from core.bedrock import classify_risks, generate_summary
from core.comprehend import enrich_risks_with_comprehend
from core.agent import run_agent

INDUSTRIES = [
    "Technology", "Healthcare", "Financials", "Energy",
    "Consumer Discretionary", "Consumer Staples", "Industrials",
    "Materials", "Utilities", "Real Estate", "Telecom", "Other",
]

SEC_USER_AGENT = "RiskLens App contact@risklens.com"
SEC_REQUEST_DELAY_SEC = 0.5


def _count_sub_risks(risks):
    return sum(len(c.get("sub_risks", [])) for c in risks)


def _run_ai(result, record_id):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    with st.spinner("Classifying risks with AI…"):
        classified = classify_risks(risks)
    with st.spinner("Extracting entities and key phrases with Comprehend…"):
        enriched_risks, comprehend_meta = enrich_risks_with_comprehend(classified)
    result["risks"] = enriched_risks
    result["comprehend_meta"] = comprehend_meta
    with st.spinner("Generating executive summary…"):
        summary = generate_summary(ov.get("company", ""), ov.get("year", 0), enriched_risks)
    result["ai_summary"] = summary
    _s3_write(
        f"{RESULTS_PREFIX}/{record_id}.json",
        json.dumps(result, indent=2, default=str, ensure_ascii=False).encode("utf-8"),
    )
    st.session_state["upload_result"] = result
    st.rerun()


def _sec_headers():
    return {"User-Agent": SEC_USER_AGENT}


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
    return str(candidates[0]).zfill(10)


def _lookup_cik(company_name: str, ticker: str = "") -> str:
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


def _filings_in_year_range(submissions: dict, start_year: int, end_year: int):
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    total = min(len(forms), len(filing_dates), len(accessions), len(primary_docs))
    out = []
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
    if any(k in n for k in ("xbrl", "_cal", "_def", "_lab", "_pre", ".xml", "schema", "graphic", "exhibit")):
        return False
    return True


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


def _download_filing_html_by_cik(cik_10: str, accession_number: str, primary_document: str):
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


def _auto_pipeline_for_html(company: str, industry: str, year: int, html_bytes: bytes):
    overview = extract_item1_overview(html_bytes, company.strip(), industry)
    risks = extract_item1a_risks(html_bytes)
    if not risks:
        return None, "Could not extract risks from Item 1A."

    classified = classify_risks(risks)
    summary = generate_summary(company.strip(), int(year), classified)
    agent_report = run_agent(
        user_query="Prioritize all risks and identify the top 5 most critical threats",
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


def _stepper(step: int):
    """Render a 3-step progress indicator. step: 1=Upload, 2=Processing, 3=Done."""
    def _cls(n):
        if n < step:   return "done"
        if n == step:  return "active"
        return "pending"
    def _lbl(n, text):
        c = _cls(n)
        icon = "✓" if c == "done" else str(n)
        return (
            f'<div class="step-item">'
            f'<div class="step-circle {c}">{icon}</div>'
            f'<span class="step-text {c}">{text}</span>'
            f'</div>'
        )
    def _conn(n):
        c = "done" if n < step else ""
        return f'<div class="step-connector {c}"></div>'

    st.markdown(
        f'<div class="stepper">'
        f'{_lbl(1,"Configure")} {_conn(1)} {_lbl(2,"Extract")} {_conn(2)} {_lbl(3,"Results")}'
        f'</div>',
        unsafe_allow_html=True,
    )


def _show_result(result, rid):
    ov = result.get("company_overview", {})
    risks = result.get("risks", [])
    ai_summary = result.get("ai_summary", "")
    comprehend_meta = result.get("comprehend_meta", {})

    # Metrics strip
    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric("Company", ov.get("company", "—"))
    mc2.metric("Year", ov.get("year", "—"))
    mc3.metric("Risk Categories", len(risks))
    mc4.metric("Risk Items", _count_sub_risks(risks))

    # AI Summary
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
    else:
        if st.button("🤖 Run AI Summarize", key=f"ai_up_{rid}"):
            _run_ai(result, rid)

    # Business overview
    bg = ov.get("background", "")
    if bg:
        st.markdown('<div class="section-header">🏢 Business Overview</div>', unsafe_allow_html=True)
        st.markdown(
            f'<p style="font-size:0.88rem; color:#374151; line-height:1.6;">{bg}</p>',
            unsafe_allow_html=True,
        )

    # Risk categories
    st.markdown(
        f'<div class="section-header">⚠️ Risk Categories ({len(risks)})</div>',
        unsafe_allow_html=True,
    )
    for cat_block in risks:
        cat_name = cat_block.get("category", "Unknown")
        subs = cat_block.get("sub_risks", [])
        if subs and isinstance(subs[0], dict):
            with st.expander(f"**{cat_name}** ({len(subs)} risks)", expanded=False):
                for s in subs:
                    labels = s.get("labels", [])
                    tags = s.get("tags", [])
                    label_str = " · ".join(f"`{l}`" for l in labels) if labels else ""
                    tag_str = " · ".join(f"`{t}`" for t in tags[:6]) if tags else ""
                    st.markdown(f"- {s.get('title','')}")
                    if label_str:
                        st.caption(f"   Labels: {label_str}")
                    if tag_str:
                        st.caption(f"   Tags: {tag_str}")
        else:
            if subs:
                with st.expander(f"**{cat_name}** ({len(subs)} risks)", expanded=False):
                    for s in subs:
                        title = str(s or "").strip()
                        if title:
                            st.markdown(f"- {title}")
            else:
                st.markdown(f"- **{cat_name}** — 0 items")

    st.markdown("<br>", unsafe_allow_html=True)
    st.download_button(
        "📥 Download Full JSON",
        data=json.dumps(result, indent=2, ensure_ascii=False),
        file_name=f"{ov.get('company','export')}_{ov.get('year','')}.json",
        mime="application/json",
        key=f"dl_up_{rid}",
        use_container_width=True,
    )


def _render_manual_upload_panel():
    has_result = "upload_result" in st.session_state
    year_options = list(range(2025, 2009, -1))

    # Strong-sync defaults from global context (apply before widget creation)
    sync_widget_from_context("up_company", "company", allow_empty=True)
    sync_widget_from_context("up_ticker", "ticker", allow_empty=True)
    sync_widget_from_context("up_year", "year", options=year_options)
    sync_widget_from_context("up_industry", "industry", options=INDUSTRIES)
    sync_widget_from_context("up_ftype", "filing_type", options=["10-K", "10-Q (coming soon)"])

    # ── Two-column layout ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([2, 3], gap="large")

    with col_left:
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.8rem;">CONFIGURE</p>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "Filing file (HTML or PDF)",
            type=["html", "htm", "pdf"],
            key="up_file",
        )
        company = st.text_input("Company Name", key="up_company", placeholder="e.g. Apple Inc.")
        ticker = st.text_input("Stock Ticker (optional)", key="up_ticker", placeholder="e.g. AAPL")

        col_y, col_i = st.columns(2)
        with col_y:
            year = st.selectbox("Filing Year", year_options, key="up_year")
        with col_i:
            industry = st.selectbox("Industry", INDUSTRIES, key="up_industry")

        filing_type = st.selectbox(
            "Filing Type", ["10-K", "10-Q (coming soon)"], key="up_ftype"
        )
        extraction_mode = st.selectbox(
            "Extraction Mode",
            ["Standard", "AI-Enhanced"],
            index=0,
            key="up_extract_mode",
            help="Standard uses existing BeautifulSoup rules. AI-Enhanced uses Bedrock with automatic fallback.",
        )

        st.markdown("<br>", unsafe_allow_html=True)

        run = st.button("🚀 Extract & Save", key="btn_run_upload",
                        type="primary", use_container_width=True)
        st.caption("HTML works best for structured extraction. PDF uses AWS Textract.")

    # ── Right panel: results or empty state ───────────────────────────────────
    with col_right:
        st.markdown(
            '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
            'letter-spacing:0.1em; margin:0 0 0.8rem;">RESULTS</p>',
            unsafe_allow_html=True,
        )

        if not has_result:
            st.markdown(
                """
                <div class="empty-state" style="height:380px; display:flex; flex-direction:column;
                     justify-content:center; align-items:center;">
                    <p class="empty-state-icon">📋</p>
                    <p class="empty-state-title">Extraction results will appear here</p>
                    <p class="empty-state-sub">Configure the inputs on the left, then hit Extract & Save</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            result = st.session_state["upload_result"]
            rid = st.session_state.get("upload_rid", "x")
            _show_result(result, rid)

    # ── Handle extraction ─────────────────────────────────────────────────────
    if run:
        if not company.strip():
            st.error("Please enter a company name.")
            return
        ticker = str(ticker or "").strip().upper()
        if uploaded is None:
            st.error("Please upload a file.")
            return
        if "coming soon" in filing_type:
            st.warning("10-Q support is not yet available.")
            return

        file_bytes = uploaded.read()
        is_pdf = uploaded.name.lower().endswith(".pdf")

        if is_pdf:
            if extraction_mode == "AI-Enhanced":
                st.info("AI-Enhanced mode currently targets HTML filings; PDF extraction uses the standard Textract path.")
            with st.spinner("Extracting text via AWS Textract…"):
                pdf_text = extract_text_from_pdf(file_bytes)
            if not pdf_text:
                st.error("Textract could not extract text from this PDF.")
                return
            with st.spinner("Parsing Item 1 overview…"):
                overview = extract_item1_overview_from_text(pdf_text, company.strip(), industry)
            with st.spinner("Parsing Item 1A risks…"):
                risks = extract_item1a_risks_from_text(pdf_text)
        else:
            if extraction_mode == "AI-Enhanced":
                with st.spinner("Extracting Item 1 overview (AI-Enhanced) …"):
                    overview = extract_item1_overview_bedrock(file_bytes, company.strip(), industry)
                with st.spinner("Extracting Item 1A risks (AI-Enhanced) …"):
                    risks = extract_item1a_risks_bedrock(file_bytes, company.strip())
            else:
                with st.spinner("Extracting Item 1 overview…"):
                    overview = extract_item1_overview(file_bytes, company.strip(), industry)
                with st.spinner("Extracting Item 1A risks…"):
                    risks = extract_item1a_risks(file_bytes)

        if not risks:
            st.error(
                "Could not extract risks from Item 1A. "
                "Check that the file is a valid SEC 10-K filing."
            )
            return

        overview["year"] = int(year)
        overview["filing_type"] = filing_type
        result = {"company_overview": overview, "risks": risks}

        rid = add_record(
            company=company.strip(),
            industry=industry,
            year=int(year),
            filing_type=filing_type,
            file_bytes=file_bytes,
            file_ext="pdf" if is_pdf else "html",
            result_json=result,
        )
        if ticker:
            try:
                upsert_company_ticker(company.strip(), ticker)
            except Exception:
                pass

        st.session_state["upload_result"] = result
        st.session_state["upload_rid"] = rid
        st.rerun()


def _render_auto_fetch_panel():
    year_options = list(range(2025, 2009, -1))
    # Strong-sync defaults from global context (apply before widget creation)
    sync_widget_from_context("auto_up_company", "company", allow_empty=True)
    sync_widget_from_context("auto_up_ticker", "ticker", allow_empty=True)
    sync_widget_from_context("auto_up_industry", "industry", options=INDUSTRIES)
    sync_widget_from_context("auto_up_start_year", "year", options=year_options)
    sync_widget_from_context("auto_up_end_year", "year", options=year_options)

    st.markdown(
        '<p style="font-size:0.62rem; font-weight:700; color:#94a3b8; text-transform:uppercase;'
        'letter-spacing:0.1em; margin:0 0 0.8rem;">AUTO FETCH CONFIGURE</p>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        company_name = st.text_input("Company Name", key="auto_up_company", placeholder="e.g. Apple Inc.")
    with c2:
        ticker = st.text_input("Stock Ticker (optional)", key="auto_up_ticker", placeholder="e.g. AAPL")

    c3, c4, c5 = st.columns(3)
    with c3:
        industry = st.selectbox("Industry", INDUSTRIES, key="auto_up_industry")
    with c4:
        start_year = st.selectbox("Start Year", year_options, index=5, key="auto_up_start_year")
    with c5:
        end_year = st.selectbox("End Year", year_options, index=1, key="auto_up_end_year")

    run_auto = st.button(
        "🚀 Auto Fetch from SEC EDGAR",
        key="btn_auto_fetch_upload",
        type="primary",
        use_container_width=True,
    )
    st.caption(
        "SEC requests include required User-Agent and 0.5s pacing. "
        "Only HTML main filing document is downloaded."
    )

    if not run_auto:
        return

    company_name = company_name.strip()
    ticker = ticker.strip().upper()
    if not company_name:
        st.error("Please enter a company name.")
        return
    if ticker:
        try:
            upsert_company_ticker(company_name, ticker)
        except Exception:
            pass
    if int(start_year) > int(end_year):
        st.error("Start year must be less than or equal to end year.")
        return

    try:
        cik = _lookup_cik(company_name, ticker)
    except Exception as e:
        st.error(f"Failed to query SEC search API: {e}")
        return

    if not cik:
        st.error("Could not find CIK from SEC EDGAR for this company. Please refine company name/ticker and try again.")
        return

    try:
        submissions = _submissions_for_cik(cik)
    except Exception as e:
        st.error(f"Failed to fetch submissions for CIK {cik}: {e}")
        return

    filings = _filings_in_year_range(submissions, int(start_year), int(end_year))
    if not filings:
        st.warning(f"No 10-K filings found for {company_name} in {start_year}–{end_year}.")
        return

    st.info(f"Found {len(filings)} 10-K filing(s) for {company_name} (CIK {cik}). Starting full pipeline...")
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
            skipped.append({"year": filing_year, "reason": err or "No HTML main filing document available."})
            continue

        with st.spinner(f"Running extraction + AI + Agent for {company_name} {filing_year}..."):
            result, pipe_err = _auto_pipeline_for_html(
                company=company_name,
                industry=industry,
                year=filing_year,
                html_bytes=html_bytes,
            )
        if pipe_err or not result:
            skipped.append({"year": filing_year, "reason": pipe_err or "Unknown pipeline error."})
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
            industry=industry,
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

        successes.append({"year": filing_year, "filing_date": filing_date, "record_id": rid})
        st.session_state["upload_result"] = result
        st.session_state["upload_rid"] = rid

    progress.progress(1.0, text="SEC auto-fetch pipeline completed.")
    status_box.success("Auto fetch job completed.")
    st.success(f"Completed {len(successes)}/{total} filing(s) for {company_name}. Skipped {len(skipped)}.")

    if successes:
        st.markdown("**Successful filings**")
        for s in successes:
            st.markdown(f"- {s['year']} ({s.get('filing_date', '')}) → `{s['record_id']}`")
    if skipped:
        st.markdown("**Skipped filings**")
        for s in skipped:
            st.markdown(f"- {s['year']}: {s['reason']}")


def render():
    # ── Page header ───────────────────────────────────────────────────────────
    header_left, header_right = st.columns([2.35, 2.65], gap="medium")
    with header_left:
        st.markdown(
            """
            <div class="page-header">
                <div class="page-header-left">
                    <span class="page-icon">🗂️</span>
                    <div>
                        <p class="page-title">Filings</p>
                        <p class="page-subtitle">Ingest new filings and manage existing records in one place</p>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with header_right:
        render_current_config_box(
            key_prefix="ctx_upload",
            year_options=list(range(2025, 2009, -1)),
            industry_options=INDUSTRIES,
        )

    def _render_ingestion_section():
        has_result = "upload_result" in st.session_state
        _stepper(3 if has_result else 1)
        mode_manual, mode_auto = st.tabs(["📄 Manual Upload", "🛰️ Auto Fetch from SEC EDGAR"])
        with mode_manual:
            _render_manual_upload_panel()
        with mode_auto:
            _render_auto_fetch_panel()

    def _render_records_section():
        from views.library import render_records_panel
        render_records_panel(
            show_header=False,
            key_prefix="filings",
            state_prefix="filings",
            show_new_filing_button=False,
        )

    def _activate_records_tab_once():
        """Switch visual tab to Records while keeping tab order fixed."""
        components.html(
            """
            <script>
            (function () {
              let tries = 0;
              const timer = setInterval(() => {
                tries += 1;
                const tabs = window.parent.document.querySelectorAll('button[data-baseweb="tab"]');
                for (const tab of tabs) {
                  const text = (tab.textContent || "").trim();
                  if (text.includes("Records")) {
                    tab.click();
                    clearInterval(timer);
                    return;
                  }
                }
                if (tries > 30) clearInterval(timer);
              }, 80);
            })();
            </script>
            """,
            height=0,
            width=0,
        )

    open_records = bool(st.session_state.pop("upload_open_records", False))
    mode_ingest, mode_records = st.tabs(["🆕 New Ingestion", "📚 Records"])
    if open_records:
        _activate_records_tab_once()

    with mode_ingest:
        _render_ingestion_section()
    with mode_records:
        _render_records_section()
