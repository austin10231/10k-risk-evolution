# app.py
from __future__ import annotations

import os
import re
import json
import time
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# Optional: used for similarity matching in Compare
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_OK = True
except Exception:
    SKLEARN_OK = False


# ----------------------------
# Page config + Light UI
# ----------------------------
st.set_page_config(page_title="10-K Risk Evolution", page_icon="📄", layout="wide")

LIGHT_CSS = """
<style>
/* Light theme */
html, body, [class*="css"]  { background: #f6f7fb !important; color: #111827 !important; }

/* Main container */
.block-container { padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1250px; }

/* Header card */
.hero {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  padding: 18px 18px 12px 18px;
  box-shadow: 0 6px 18px rgba(17, 24, 39, 0.06);
  margin-bottom: 14px;
}
.hero h1 { margin: 0; font-size: 26px; }
.hero p { margin: 6px 0 0 0; color: #4b5563; }

/* Panels */
.panel {
  background: white;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  padding: 14px;
  box-shadow: 0 6px 18px rgba(17, 24, 39, 0.04);
}
.small { color: #6b7280; font-size: 13px; }
.kpi { background: #f9fafb; border: 1px solid #e5e7eb; padding: 10px 12px; border-radius: 12px; }

/* Buttons */
.stButton > button {
  border-radius: 12px !important;
  padding: 10px 14px !important;
  border: 1px solid #e5e7eb !important;
}
.stButton > button[kind="primary"]{
  background: #2563eb !important;
  border: 1px solid #1d4ed8 !important;
  color: white !important;
}

/* File uploader */
div[data-testid="stFileUploader"] section {
  border-radius: 12px !important;
  border: 1px dashed #cbd5e1 !important;
  background: #f9fafb !important;
}

/* Expander */
details {
  border-radius: 12px !important;
  border: 1px solid #e5e7eb !important;
  background: #ffffff !important;
}

/* Tabs */
button[data-baseweb="tab"] {
  border-radius: 999px !important;
}

/* Code blocks a bit nicer */
pre, code { border-radius: 12px !important; }
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
# Storage (local JSON files)
# ----------------------------
DATA_DIR = "data_store"

def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)

def slugify(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "unknown"

def stable_id(company: str, year: str, source_name: str, raw_bytes: bytes) -> str:
    h = hashlib.sha256()
    h.update((company or "").encode("utf-8"))
    h.update((year or "").encode("utf-8"))
    h.update((source_name or "").encode("utf-8"))
    h.update(raw_bytes[:20000])  # enough for uniqueness without huge cost
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
            if not fn.endswith(".json"):
                continue
            p = os.path.join(root, fn)
            try:
                d = read_json(p)
                d["_path"] = p
                out.append(d)
            except Exception:
                continue
    # newest first
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out

def delete_doc(path: str) -> None:
    try:
        os.remove(path)
    except Exception:
        pass

def group_by_sector_company_year(docs: List[dict]) -> Dict[str, Dict[str, Dict[str, List[dict]]]]:
    tree: Dict[str, Dict[str, Dict[str, List[dict]]]] = {}
    for d in docs:
        sec = d.get("sector", "Unknown") or "Unknown"
        comp = d.get("company", "Unknown") or "Unknown"
        yr = str(d.get("year", "Unknown") or "Unknown")
        tree.setdefault(sec, {}).setdefault(comp, {}).setdefault(yr, []).append(d)
    return tree


# ----------------------------
# Extractor bridge
# ----------------------------
def _try_import_extractor():
    try:
        import extractor  # your repo file: extractor.py
        return extractor
    except Exception:
        return None

EXTRACTOR_MOD = _try_import_extractor()

def normalize_extraction_result(
    result: Dict[str, Any],
    company: str,
    year: str,
    sector: str,
    source_name: str,
    doc_id: str,
) -> Dict[str, Any]:
    """
    Standardize keys so UI can display consistently even if extractor returns different names.
    """
    r = dict(result or {})

    # Common fields
    r["company"] = r.get("company") or company
    r["year"] = str(r.get("year") or year)
    r["sector"] = r.get("sector") or sector
    r["source_name"] = r.get("source_name") or source_name
    r["doc_id"] = r.get("doc_id") or doc_id

    # Company overview (Item 1)
    if "company_overview" not in r:
        # try some alternative names
        for k in ["item1", "item_1", "business", "business_overview", "overview"]:
            if k in r:
                r["company_overview"] = r[k]
                break
        r.setdefault("company_overview", {})

    # Risk blocks (Item 1A)
    if "risk_blocks" not in r:
        for k in ["risk_factors", "item1a", "item_1a", "risks"]:
            if k in r:
                r["risk_blocks"] = r[k]
                break
        r.setdefault("risk_blocks", [])

    # Tables
    if "tables" not in r:
        for k in ["financial_tables", "financials", "statements", "extracted_tables"]:
            if k in r:
                r["tables"] = r[k]
                break
        r.setdefault("tables", [])

    # Normalize risk_blocks format to list[{"title":..., "content":...}]
    rb = r.get("risk_blocks", [])
    norm_rb: List[dict] = []
    if isinstance(rb, dict):
        # sometimes dict of title->content
        for t, c in rb.items():
            norm_rb.append({"title": str(t), "content": str(c)})
    elif isinstance(rb, list):
        for item in rb:
            if isinstance(item, dict):
                title = item.get("title") or item.get("heading") or item.get("risk_title") or "Untitled"
                content = item.get("content") or item.get("text") or item.get("body") or ""
                norm_rb.append({"title": str(title), "content": str(content)})
            else:
                norm_rb.append({"title": "Risk", "content": str(item)})
    r["risk_blocks"] = norm_rb

    return r

def extract_10k_bridge(raw_bytes: bytes, filename: str, company: str, year: str, sector_override: Optional[str]) -> Dict[str, Any]:
    """
    Calls your extractor.py if present; otherwise returns a placeholder extraction.
    Supports multiple possible function signatures to avoid crashing.
    """
    if EXTRACTOR_MOD is None or not hasattr(EXTRACTOR_MOD, "extract_10k"):
        # fallback (no extractor)
        text_snip = raw_bytes[:2000].decode("utf-8", errors="ignore")
        return {
            "company_overview": {"note": "Extractor not found. Add extractor.py with extract_10k().", "preview": text_snip[:500]},
            "risk_blocks": [],
            "tables": [],
        }

    fn = getattr(EXTRACTOR_MOD, "extract_10k")

    # Try different signatures gracefully
    # 1) extract_10k(bytes, filename, company, year, sector_override)
    try:
        return fn(raw_bytes, filename, company, year, sector_override)
    except TypeError:
        pass
    # 2) extract_10k(bytes, filename, company, year)
    try:
        return fn(raw_bytes, filename, company, year)
    except TypeError:
        pass
    # 3) extract_10k(bytes, filename)
    try:
        return fn(raw_bytes, filename)
    except TypeError:
        pass
    # 4) extract_10k(text: str)
    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
        return fn(text)
    except Exception:
        # As last resort, raise the original
        raise


# ----------------------------
# Compare helpers
# ----------------------------
def normalize_title(t: str) -> str:
    t = (t or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

def title_similarity(a: str, b: str) -> float:
    a = normalize_title(a)
    b = normalize_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    if SKLEARN_OK:
        vec = TfidfVectorizer().fit([a, b])
        X = vec.transform([a, b])
        sim = float(cosine_similarity(X[0], X[1])[0][0])
        return max(0.0, min(1.0, sim))

    # fallback: simple token overlap
    sa = set(a.split())
    sb = set(b.split())
    inter = len(sa & sb)
    union = max(1, len(sa | sb))
    return inter / union

def match_risk_blocks(
    blocks_a: List[dict],
    blocks_b: List[dict],
    threshold: float = 0.55,
) -> Tuple[List[dict], List[dict], List[dict]]:
    """
    Return: matched, new_in_b, removed_from_a
    matched: [{"a":{...},"b":{...},"title_sim":0.xx}]
    """
    used_b = set()
    matched: List[dict] = []

    for i, a in enumerate(blocks_a):
        best_j = None
        best_sim = -1.0
        for j, b in enumerate(blocks_b):
            if j in used_b:
                continue
            sim = title_similarity(a.get("title", ""), b.get("title", ""))
            if sim > best_sim:
                best_sim = sim
                best_j = j
        if best_j is not None and best_sim >= threshold:
            used_b.add(best_j)
            matched.append({"a": a, "b": blocks_b[best_j], "title_sim": round(best_sim, 4)})

    new_in_b = [b for j, b in enumerate(blocks_b) if j not in used_b]
    removed = []
    # removed are those in A that didn't match
    matched_a_titles = set((m["a"].get("title", "") for m in matched))
    for a in blocks_a:
        if a.get("title", "") not in matched_a_titles:
            # could be false positive if duplicate titles; acceptable for demo
            removed.append(a)

    return matched, new_in_b, removed


# ----------------------------
# Session state
# ----------------------------
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None


# ----------------------------
# Top tabs (product-like)
# ----------------------------
tab_upload, tab_library, tab_compare = st.tabs(["⬆️ Upload & Extract", "📚 Library", "🔎 Compare"])


# ==========================================
# TAB 1: Upload & Extract
# ==========================================
with tab_upload:
    left, right = st.columns([1.05, 1.35], gap="large")

    with left:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Upload")
        uploaded = st.file_uploader("Upload a 10-K file (HTML/PDF/TXT)", type=["html", "htm", "pdf", "txt"])
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

        run = st.button("🚀 Extract & Save to Library", type="primary", use_container_width=True)

        st.markdown('<div class="small">Tip: HTML filings usually give the best extraction quality (risk blocks + tables).</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Results (Structured JSON)")
        st.caption("After you click Extract, parsed outputs will appear here.")
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

            # Extract
            with st.spinner("Extracting..."):
                extracted = extract_10k_bridge(raw, uploaded.name, company_clean, year_clean, sector_override)

            # Determine sector: override > extracted > Unknown
            sector_final = sector_override or extracted.get("sector") or "Unknown"

            # Normalize + persist
            normalized = normalize_extraction_result(
                extracted,
                company=company_clean,
                year=year_clean,
                sector=sector_final,
                source_name=uploaded.name,
                doc_id=doc_id,
            )
            normalized["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

            path = doc_path(sector_final, company_clean, year_clean, doc_id)
            write_json(path, normalized)

            st.session_state["last_result"] = normalized
            st.success(f"Extracted & saved ✅  (Sector: {sector_final}, Company: {company_clean}, Year: {year_clean})")

    # Right result panel render
    with right:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        data = st.session_state.get("last_result")

        if not data:
            st.info("No extraction yet. Upload a 10-K and click Extract.")
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

            with st.expander("⚠️ Risk Factors (Item 1A) - structured blocks", expanded=True):
                st.code(json.dumps(data.get("risk_blocks", []), indent=2, ensure_ascii=False), language="json")

            with st.expander("📊 Financial Tables (extracted)", expanded=False):
                st.code(json.dumps(data.get("tables", []), indent=2, ensure_ascii=False), language="json")

        st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# TAB 2: Library (browse + view + download)
# ==========================================
with tab_library:
    docs = list_all_docs()
    tree = group_by_sector_company_year(docs)

    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.subheader("Library")
    st.caption("Browse saved 10-K extractions by Sector → Company → Year. View / download / delete.")
    st.markdown('</div>', unsafe_allow_html=True)

    if not docs:
        st.info("Library is empty. Go to Upload & Extract first.")
    else:
        colA, colB, colC = st.columns([1.1, 1.1, 1.2], gap="large")

        sectors = sorted(tree.keys())
        with colA:
            sector_sel = st.selectbox("Sector", ["(All)"] + sectors, index=0)
        comps = sorted({d.get("company","") for d in docs if d.get("company")})
        with colB:
            company_sel = st.selectbox("Company", ["(All)"] + comps, index=0)
        years = sorted({str(d.get("year","")) for d in docs if d.get("year")})
        with colC:
            year_sel = st.selectbox("Year", ["(All)"] + years, index=0)

        # Filter docs
        filtered = docs
        if sector_sel != "(All)":
            filtered = [d for d in filtered if (d.get("sector") or "Unknown") == sector_sel]
        if company_sel != "(All)":
            filtered = [d for d in filtered if (d.get("company") or "") == company_sel]
        if year_sel != "(All)":
            filtered = [d for d in filtered if str(d.get("year") or "") == year_sel]

        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader(f"Saved Documents ({len(filtered)})")

        options = []
        for d in filtered:
            label = f"{d.get('sector','Unknown')} / {d.get('company','Unknown')} / {d.get('year','')}  —  {d.get('source_name','')}"
            options.append((label, d.get("_path","")))

        if not options:
            st.info("No documents match your filters.")
        else:
            labels = [x[0] for x in options]
            paths = [x[1] for x in options]
            sel = st.selectbox("Select a document", labels, index=0)
            sel_path = paths[labels.index(sel)]
            doc = read_json(sel_path)

            c1, c2, c3 = st.columns([1,1,1])
            with c1:
                st.download_button(
                    "⬇️ Download JSON",
                    data=json.dumps(doc, indent=2, ensure_ascii=False).encode("utf-8"),
                    file_name=f"{slugify(doc.get('company','company'))}_{doc.get('year','year')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with c2:
                if st.button("⭐ Set as 'Last Result' (preview in Upload tab)", use_container_width=True):
                    st.session_state["last_result"] = doc
                    st.success("Set as last result.")
            with c3:
                if st.button("🗑️ Delete", use_container_width=True):
                    delete_doc(sel_path)
                    st.warning("Deleted. Refresh tab (or rerun).")
                    st.stop()

            with st.expander("Document JSON", expanded=True):
                st.code(json.dumps(doc, indent=2, ensure_ascii=False), language="json")

        st.markdown('</div>', unsafe_allow_html=True)


# ==========================================
# TAB 3: Compare (same company, different years)
# ==========================================
with tab_compare:
    docs = list_all_docs()
    if not docs:
        st.info("Library is empty. Upload at least 2 years of the same company first.")
    else:
        st.markdown('<div class="panel">', unsafe_allow_html=True)
        st.subheader("Compare Risk Factors (Year-over-Year)")
        st.caption("Select a company and two filing years. We match risk blocks by title similarity and show matched / new / removed.")
        st.markdown('</div>', unsafe_allow_html=True)

        companies = sorted({d.get("company","") for d in docs if d.get("company")})
        company = st.selectbox("Company", companies, index=0 if companies else None)
        company_docs = [d for d in docs if d.get("company") == company]
        years = sorted({str(d.get("year","")) for d in company_docs})
        if len(years) < 2:
            st.warning("This company has fewer than 2 years in the library. Upload another year first.")
        else:
            c1, c2, c3 = st.columns([1,1,1.2])
            with c1:
                year_a = st.selectbox("Year A (baseline)", years, index=0)
            with c2:
                year_b = st.selectbox("Year B (compare)", years, index=min(1, len(years)-1))
            with c3:
                threshold = st.slider("Title similarity threshold", min_value=0.30, max_value=0.95, value=0.55, step=0.05)

            def pick_doc(year: str) -> dict:
                cand = [d for d in company_docs if str(d.get("year")) == str(year)]
                # choose newest if multiple
                cand.sort(key=lambda x: x.get("created_at",""), reverse=True)
                return read_json(cand[0]["_path"])

            docA = pick_doc(year_a)
            docB = pick_doc(year_b)

            blocks_a = docA.get("risk_blocks", [])
            blocks_b = docB.get("risk_blocks", [])

            matched, new_blocks, removed = match_risk_blocks(blocks_a, blocks_b, threshold=float(threshold))

            st.markdown('<div class="panel">', unsafe_allow_html=True)
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Year A blocks", len(blocks_a))
            k2.metric("Year B blocks", len(blocks_b))
            k3.metric("Matched", len(matched))
            k4.metric("New / Removed", f"{len(new_blocks)} / {len(removed)}")
            st.markdown('</div>', unsafe_allow_html=True)

            tab1, tab2, tab3, tab4 = st.tabs(["✅ Matched", "🆕 New in B", "🗑️ Removed from A", "⬇️ Export JSON"])

            with tab1:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not matched:
                    st.info("No matched blocks found at this threshold.")
                else:
                    for m in matched:
                        title = m["b"].get("title", "Untitled")
                        sim = m.get("title_sim", 0)
                        with st.expander(f"{title}  —  sim={sim}", expanded=False):
                            st.markdown(f"**{year_a} — {m['a'].get('title','')}**")
                            st.write(m["a"].get("content",""))
                            st.markdown("---")
                            st.markdown(f"**{year_b} — {m['b'].get('title','')}**")
                            st.write(m["b"].get("content",""))
                st.markdown('</div>', unsafe_allow_html=True)

            with tab2:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not new_blocks:
                    st.success("No new blocks detected at this threshold.")
                else:
                    for b in new_blocks:
                        with st.expander(f"NEW — {b.get('title','Untitled')}", expanded=False):
                            st.write(b.get("content",""))
                st.markdown('</div>', unsafe_allow_html=True)

            with tab3:
                st.markdown('<div class="panel">', unsafe_allow_html=True)
                if not removed:
                    st.success("No removed blocks detected at this threshold.")
                else:
                    for b in removed:
                        with st.expander(f"REMOVED — {b.get('title','Untitled')}", expanded=False):
                            st.write(b.get("content",""))
                st.markdown('</div>', unsafe_allow_html=True)

            with tab4:
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
                st.markdown('</div>', unsafe_allow_html=True)
