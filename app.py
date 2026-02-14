# app.py
from __future__ import annotations

import json
from typing import Dict, Any, List, Tuple

import streamlit as st
import pandas as pd

from extractors import extract_10k
from storage import (
    save_document,
    load_document,
    list_documents,
    delete_document,
    group_by_sector,
    group_company_years,
)

# -----------------------
# UI setup + styling
# -----------------------
st.set_page_config(page_title="10-K Risk Evolution", page_icon="📄", layout="wide")

CSS = """
<style>
:root { --card-bg: rgba(255,255,255,0.06); --border: rgba(255,255,255,0.12); }
.block-container { padding-top: 1.0rem; padding-bottom: 2rem; }
.hero {
  border: 1px solid var(--border);
  background: linear-gradient(135deg, rgba(99,102,241,0.18), rgba(16,185,129,0.12));
  border-radius: 18px;
  padding: 18px 18px 14px 18px;
}
.kpi {
  border: 1px solid var(--border);
  background: var(--card-bg);
  border-radius: 16px;
  padding: 14px;
}
.badge {
  display:inline-block; padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--border); background: rgba(255,255,255,0.06);
  font-size: 12px;
}
.small { font-size: 12px; opacity: 0.85; }
hr { border: none; border-top: 1px solid rgba(255,255,255,0.10); margin: 12px 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

st.markdown(
    """
<div class="hero">
  <div style="font-size:26px; font-weight:800;">📄 10-K Risk Evolution</div>
  <div class="small">
    Upload a SEC 10-K (HTML recommended). Extract <span class="mono">Item 1 (Business)</span>,
    <span class="mono">Item 1A (Risk Factors)</span> into structured JSON, and capture key financial tables.
  </div>
  <div style="margin-top:8px;">
    <span class="badge">Upload → Extract → Store</span>
    <span class="badge">Library (by Sector/Company/Year)</span>
    <span class="badge">Compare (same company, different years)</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")

# -----------------------
# Sidebar navigation
# -----------------------
page = st.sidebar.radio("Navigation", ["1) Upload & Extract", "2) Library", "3) Compare"], index=0)

st.sidebar.divider()
st.sidebar.caption("Tip: HTML filings give the best extraction quality (risk blocks + tables).")


# -----------------------
# Helpers
# -----------------------
def _bytes(uploader) -> bytes:
    return uploader.getvalue()


def render_tables_block(fin_tables: Dict[str, Any]) -> None:
    st.caption(fin_tables.get("note", ""))
    for key, label in [
        ("balance_sheet", "Balance Sheet"),
        ("income_statement", "Income Statement"),
        ("cash_flow", "Cash Flow Statement"),
        ("other_tables", "Other Tables (Unclassified)"),
    ]:
        items = fin_tables.get(key, [])
        with st.expander(f"{label} — {len(items)} table(s)", expanded=False):
            if not items:
                st.write("No tables found.")
            for i, tjson in enumerate(items):
                cols = tjson.get("columns", [])
                data = tjson.get("data", [])
                df = pd.DataFrame(data, columns=cols) if cols and data else pd.DataFrame(data)
                st.write(f"Table {i+1} (shape={tjson.get('shape')})")
                st.dataframe(df, use_container_width=True)


def render_risk_blocks(risk_blocks: List[Dict[str, str]]) -> None:
    if not risk_blocks:
        st.warning("No risk blocks found. Try using the HTML filing.")
        return
    for i, b in enumerate(risk_blocks, start=1):
        with st.expander(f"{i}. {b['title']}", expanded=False):
            st.write(b["content"])


