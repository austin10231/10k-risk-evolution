"""
Risk Change Alert Report — Entry Point
Run: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Risk Change Alert Report",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Light-theme CSS overrides ────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* Force light background */
    .stApp { background-color: #f8f9fb; }
    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e0e3e8; }
    /* Card helper */
    .card {
        background: #ffffff; border: 1px solid #e0e3e8; border-radius: 10px;
        padding: 1.2rem 1.4rem; margin-bottom: 1rem;
    }
    /* Metric labels */
    [data-testid="stMetricLabel"] { font-size: 0.82rem; color: #6b7280; }
    /* Download buttons */
    .stDownloadButton > button {
        background-color: #2563eb; color: white; border: none; border-radius: 6px;
    }
    .stDownloadButton > button:hover { background-color: #1d4ed8; }
    /* Expander header */
    .streamlit-expanderHeader { font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar navigation ──────────────────────────────────────────────────────
st.sidebar.image(
    "https://img.icons8.com/fluency/48/shield.png", width=40
)
st.sidebar.title("Risk Change Alert")
st.sidebar.caption("10-K Risk Factors Analysis")

page = st.sidebar.radio(
    "Navigation",
    ["🏠 Home", "🔍 Analyze", "⚖️ Compare"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.info("MVP Scope: **Item 1A – Risk Factors** (text only)")

# ── Route to pages ───────────────────────────────────────────────────────────
if page == "🏠 Home":
    from pages.home import render
    render()
elif page == "🔍 Analyze":
    from pages.analyze import render
    render()
elif page == "⚖️ Compare":
    from pages.compare import render
    render()
