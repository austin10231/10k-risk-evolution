# app.py
# Streamlit UI for SEC 10-K Risk Factors extraction + year-over-year comparison (MVP but "complete" workflow)
# - Upload two 10-K files (HTML/PDF/TXT)
# - Extract Item 1A (Risk Factors)
# - Segment into risk blocks using subheadings
# - Compare Year A vs Year B with TF-IDF cosine similarity (stable baseline)
# - Show New / Removed / Matched risks + scores + downloadable JSON

import io
import re
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional

import streamlit as st

# Optional imports (PDF parsing + HTML parsing)
try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ----------------------------
# UI THEME (simple but designed)
# ----------------------------
st.set_page_config(page_title="10-K Risk Evolution", page_icon="📄", layout="wide")

CSS = """
<style>
:root { --card-bg: rgba(255,255,255,0.06); --border: rgba(255,255,255,0.10); }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
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
  <div style="display:flex; align-items:flex-start; justify-content:space-between; gap:14px;">
    <div>
      <div style="font-size:26px; font-weight:800;">📄 10-K Risk Evolution Dashboard</div>
      <div class="small">Extract <span class="mono">Item 1A — Risk Factors</span>, segment by subheadings, and compare year-over-year changes.</div>
      <div style="margin-top:8px;">
        <span class="badge">MVP UI</span>
        <span class="badge">Risk blocks</span>
        <span class="badge">YoY matching</span>
        <span class="badge">Download JSON</span>
      </div>
    </div>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

st.write("")


# ----------------------------
# Helpers / Data structures
# ----------------------------
@dataclass
class RiskBlock:
    title: str
    content: str
    source_year: str
    idx: int


BOILERPLATE_PATTERNS = [
    r"forward-looking statements",
    r"should be read in conjunction with",
    r"not be considered to be a reliable indicator of future performance",
    r"may be materially and adversely affected",
    r"results of operations and financial condition",
]


def normalize_text(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def looks_like_boilerplate(par: str) -> bool:
    p = par.lower()
    return any(re.search(pat, p) for pat in BOILERPLATE_PATTERNS) or len(p) < 80


def extract_text_from_pdf(file_bytes: bytes) -> str:
    if pdfplumber is None:
        raise RuntimeError("pdfplumber is not installed. Add it to requirements.txt to parse PDFs.")
    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)
    return normalize_text("\n".join(text_parts))


def html_to_text(file_bytes: bytes) -> str:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 is not installed. Add it to requirements.txt to parse HTML.")
    soup = BeautifulSoup(file_bytes, "html.parser")
    # Remove script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n")
    return normalize_text(text)


def extract_item_1a_risk_section(full_text: str) -> str:
    """
    Extract a rough slice of Item 1A Risk Factors section using text anchors.
    Works best for HTML -> text or well-extracted PDF text.
    """
    t = full_text

    # Common anchors
    start_patterns = [
        r"\bItem\s*1A\.*\s*Risk\s*Factors\b",
        r"\bITEM\s*1A\.*\s*RISK\s*FACTORS\b",
    ]
    end_patterns = [
        r"\bItem\s*1B\.*\s*Unresolved\s*Staff\s*Comments\b",
        r"\bITEM\s*1B\.*\s*UNRESOLVED\s*STAFF\s*COMMENTS\b",
        r"\bItem\s*2\.*\s*Properties\b",
        r"\bITEM\s*2\.*\s*PROPERTIES\b",
        r"\bPart\s*II\b",
        r"\bPART\s*II\b",
    ]

    start_idx = None
    for pat in start_patterns:
        m = re.search(pat, t, flags=re.IGNORECASE)
        if m:
            start_idx = m.start()
            break

    if start_idx is None:
        # Fallback: return full text (still lets you test segmentation)
        return t

    sub = t[start_idx:]

    end_idx = None
    for pat in end_patterns:
        m = re.search(pat, sub, flags=re.IGNORECASE)
        if m and m.start() > 200:  # avoid matching within header lines
            end_idx = m.start()
            break

    return normalize_text(sub[:end_idx] if end_idx else sub)


def segment_risk_blocks(risk_section_text: str, year: str) -> List[RiskBlock]:
    """
    Segment Risk Factors section into blocks using heuristic heading detection.
    We treat lines that look like headings as titles and collect following paragraphs.
    """
    lines = [ln.strip() for ln in risk_section_text.splitlines() if ln.strip()]
    # Remove the first "Item 1A..." header line if present
    if lines and re.search(r"\bItem\s*1A\b", lines[0], flags=re.IGNORECASE):
        lines = lines[1:]

    # Heuristic: heading lines are short-ish, mostly Title Case / all caps, no ending period
    def is_heading(line: str) -> bool:
        if len(line) < 6 or len(line) > 140:
            return False
        if line.endswith("."):
            return False
        # Too many digits => likely table/numbered
        if sum(ch.isdigit() for ch in line) > 4:
            return False
        # Looks like a category heading
        all_caps = (line.upper() == line) and (sum(ch.isalpha() for ch in line) >= 8)
        titleish = (sum(ch.isupper() for ch in line) >= 3) and ("  " not in line)
        # Avoid boilerplate headers
        if "forward-looking" in line.lower():
            return False
        return all_caps or titleish

    blocks: List[RiskBlock] = []
    current_title = "General"
    current_body: List[str] = []

    def flush():
        nonlocal current_title, current_body, blocks
        body_text = normalize_text("\n".join(current_body))
        if body_text:
            # remove boilerplate-y short paragraphs
            paras = [p.strip() for p in re.split(r"\n\s*\n", body_text) if p.strip()]
            paras = [p for p in paras if not looks_like_boilerplate(p)]
            cleaned = normalize_text("\n\n".join(paras))
            if cleaned:
                blocks.append(RiskBlock(title=current_title, content=cleaned, source_year=year, idx=len(blocks)))

    for ln in lines:
        if is_heading(ln):
            flush()
            current_title = ln
            current_body = []
        else:
            current_body.append(ln)

    flush()

    # If everything filtered out, at least return one block with raw (so UI still works)
    if not blocks:
        blocks = [RiskBlock(title="Risk Factors", content=risk_section_text[:6000], source_year=year, idx=0)]
    return blocks


def build_similarity_matrix(a_texts: List[str], b_texts: List[str]) -> "list[list[float]]":
    corpus = a_texts + b_texts
    vec = TfidfVectorizer(stop_words="english", max_features=6000, ngram_range=(1, 2))
    X = vec.fit_transform(corpus)
    A = X[: len(a_texts)]
    B = X[len(a_texts) :]
    sim = cosine_similarity(A, B)  # shape (len(a), len(b))
    return sim


def match_blocks(
    blocks_a: List[RiskBlock], blocks_b: List[RiskBlock], threshold: float
) -> Tuple[List[dict], List[RiskBlock], List[RiskBlock]]:
    """
    Greedy matching based on similarity; returns:
      - matched pairs list with similarity
      - new in B (unmatched)
      - removed from A (unmatched)
    """
    a_texts = [b.title + "\n" + b.content for b in blocks_a]
    b_texts = [b.title + "\n" + b.content for b in blocks_b]
    sim = build_similarity_matrix(a_texts, b_texts)

    used_a, used_b = set(), set()
    pairs = []

    # Flatten candidates
    candidates = []
    for i in range(len(blocks_a)):
        for j in range(len(blocks_b)):
            candidates.append((sim[i][j], i, j))
    candidates.sort(reverse=True, key=lambda x: x[0])

    for s, i, j in candidates:
        if s < threshold:
            break
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        pairs.append(
            {
                "similarity": float(s),
                "year_a": blocks_a[i].source_year,
                "year_b": blocks_b[j].source_year,
                "title_a": blocks_a[i].title,
                "title_b": blocks_b[j].title,
                "content_a": blocks_a[i].content,
                "content_b": blocks_b[j].content,
                "a_idx": blocks_a[i].idx,
                "b_idx": blocks_b[j].idx,
            }
        )

    removed = [b for b in blocks_a if b.idx not in used_a]
    new = [b for b in blocks_b if b.idx not in used_b]
    return pairs, new, removed


def safe_decode(file) -> bytes:
    return file.getvalue() if hasattr(file, "getvalue") else file.read()


def read_document(file, filetype: str) -> str:
    b = safe_decode(file)
    if filetype == "pdf":
        return extract_text_from_pdf(b)
    if filetype in ("html", "htm"):
        return html_to_text(b)
    # txt fallback
    return normalize_text(b.decode("utf-8", errors="ignore"))


# ----------------------------
# Sidebar controls
# ----------------------------
with st.sidebar:
    st.header("⚙️ Controls")

    company = st.text_input("Company (optional)", value="(Select / type company)")
    year_a = st.text_input("Year A", value="2023")
    year_b = st.text_input("Year B", value="2024")

    st.divider()
    st.subheader("Matching settings")
    threshold = st.slider("Similarity threshold (higher = stricter)", 0.30, 0.90, 0.62, 0.01)
    show_raw = st.toggle("Show raw extracted Item 1A text", value=False)
    st.caption("Tip: Start around 0.60–0.70. If you get too many 'New/Removed', lower it slightly.")


# ----------------------------
# Main: Upload + Run
# ----------------------------
c1, c2 = st.columns(2)
with c1:
    st.subheader(f"📎 Upload 10-K (Year {year_a})")
    file_a = st.file_uploader("Choose HTML/PDF/TXT", type=["html", "htm", "pdf", "txt"], key="fileA")

with c2:
    st.subheader(f"📎 Upload 10-K (Year {year_b})")
    file_b = st.file_uploader("Choose HTML/PDF/TXT", type=["html", "htm", "pdf", "txt"], key="fileB")

run = st.button("🚀 Run Extraction & Comparison", type="primary", use_container_width=True)

if "results" not in st.session_state:
    st.session_state.results = None

if run:
    if not file_a or not file_b:
        st.error("Please upload BOTH Year A and Year B files.")
    else:
        try:
            text_a = read_document(file_a, file_a.name.split(".")[-1].lower())
            text_b = read_document(file_b, file_b.name.split(".")[-1].lower())

            item1a_a = extract_item_1a_risk_section(text_a)
            item1a_b = extract_item_1a_risk_section(text_b)

            blocks_a = segment_risk_blocks(item1a_a, year_a)
            blocks_b = segment_risk_blocks(item1a_b, year_b)

            pairs, new_blocks, removed_blocks = match_blocks(blocks_a, blocks_b, threshold=threshold)

            st.session_state.results = {
                "company": company,
                "year_a": year_a,
                "year_b": year_b,
                "threshold": threshold,
                "count_a": len(blocks_a),
                "count_b": len(blocks_b),
                "matched": pairs,
                "new_in_b": [asdict(b) for b in new_blocks],
                "removed_in_a": [asdict(b) for b in removed_blocks],
                "blocks_a": [asdict(b) for b in blocks_a],
                "blocks_b": [asdict(b) for b in blocks_b],
                "raw_item1a_a": item1a_a if show_raw else None,
                "raw_item1a_b": item1a_b if show_raw else None,
            }
            st.success("Done. Scroll down to view results.")
        except Exception as e:
            st.error(f"Failed to process files: {e}")

# ----------------------------
# Results section
# ----------------------------
res = st.session_state.results
if res is None:
    st.info("Upload two 10-K files and click **Run Extraction & Comparison**.")
    st.stop()

# KPIs
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"<div class='kpi'><div class='small'>Risk blocks (Year {res['year_a']})</div><div style='font-size:24px;font-weight:800;'>{res['count_a']}</div></div>", unsafe_allow_html=True)
with k2:
    st.markdown(f"<div class='kpi'><div class='small'>Risk blocks (Year {res['year_b']})</div><div style='font-size:24px;font-weight:800;'>{res['count_b']}</div></div>", unsafe_allow_html=True)
with k3:
    st.markdown(f"<div class='kpi'><div class='small'>Matched blocks</div><div style='font-size:24px;font-weight:800;'>{len(res['matched'])}</div></div>", unsafe_allow_html=True)
with k4:
    st.markdown(f"<div class='kpi'><div class='small'>New / Removed</div><div style='font-size:24px;font-weight:800;'>{len(res['new_in_b'])} / {len(res['removed_in_a'])}</div></div>", unsafe_allow_html=True)

st.write("")
tab1, tab2, tab3, tab4 = st.tabs(["✅ Matched", "🆕 New in Year B", "🗑 Removed from Year A", "⬇️ Export"])

# Matched
with tab1:
    if not res["matched"]:
        st.warning("No matched blocks at the current threshold. Try lowering the similarity threshold.")
    else:
        st.caption("Matched risk blocks based on TF-IDF cosine similarity (title + content).")
        for p in sorted(res["matched"], key=lambda x: x["similarity"], reverse=True):
            st.markdown(f"**Similarity:** `{p['similarity']:.3f}`")
            cL, cR = st.columns(2)
            with cL:
                st.markdown(f"**{res['year_a']} — {p['title_a']}**")
                st.write(p["content_a"])
            with cR:
                st.markdown(f"**{res['year_b']} — {p['title_b']}**")
                st.write(p["content_b"])
            st.markdown("<hr/>", unsafe_allow_html=True)

# New in B
with tab2:
    if not res["new_in_b"]:
        st.success("No new risk blocks detected in Year B at this threshold.")
    else:
        st.caption("Blocks in Year B that did not match any Year A block above threshold.")
        for b in res["new_in_b"]:
            st.markdown(f"**{res['year_b']} — {b['title']}**  <span class='badge'>NEW</span>", unsafe_allow_html=True)
            st.write(b["content"])
            st.markdown("<hr/>", unsafe_allow_html=True)

# Removed
with tab3:
    if not res["removed_in_a"]:
        st.success("No removed risk blocks detected from Year A at this threshold.")
    else:
        st.caption("Blocks in Year A that did not match any Year B block above threshold.")
        for b in res["removed_in_a"]:
            st.markdown(f"**{res['year_a']} — {b['title']}**  <span class='badge'>REMOVED</span>", unsafe_allow_html=True)
            st.write(b["content"])
            st.markdown("<hr/>", unsafe_allow_html=True)

# Export
with tab4:
    st.caption("Download structured outputs for your report / next pipeline steps.")
    payload = {
        "company": res["company"],
        "year_a": res["year_a"],
        "year_b": res["year_b"],
        "threshold": res["threshold"],
        "summary": {
            "count_a": res["count_a"],
            "count_b": res["count_b"],
            "matched": len(res["matched"]),
            "new_in_b": len(res["new_in_b"]),
            "removed_in_a": len(res["removed_in_a"]),
        },
        "matched": res["matched"],
        "new_in_b": res["new_in_b"],
        "removed_in_a": res["removed_in_a"],
    }
    st.download_button(
        "⬇️ Download comparison JSON",
        data=json.dumps(payload, indent=2).encode("utf-8"),
        file_name=f"risk_comparison_{res['year_a']}_vs_{res['year_b']}.json",
        mime="application/json",
        use_container_width=True,
    )

    with st.expander("Preview JSON"):
        st.code(json.dumps(payload, indent=2), language="json")

if res.get("raw_item1a_a") or res.get("raw_item1a_b"):
    st.write("")
    st.subheader("Raw extracted Item 1A (optional)")
    ra, rb = st.columns(2)
    with ra:
        st.markdown(f"**Year {res['year_a']} raw Item 1A**")
        st.text_area(" ", value=res.get("raw_item1a_a") or "", height=260)
    with rb:
        st.markdown(f"**Year {res['year_b']} raw Item 1A**")
        st.text_area("  ", value=res.get("raw_item1a_b") or "", height=260)