# -----------------------
# Page 1: Upload & Extract
# -----------------------
if page.startswith("1"):
    st.subheader("Upload & Extract")

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        file = st.file_uploader("Upload a 10-K file (HTML/PDF/TXT)", type=["html", "htm", "pdf", "txt"])
    with c2:
        year = st.text_input("Filing Year", value="2024")
    with c3:
        company_name = st.text_input("Company Name (required)", value="")

    sector_override = st.selectbox(
        "Sector (optional override)",
        ["(Auto)", "Technology", "Semiconductor", "Retail", "Energy", "Utilities", "Manufacturing", "Other", "Unknown"],
        index=0,
    )

    run = st.button("🚀 Extract & Save to Library", type="primary", use_container_width=True)

    if run:
        if not file:
            st.error("Please upload a file.")
            st.stop()
        if not company_name.strip():
            st.error("Please enter the Company Name (this is used for storage + comparison).")
            st.stop()

        ext = file.name.split(".")[-1].lower()
        file_bytes = _bytes(file)

        with st.spinner("Extracting sections & tables..."):
            extracted = extract_10k(file_bytes, ext)

        sector = extracted.get("sector_inferred", "Unknown")
        if sector_override != "(Auto)":
            sector = sector_override

        doc = {
            "company_name": company_name.strip(),
            "year": str(year).strip(),
            "sector": sector,
            "source_file": {"name": file.name, "type": ext},
            "extracted": {
                "company_background": extracted.get("company_background", ""),
                "risk_blocks": extracted.get("risk_blocks", []),
                "financial_tables": extracted.get("financial_tables", {}),
                # optionally keep raw (can be large) - comment out if you prefer smaller JSON
                "raw": {
                    "item1_business_text": extracted.get("item1_business_text", "")[:20000],
                    "item1a_risk_text": extracted.get("item1a_risk_text", "")[:20000],
                },
            },
        }

        doc_id = save_document(doc)
        st.success(f"Saved to Library ✅  doc_id = {doc_id}")

        # Quick preview
        st.divider()
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"<div class='kpi'><div class='small'>Sector</div><div style='font-size:22px;font-weight:800;'>{sector}</div></div>", unsafe_allow_html=True)
        k2.markdown(f"<div class='kpi'><div class='small'>Risk Blocks</div><div style='font-size:22px;font-weight:800;'>{len(doc['extracted']['risk_blocks'])}</div></div>", unsafe_allow_html=True)
        ft = doc["extracted"]["financial_tables"]
        total_tables = sum(len(ft.get(k, [])) for k in ["balance_sheet", "income_statement", "cash_flow", "other_tables"]) if isinstance(ft, dict) else 0
        k3.markdown(f"<div class='kpi'><div class='small'>Tables Found</div><div style='font-size:22px;font-weight:800;'>{total_tables}</div></div>", unsafe_allow_html=True)
        bg_len = len(doc["extracted"]["company_background"] or "")
        k4.markdown(f"<div class='kpi'><div class='small'>Background chars</div><div style='font-size:22px;font-weight:800;'>{bg_len}</div></div>", unsafe_allow_html=True)

        st.subheader("Company Background (from Item 1)")
        st.write(doc["extracted"]["company_background"] or "—")

        st.subheader("Risk Factors (structured by subheadings)")
        render_risk_blocks(doc["extracted"]["risk_blocks"])

        st.subheader("Financial Statements Tables (HTML works best)")
        render_tables_block(doc["extracted"]["financial_tables"])

        st.download_button(
            "⬇️ Download extracted JSON",
            data=json.dumps(doc, indent=2).encode("utf-8"),
            file_name=f"{company_name.strip()}_{year}_extracted.json",
            mime="application/json",
            use_container_width=True,
        )


# -----------------------
# Page 2: Library
# -----------------------
elif page.startswith("2"):
    st.subheader("Library (Stored Filings)")

    docs = list_documents()
    if not docs:
        st.info("No documents yet. Go to **Upload & Extract** and save a filing.")
        st.stop()

    grouped = group_by_sector(docs)

    left, right = st.columns([1, 2], gap="large")
    with left:
        sector = st.selectbox("Sector", sorted(grouped.keys()))
        sector_docs = grouped[sector]
        companies = sorted(set(d["company_name"] for d in sector_docs))
        company = st.selectbox("Company", companies)

        years = [d for d in sector_docs if d["company_name"] == company]
        years_sorted = sorted(years, key=lambda x: x["year"])
        year_pick = st.selectbox("Year", [d["year"] for d in years_sorted])

    with right:
        # find doc_id
        doc_id = None
        for d in sector_docs:
            if d["company_name"] == company and d["year"] == year_pick:
                doc_id = d["doc_id"]
                break
        if not doc_id:
            st.error("Document not found in index.")
            st.stop()

        doc = load_document(doc_id)
        st.markdown(f"**Selected:** {doc['company_name']} — {doc['year']}  <span class='badge'>{doc.get('sector','')}</span>", unsafe_allow_html=True)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("Company Background")
            st.write(doc["extracted"].get("company_background", "") or "—")
        with c2:
            st.subheader("Quick Stats")
            rb = doc["extracted"].get("risk_blocks", [])
            ft = doc["extracted"].get("financial_tables", {})
            total_tables = sum(len(ft.get(k, [])) for k in ["balance_sheet", "income_statement", "cash_flow", "other_tables"]) if isinstance(ft, dict) else 0
            st.write(f"- Risk blocks: **{len(rb)}**")
            st.write(f"- Tables found: **{total_tables}**")
            st.write(f"- Source: **{doc.get('source_file',{}).get('name','')}**")

        st.subheader("Risk Blocks")
        render_risk_blocks(doc["extracted"].get("risk_blocks", []))

        st.subheader("Financial Tables")
        render_tables_block(doc["extracted"].get("financial_tables", {}))

        st.divider()
        colA, colB = st.columns([1, 1])
        with colA:
            st.download_button(
                "⬇️ Download JSON (this filing)",
                data=json.dumps(doc, indent=2).encode("utf-8"),
                file_name=f"{doc['company_name']}_{doc['year']}_stored.json",
                mime="application/json",
                use_container_width=True,
            )
        with colB:
            if st.button("🗑 Delete this filing", use_container_width=True):
                delete_document(doc_id)
                st.success("Deleted. Refresh the page.")
                st.stop()


