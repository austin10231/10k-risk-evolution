# app.py
from __future__ import annotations

import os
import re
import json
import time
import hashlib
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
from bs4 import BeautifulSoup

# Optional PDF support (best-effort)
try:
    import pdfplumber  # type: ignore
    PDF_OK = True
except Exception:
    PDF_OK = False

# Optional similarity for Compare
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SK_OK = True
except Exception:
    SK_OK = False


# ----------------------------
# Light UI (force)
# ----------------------------
st.set_page_config(page_title="10-K Risk Evolution", page_icon="📄", layout="wide")

LIGHT_CSS = """
<style>
/* Force full light background across Streamlit */
html, body, .stApp { background: #f6f7fb !important; color: #111827 !important; }
header, footer { background: transparent !important; }
section[data-testid="stSidebar"] { background: #ffffff !important; border-right: 1px solid #e5e7eb !important; }
div[data-testid="stAppViewContainer"] { background: #f6f7fb !important; }
div[data-testid="stHeader"] { background: #f6f7fb !important; }
div[data-testid="stToolbar"] { background: #f6f7fb !important; }

/* main container width */
.block-container { padding-top: 1.1rem; padding-bottom: 2.2rem; max-width: 1250px; }

/* hero */
.hero {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  padding: 18px 18px 12px 18px;
  box-shadow: 0 10px 24px rgba(17,24,39,0.06);
  margin-bottom: 14px;
}
.hero h1 { margin: 0; font-size: 28px; letter-spacing: -0.3px; }
.hero p { margin: 8px 0 0 0; color: #4b5563; }

/* panels */
.panel {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 14px;
  box-shadow: 0 10px 22px rgba(17,24,39,0.05);
}
.small { color: #6b7280; font-size: 13px; }
hr { border-color: #e5e7eb !important; }

/* buttons */
.stButton > button {
  border-radius: 12px !important;
  border: 1px solid #e5e7eb !important;
  padding: 10px 14px !important;
}
.stButton > button[kind="primary"]{
  background: #2563eb !important;
  border: 1px solid #1d4ed8 !important;
  color: white !important;
}

/* file uploader */
div[data-testid="stFileUploader"] section{
  background: #f9fafb !important;
  border-radius: 12px !important;
  border: 1px dashed #cbd5e1 !important;
}

/* tabs */
button[data-baseweb="tab"]{
  border-radius: 999px !important;
  padding-left: 14px !important;
  padding-right: 14px !important;
}
div[data-baseweb="tab-list"]{ gap: 8px !important; }

/* code blocks */
pre, code { border-radius: 12px !important; }

/* --- Fix washed-out text on light background --- */

/* General text */
.stApp, .stApp * {
  color: #111827;
}

/* Tabs text */
button[data-baseweb="tab"] * {
  color: #111827 !important;
}

/* Expander header text */
div[data-testid="stExpander"] summary,
div[data-testid="stExpander"] summary * {
  color: #111827 !important;
}

/* Metric labels + values */
div[data-testid="stMetricLabel"],
div[data-testid="stMetricValue"],
div[data-testid="stMetricDelta"] {
  color: #111827 !important;
}

/* Selectbox / input text */
div[data-baseweb="select"] * ,
input, textarea {
  color: #111827 !important;
}

/* Caption / secondary text */
small, .small, .stCaption, div[data-testid="stCaptionContainer"] * {
  color: #4b5563 !important;
}

/* Code block text already OK, but ensure visible */
pre, code {
  color: #111827 !important;
}

/* --- Fix dark form controls on light theme --- */

/* Text input / number input / textarea */
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextArea"] textarea {
  background: #ffffff !important;
  color: #111827 !important;
  border: 1px solid #e5e7eb !important;
}

/* Selectbox + Multiselect (BaseWeb) */
div[data-baseweb="select"] > div {
  background: #ffffff !important;
  border: 1px solid #e5e7eb !important;
}
div[data-baseweb="select"] * {
  color: #111827 !important;
}

/* The dropdown menu */
ul[role="listbox"] {
  background: #ffffff !important;
  border: 1px solid #e5e7eb !important;
}
ul[role="listbox"] * {
  color: #111827 !important;
}

/* File uploader */
div[data-testid="stFileUploader"] section {
  background: #ffffff !important;
  border: 1px dashed #d1d5db !important;
}
div[data-testid="stFileUploader"] * {
  color: #111827 !important;
}

/* Buttons on light background */
.stButton>button {
  background: #2563eb !important;
  color: #ffffff !important;
  border: 0 !important;
}

</style>
"""
st.markdown(LIGHT_CSS, unsafe_allow_html=True)

