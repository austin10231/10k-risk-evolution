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
    /* Force light background & dark text globally */
    .stApp { background-color: #f8f9fb; color: #1f2937; }
    section[data-testid="stSidebar"] {
        background-color: #ffffff; border-right: 1px solid #e0e3e8;
    }
    section[data-testid="stSidebar"] * { color: #1f2937; }
    h1, h2, h3, h4, h5, h6, p, span, li, label, div { color: #1f2937; }
    .stMarkdown, .stText, [data-testid="stMarkdownContainer"] { color: #1f2937; }
    /* Card helper */
    .card {
        background: #ffffff; border: 1px solid #e0e3e8; border-radius: 10px;
        padding: 1.2rem 1.4rem; margin-bottom: 1rem; color: #1f2937;
    }
    .card h4 { color: #111827; }
    .card p  { color: #374151; }
    /* Metric */
    [data-testid="stMetricLabel"] { font-size: 0.82rem; color: #6b7280 !important; }
    [data-testid="stMetricValue"] { color: #111827 !important; }
    /* Download buttons */
    .stDownloadButton > button {
        background-color: #2563eb; color: white !important; border: none; border-radius: 6px;
    }
    .stDownloadButton > button:hover { background-color: #1d4ed8; }
    /* Expander header */
    .streamlit-expanderHeader { font-weight: 600; color: #1f2937; }
    /* Selectbox / input text */
    .stSelectbox label, .stTextInput label, .stFileUploader label { color: #374151 !important; }
    /* Tabs */
    .stTabs [data-baseweb="tab"] { color: #374151; }
    /* Info/Warning/Success boxes */
    [data-testid="stAlert"] { color: #1f2937; }
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