# -----------------------
# Page 3: Compare (same company across years)
# -----------------------
else:
    st.subheader("Compare (Same Company, Different Years)")

    docs = list_documents()
    if not docs:
        st.info("No documents yet. Upload at least two filings for the same company.")
        st.stop()

    companies = sorted(set(d["company_name"] for d in docs))
    company = st.selectbox("Company", companies)

    company_docs = group_company_years(docs, company)
    if len(company_docs) < 2:
        st.warning("Need at least two years stored for this company to compare.")
        st.stop()

    years = [d["year"] for d in company_docs]
    col1, col2 = st.columns(2)
    with col1:
        year_a = st.selectbox("Year A", years, index=0)
    with col2:
        year_b = st.selectbox("Year B", years, index=min(1, len(years) - 1))

    threshold = st.slider("Title similarity threshold (simple baseline)", 0.30, 0.90, 0.60, 0.01)

    def title_sim(a: str, b: str) -> float:
        # simple normalized overlap baseline (replace later with embeddings)
        a_set = set(a.lower().split())
        b_set = set(b.lower().split())
        if not a_set or not b_set:
            return 0.0
        return len(a_set & b_set) / len(a_set | b_set)

    if st.button("🔎 Compare", type="primary", use_container_width=True):
        doc_id_a = next(d["doc_id"] for d in company_docs if d["year"] == year_a)
        doc_id_b = next(d["doc_id"] for d in company_docs if d["year"] == year_b)
        A = load_document(doc_id_a)
        B = load_document(doc_id_b)

        blocks_a = A["extracted"].get("risk_blocks", [])
        blocks_b = B["extracted"].get("risk_blocks", [])

        # greedy match by title similarity (baseline). You can replace with TF-IDF/embeddings later.
        used_b = set()
        matched = []
        removed = []
        for i, ba in enumerate(blocks_a):
            best = (-1.0, None)
            for j, bb in enumerate(blocks_b):
                if j in used_b:
                    continue
                s = title_sim(ba["title"], bb["title"])
                if s > best[0]:
                    best = (s, j)
            if best[1] is not None and best[0] >= threshold:
                j = best[1]
                used_b.add(j)
                matched.append({"sim": best[0], "a": ba, "b": blocks_b[j]})
            else:
                removed.append(ba)

        new_blocks = [bb for j, bb in enumerate(blocks_b) if j not in used_b]

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"<div class='kpi'><div class='small'>Risk blocks {year_a}</div><div style='font-size:22px;font-weight:800;'>{len(blocks_a)}</div></div>", unsafe_allow_html=True)
        k2.markdown(f"<div class='kpi'><div class='small'>Risk blocks {year_b}</div><div style='font-size:22px;font-weight:800;'>{len(blocks_b)}</div></div>", unsafe_allow_html=True)
        k3.markdown(f"<div class='kpi'><div class='small'>Matched</div><div style='font-size:22px;font-weight:800;'>{len(matched)}</div></div>", unsafe_allow_html=True)
        k4.markdown(f"<div class='kpi'><div class='small'>New / Removed</div><div style='font-size:22px;font-weight:800;'>{len(new_blocks)} / {len(removed)}</div></div>", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["✅ Matched", "🆕 New", "🗑 Removed", "⬇️ Export"])
        with tab1:
            if not matched:
                st.warning("No matches. Lower the threshold or check risk titles in both years.")
            else:
                for m in sorted(matched, key=lambda x: x["sim"], reverse=True):
                    st.markdown(f"**Title similarity:** `{m['sim']:.2f}`")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown(f"**{year_a} — {m['a']['title']}**")
                        st.write(m["a"]["content"])
                    with c2:
                        st.markdown(f"**{year_b} — {m['b']['title']}**")
                        st.write(m["b"]["content"])
                    st.markdown("<hr/>", unsafe_allow_html=True)

        with tab2:
            if not new_blocks:
                st.success("No new blocks detected at this threshold.")
            else:
                for b in new_blocks:
                    with st.expander(f"NEW — {b['title']}", expanded=False):
                        st.write(b["content"])

        with tab3:
            if not removed:
                st.success("No removed blocks detected at this threshold.")
            else:
                for b in removed:
                    with st.expander(f"REMOVED — {b['title']}", expanded=False):
                        st.write(b["content"])

       
        with tab4:
            payload = {
                "company": company,
                "year_a": year_a,
                "year_b": year_b,
                "threshold": threshold,
                "matched_count": len(matched),
                "new_count": len(new_blocks),
                "removed_count": len(removed),
                "matched": matched,
                "new": new_blocks,
                "removed": removed,
            }
            st.download_button(
                "⬇️ Download comparison JSON",
                data=json.dumps(payload, indent=2).encode("utf-8"),
                file_name=f"{company}_{year_a}_vs_{year_b}_compare.json",
                mime="application/json",
                use_container_width=True,
            )
            st.code(json.dumps(payload, indent=2), language="json")