st.markdown(
    """
<div class="hero">
  <h1>📄 10-K Risk Evolution</h1>
  <p>Upload a SEC 10-K (HTML recommended). Extract Item 1 (Business), Item 1A (Risk Factors) into structured JSON, and capture key financial tables. Store & compare year-over-year changes.</p>
</div>
""",
    unsafe_allow_html=True,
)


# ----------------------------
# Storage
# ----------------------------
DATA_DIR = "data_store"

def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"

def stable_id(company: str, year: str, filename: str, raw_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update(company.encode("utf-8"))
    h.update(year.encode("utf-8"))
    h.update(filename.encode("utf-8"))
    h.update(raw_bytes[:20000])
    return h.hexdigest()[:16]

def doc_path(sector: str, company: str, year: str, doc_id: str) -> str:
    return os.path.join(DATA_DIR, slugify(sector), slugify(company), slugify(year), f"{doc_id}.json")

def write_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def list_all_docs() -> List[dict]:
    ensure_data_dir()
    out: List[dict] = []
    for root, _, files in os.walk(DATA_DIR):
        for fn in files:
            if fn.endswith(".json"):
                p = os.path.join(root, fn)
                try:
                    d = read_json(p)
                    d["_path"] = p
                    out.append(d)
                except Exception:
                    continue
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out

def delete_doc(path: str) -> None:
    try:
        os.remove(path)
    except Exception:
        pass


# ----------------------------
# 10-K HTML extraction (PoC but real)
# ----------------------------
ITEM1_RE = re.compile(r"\bITEM\s+1\b[\.\:]*\s*(BUSINESS)?", re.IGNORECASE)
ITEM1A_RE = re.compile(r"\bITEM\s+1A\b[\.\:]*\s*(RISK\s+FACTORS)?", re.IGNORECASE)
ITEM1B_RE = re.compile(r"\bITEM\s+1B\b", re.IGNORECASE)
ITEM2_RE = re.compile(r"\bITEM\s+2\b", re.IGNORECASE)
ITEM7_RE = re.compile(r"\bITEM\s+7\b[\.\:]*\s*(MANAGEMENT\S*\s+DISCUSSION)?", re.IGNORECASE)
ITEM8_RE = re.compile(r"\bITEM\s+8\b[\.\:]*\s*(FINANCIAL\s+STATEMENTS)?", re.IGNORECASE)
ITEM9_RE = re.compile(r"\bITEM\s+9\b", re.IGNORECASE)

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    # remove scripts/styles
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    # normalize
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text

def slice_item(text: str, start_re: re.Pattern, end_res: List[re.Pattern]) -> str:
    m = start_re.search(text)
    if not m:
        return ""
    start = m.end()
    end = len(text)
    for er in end_res:
        mm = er.search(text, start)
        if mm:
            end = min(end, mm.start())
    chunk = text[start:end].strip()
    # prevent insane size
    return chunk[:250000]

def is_heading_line(line: str) -> bool:
    s = line.strip()
    if len(s) < 6 or len(s) > 140:
        return False
    # exclude obvious boilerplate
    bad_prefix = ("item ", "part ", "table of contents", "risk factors", "forward-looking")
    if s.lower().startswith(bad_prefix):
        return False
    # mostly letters/spaces/punct
    if re.search(r"https?://", s.lower()):
        return False
    # heading signals:
    # 1) All caps (or nearly) and not too many digits
    letters = re.sub(r"[^A-Za-z]+", "", s)
    if letters:
        upper_ratio = sum(1 for c in letters if c.isupper()) / max(1, len(letters))
        if upper_ratio > 0.85 and len(letters) >= 8:
            return True
    # 2) Title-like (ends no period) and starts with capital
    if s[0].isupper() and not s.endswith(".") and len(s.split()) <= 18:
        # avoid paragraph-ish
        if len(s) < 90:
            return True
    return False

def split_risk_blocks(item1a_text: str) -> List[dict]:
    if not item1a_text:
        return []

    lines = [ln.strip() for ln in item1a_text.splitlines() if ln.strip()]
    blocks: List[dict] = []

    cur_title = "Overview"
    cur_buf: List[str] = []

    def flush():
        nonlocal cur_title, cur_buf
        content = "\n".join(cur_buf).strip()
        if content:
            blocks.append({"title": cur_title[:140], "content": content[:20000]})
        cur_buf = []

    for ln in lines:
        # detect headings
        if is_heading_line(ln):
            # avoid treating repeated headings too frequently
            if cur_buf:
                flush()
            cur_title = re.sub(r"\s+", " ", ln)
        else:
            cur_buf.append(ln)

    flush()

    # remove tiny blocks (noise)
    cleaned = []
    for b in blocks:
        if len(b["content"]) >= 120:
            cleaned.append(b)
    return cleaned[:120]

def extract_tables_from_html(html: str, max_tables: int = 8) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    scored: List[Tuple[int, Any]] = []

    for t in tables:
        rows = t.find_all("tr")
        if len(rows) < 6:
            continue
        # score by cells
        cell_count = 0
        for r in rows[:40]:
            cell_count += len(r.find_all(["td", "th"]))
        if cell_count < 30:
            continue
        scored.append((cell_count, t))

    scored.sort(key=lambda x: x[0], reverse=True)
    picked = [t for _, t in scored[:max_tables]]

    out: List[dict] = []
    for idx, t in enumerate(picked, start=1):
        rows = []
        for tr in t.find_all("tr")[:60]:
            cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["th", "td"])]
            if any(cells):
                rows.append(cells[:25])
        # normalize ragged rows for display
        max_len = max((len(r) for r in rows), default=0)
        if max_len == 0:
            continue
        for r in rows:
            if len(r) < max_len:
                r.extend([""] * (max_len - len(r)))

        out.append({
            "table_id": f"T{idx}",
            "rows": rows,
            "shape": {"rows": len(rows), "cols": max_len},
        })
    return out

