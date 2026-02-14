import json
import streamlit as st
from typing import Any, Dict, List, Optional

def render_header():
    st.title("Risk Change Alert Report")
    st.caption("MVP: SEC 10-K HTML → Item 1A Risk Factors → Structured JSON (+ YoY Compare)")

def render_sidebar_nav(pages: List[tuple]) -> str:
    st.sidebar.header("Navigation")
    labels = [f"{p[0]}  ·  {p[1]}" for p in pages]
    choice = st.sidebar.radio("Go to", labels, index=0)
    return choice.split("  ·  ")[0]

def json_viewer(data: Dict[str, Any], title: str = "JSON Preview"):
    st.subheader(title)
    st.json(data)

def download_json_button(payload, filename: str, label: str = "Download JSON", key: str | None = None):
    import json
    import hashlib

    if key is None:
        # 用文件名+payload hash生成稳定且唯一的key，避免重复组件ID
        h = hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:10]
        key = f"dl-{filename}-{h}"

    st.download_button(
        label=label,
        data=json.dumps(payload, indent=2, ensure_ascii=False),
        file_name=filename,
        mime="application/json",
        use_container_width=True,
        key=key,
    )


def info_kv_card(title: str, kv: Dict[str, Any]):
    st.subheader(title)
    cols = st.columns(3)
    items = list(kv.items())
    for i, (k, v) in enumerate(items):
        cols[i % 3].metric(label=str(k), value=str(v))

def risk_blocks_list(blocks: List[Dict[str, Any]]):
    st.subheader("Risk Blocks")
    if not blocks:
        st.info("No risk blocks found.")
        return

    for i, b in enumerate(blocks, start=1):
        with st.expander(f"{i}. [{b.get('risk_theme','unknown')}] {b.get('title','(no title)')[:80]}"):
            st.caption(f"block_id: {b.get('block_id')} | locator: {b.get('evidence_pointer')}")
            st.write(b.get("risk_text", ""))

def changes_table(changes: List[Dict[str, Any]]):
    st.subheader("Top Risk Changes")
    if not changes:
        st.info("No changes generated.")
        return

    rows = []
    for c in changes:
        rows.append({
            "theme": c.get("risk_theme"),
            "change_type": c.get("change_type"),
            "score": c.get("change_score"),
            "summary": c.get("short_explanation", ""),
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)

def side_by_side_evidence(old_text: Optional[str], new_text: Optional[str]):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Prior (t-1)")
        st.write(old_text or "")
    with col2:
        st.markdown("### Latest (t)")
        st.write(new_text or "")