def extract_from_html(raw_bytes: bytes) -> Dict[str, Any]:
    html = raw_bytes.decode("utf-8", errors="ignore")
    text = html_to_text(html)

    item1 = slice_item(text, ITEM1_RE, [ITEM1A_RE, ITEM2_RE, ITEM1B_RE])
    item1a = slice_item(text, ITEM1A_RE, [ITEM1B_RE, ITEM2_RE, ITEM7_RE, ITEM8_RE])
    # some filings label risk factors later; fallback: if empty, try between Item 1A and Item 2 only
    if not item1a:
        item1a = slice_item(text, ITEM1A_RE, [ITEM2_RE])

    company_overview = {
        "source": "Item 1",
        "raw_text": item1[:20000],
    }
    risk_blocks = split_risk_blocks(item1a)

    tables = extract_tables_from_html(html, max_tables=8)

    return {
        "company_overview": company_overview,
        "risk_blocks": risk_blocks,
        "tables": tables,
        "debug": {
            "item1_found": bool(item1),
            "item1a_found": bool(item1a),
            "total_text_len": len(text),
        }
    }

def extract_from_pdf(raw_bytes: bytes) -> Dict[str, Any]:
    if not PDF_OK:
        return {
            "company_overview": {"note": "PDF support not installed on server."},
            "risk_blocks": [],
            "tables": [],
        }
    # PoC: extract text only
    import io
    text_parts = []
    with pdfplumber.open(io.BytesIO(raw_bytes)) as pdf:
        for p in pdf.pages[:25]:
            t = p.extract_text() or ""
            if t.strip():
                text_parts.append(t)
    text = "\n".join(text_parts)
    item1 = slice_item(text, ITEM1_RE, [ITEM1A_RE, ITEM2_RE])
    item1a = slice_item(text, ITEM1A_RE, [ITEM2_RE, ITEM7_RE])
    return {
        "company_overview": {"source": "Item 1", "raw_text": (item1 or "")[:20000]},
        "risk_blocks": split_risk_blocks(item1a or ""),
        "tables": [],  # PDF tables are harder; keep empty for now
        "debug": {"pdf_text_len": len(text)}
    }

def extract_10k(raw_bytes: bytes, filename: str) -> Dict[str, Any]:
    ext = filename.lower().split(".")[-1]
    if ext in ("html", "htm"):
        return extract_from_html(raw_bytes)
    if ext == "pdf":
        return extract_from_pdf(raw_bytes)
    # txt fallback
    text = raw_bytes.decode("utf-8", errors="ignore")
    item1 = slice_item(text, ITEM1_RE, [ITEM1A_RE, ITEM2_RE])
    item1a = slice_item(text, ITEM1A_RE, [ITEM2_RE, ITEM7_RE])
    return {
        "company_overview": {"source": "Item 1", "raw_text": (item1 or "")[:20000]},
        "risk_blocks": split_risk_blocks(item1a or ""),
        "tables": [],
        "debug": {"txt_len": len(text)}
    }


# ----------------------------
# Compare helpers
# ----------------------------
def norm_title(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def title_sim(a: str, b: str) -> float:
    a = norm_title(a)
    b = norm_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if SK_OK:
        vec = TfidfVectorizer().fit([a, b])
        X = vec.transform([a, b])
        return float(cosine_similarity(X[0], X[1])[0][0])
    # fallback
    sa, sb = set(a.split()), set(b.split())
    return len(sa & sb) / max(1, len(sa | sb))

def match_blocks(a: List[dict], b: List[dict], threshold: float) -> Tuple[List[dict], List[dict], List[dict]]:
    used_b = set()
    matched = []
    for i, aa in enumerate(a):
        best_j, best = None, -1.0
        for j, bb in enumerate(b):
            if j in used_b:
                continue
            s = title_sim(aa.get("title",""), bb.get("title",""))
            if s > best:
                best = s
                best_j = j
        if best_j is not None and best >= threshold:
            used_b.add(best_j)
            matched.append({"a": aa, "b": b[best_j], "title_sim": round(best, 4)})

    new_in_b = [bb for j, bb in enumerate(b) if j not in used_b]

    matched_a_titles = set(m["a"].get("title","") for m in matched)
    removed = [aa for aa in a if aa.get("title","") not in matched_a_titles]

    return matched, new_in_b, removed


# ----------------------------
# Session state
# ----------------------------
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None


# ----------------------------
# Tabs
# ----------------------------
tab_upload, tab_library, tab_compare = st.tabs(["⬆️ Upload & Extract", "📚 Library", "🔎 Compare"])


# ==========================================
# Upload & Extract
# ==========================================
with tab_upload:
    left, right = st.columns([1.05, 1.35], gap="large")

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Upload")

        uploaded = st.file_uploader("Upload a 10-K file (HTML recommended)", type=["html", "htm", "pdf", "txt"])
        c1, c2 = st.columns([1, 1])
        with c1:
            year = st.text_input("Filing Year", value=str(time.gmtime().tm_year - 1))
        with c2:
            company = st.text_input("Company Name (required)", value="")

        sector = st.selectbox(
            "Sector (optional override)",
            ["(Auto)", "Technology", "Semiconductors", "Retail", "Energy", "Financials", "Industrial", "Healthcare", "Other"],
            index=0,
        )

        run = st.button("🚀 Extract & Save", type="primary", use_container_width=True)
        st.markdown('<div class="small">Tip: EDGAR HTML usually gives best results for Item 1A headings + tables.</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Results (Structured JSON)")
        st.caption("After you click Extract, the JSON output will appear here.")
        st.markdown('</div>', unsafe_allow_html=True)

    if run:
        if not uploaded or not company.strip():
            st.error("Please upload a file and enter Company Name.")
        else:
            ensure_data_dir()
            raw = uploaded.getvalue()
            company_clean = company.strip()
            year_clean = year.strip()
            sector_override = None if sector == "(Auto)" else sector

            doc_id = stable_id(company_clean, year_clean, uploaded.name, raw)

            with st.spinner("Extracting from filing..."):
                extracted = extract_10k(raw, uploaded.name)

            sector_final = sector_override or "Unknown"

            result = {
                "doc_id": doc_id,
                "company": company_clean,
                "year": year_clean,
                "sector": sector_final,
                "source_name": uploaded.name,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "company_overview": extracted.get("company_overview", {}),
                "risk_blocks": extracted.get("risk_blocks", []),
                "tables": extracted.get("tables", []),
                "debug": extracted.get("debug", {}),
            }

            path = doc_path(sector_final, company_clean, year_clean, doc_id)
            write_json(path, result)

            st.session_state["last_result"] = result
            st.success(f"Saved ✅  {sector_final} / {company_clean} / {year_clean}")

    # Render right results panel
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        data = st.session_state.get("last_result")

        if not data:
            st.info("No extraction yet. Upload a 10-K HTML and click Extract.")
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Company", data.get("company", ""))
            k2.metric("Year", data.get("year", ""))
            k3.metric("Risk Blocks", len(data.get("risk_blocks", [])))
            k4.metric("Tables", len(data.get("tables", [])))

            st.download_button(
                "⬇️ Download Full JSON",
                data=json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"),
                file_name=f"{slugify(data.get('company','company'))}_{data.get('year','year')}_10k.json",
                mime="application/json",
                use_container_width=True,
            )

            with st.expander("🏢 Company Overview (Item 1)", expanded=True):
                st.code(json.dumps(data.get("company_overview", {}), indent=2, ensure_ascii=False), language="json")

            with st.expander("⚠️ Risk Factors (Item 1A) — structured blocks", expanded=True):
                st.code(json.dumps(data.get("risk_blocks", []), indent=2, ensure_ascii=False), language="json")

            with st.expander("📊 Financial-like Tables (PoC)", expanded=False):
                st.code(json.dumps(data.get("tables", []), indent=2, ensure_ascii=False), language="json")

            with st.expander("🧪 Debug", expanded=False):
                st.code(json.dumps(data.get("debug", {}), indent=2, ensure_ascii=False), language="json")

        st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# Library
# ==========================================
with tab_library:
    docs = list_all_docs()

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Library")
    st.caption("Browse saved extractions. Select one to view / download / delete.")
    st.markdown("</div>", unsafe_allow_html=True)

    if not docs:
        st.info("Library is empty. Upload & Extract first.")
    else:
        sectors = sorted({d.get("sector","Unknown") for d in docs})
        companies = sorted({d.get("company","") for d in docs if d.get("company")})
        years = sorted({str(d.get("year","")) for d in docs if d.get("year")})

        c1, c2, c3 = st.columns(3)
        with c1:
            sector_sel = st.selectbox("Sector", ["(All)"] + sectors, index=0)
        with c2:
            company_sel = st.selectbox("Company", ["(All)"] + companies, index=0)
        with c3:
            year_sel = st.selectbox("Year", ["(All)"] + years, index=0)

        filtered = docs
        if sector_sel != "(All)":
            filtered = [d for d in filtered if d.get("sector","Unknown") == sector_sel]
        if company_sel != "(All)":
            filtered = [d for d in filtered if d.get("company","") == company_sel]
        if year_sel != "(All)":
            filtered = [d for d in filtered if str(d.get("year","")) == year_sel]

        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader(f"Saved Documents ({len(filtered)})")

        options = []
        for d in filtered:
            label = f"{d.get('sector','Unknown')} / {d.get('company','Unknown')} / {d.get('year','')} — {d.get('source_name','')}"
            options.append((label, d["_path"]))

        if not options:
            st.info("No documents match your filters.")
        else:
            labels = [x[0] for x in options]
            paths = [x[1] for x in options]
            sel = st.selectbox("Select a document", labels, index=0)
            sel_path = paths[labels.index(sel)]
            doc = read_json(sel_path)

            b1, b2, b3 = st.columns([1,1,1])
            with b1:
                st.download_button(
                    "⬇️ Download JSON",
                    data=json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8"),
                    file_name=f"{slugify(doc.get('company','company'))}_{doc.get('year','year')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with b2:
                if st.button("👁️ Preview in Results", use_container_width=True):
                    st.session_state["last_result"] = doc
                    st.success("Preview set.")
            with b3:
                if st.button("🗑️ Delete", use_container_width=True):
                    delete_doc(sel_path)
                    st.warning("Deleted. Rerun to refresh.")
                    st.stop()

            with st.expander("Document JSON", expanded=True):
                st.code(json.dumps(doc, indent=2, ensure_ascii=False), language="json")

        st.markdown("</div>", unsafe_allow_html=True)


# ==========================================
# Compare
# ==========================================
with tab_compare:
    docs = list_all_docs()
    if not docs:
        st.info("Library is empty. Upload at least 2 years of the same company first.")
    else:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Compare Risk Factors (YoY)")
        st.caption("Match risk blocks by title similarity → show matched / new / removed.")
        st.markdown("</div>", unsafe_allow_html=True)

        companies = sorted({d.get("company","") for d in docs if d.get("company")})
        company = st.selectbox("Company", companies, index=0)

        cdocs = [d for d in docs if d.get("company") == company]
        years = sorted({str(d.get("year","")) for d in cdocs})
        if len(years) < 2:
            st.warning("Need at least 2 years for this company.")
        else:
            c1, c2, c3 = st.columns([1,1,1.3])
            with c1:
                year_a = st.selectbox("Year A (baseline)", years, index=0)
            with c2:
                year_b = st.selectbox("Year B (compare)", years, index=min(1, len(years)-1))
            with c3:
                threshold = st.slider("Title similarity threshold", 0.30, 0.95, 0.55, 0.05)

            def pick_doc(y: str) -> dict:
                cand = [d for d in cdocs if str(d.get("year","")) == str(y)]
                cand.sort(key=lambda x: x.get("created_at",""), reverse=True)
                return read_json(cand[0]["_path"])

            A = pick_doc(year_a)
            B = pick_doc(year_b)

            matched, new_blocks, removed = match_blocks(A.get("risk_blocks", []), B.get("risk_blocks", []), float(threshold))

            st.markdown('<div class="panel">', unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("A blocks", len(A.get("risk_blocks", [])))
            k2.metric("B blocks", len(B.get("risk_blocks", [])))
            k3.metric("Matched", len(matched))
            k4.metric("New / Removed", f"{len(new_blocks)} / {len(removed)}")
            st.markdown("</div>", unsafe_allow_html=True)

            t1, t2, t3, t4 = st.tabs(["✅ Matched", "🆕 New in B", "🗑️ Removed from A", "⬇️ Export JSON"])

            with t1:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not matched:
                    st.info("No matched blocks at this threshold.")
                else:
                    for m in matched:
                        title = m["b"].get("title","Untitled")
                        sim = m.get("title_sim", 0)
                        with st.expander(f"{title} — sim={sim}", expanded=False):
                            st.markdown(f"**{year_a}**")
                            st.write(m["a"].get("content",""))
                            st.markdown("---")
                            st.markdown(f"**{year_b}**")
                            st.write(m["b"].get("content",""))
                st.markdown("</div>", unsafe_allow_html=True)

            with t2:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not new_blocks:
                    st.success("No new blocks.")
                else:
                    for b in new_blocks:
                        with st.expander(f"NEW — {b.get('title','Untitled')}", expanded=False):
                            st.write(b.get("content",""))
                st.markdown("</div>", unsafe_allow_html=True)

            with t3:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not removed:
                    st.success("No removed blocks.")
                else:
                    for b in removed:
                        with st.expander(f"REMOVED — {b.get('title','Untitled')}", expanded=False):
                            st.write(b.get("content",""))
                st.markdown("</div>", unsafe_allow_html=True)

            with t4:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                payload = {
                    "company": company,
                    "year_a": year_a,
                    "year_b": year_b,
                    "threshold": float(threshold),
                    "matched_count": len(matched),
                    "new_count": len(new_blocks),
                    "removed_count": len(removed),
                    "matched": matched,
                    "new": new_blocks,
                    "removed": removed,
                }
                st.download_button(
                    "⬇️ Download comparison JSON",
                    data=json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"),
                    file_name=f"{slugify(company)}_{year_a}_vs_{year_b}_compare.json",
                    mime="application/json",
                    use_container_width=True,
                )
                st.code(json.dumps(payload, indent=2, ensure_ascii=False), language="json")
                st.markdown("</div>", unsafe_allow_html=True)
