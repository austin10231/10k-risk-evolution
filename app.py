"""
Risk Change Alert Report — Entry Point
Run:  streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Risk Change Alert Report",
    page_icon="🛡️",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp { background-color: #f8f9fb; color: #1f2937; }
    section[data-testid="stSidebar"] { display: none !important; }
    h1,h2,h3,h4,h5,h6,p,span,li,label,div { color: #1f2937; }
    .card {
        background:#fff; border:1px solid #e0e3e8; border-radius:10px;
        padding:1.2rem 1.4rem; margin-bottom:1rem; color:#1f2937;
    }
    .card h4 { color:#111827; } .card p { color:#374151; }
    [data-testid="stMetricLabel"]  { font-size:.82rem; color:#6b7280!important; }
    [data-testid="stMetricValue"]  { color:#111827!important; }
    .stDownloadButton>button {
        background:#2563eb; color:#fff!important; border:none; border-radius:6px;
    }
    .stDownloadButton>button:hover { background:#1d4ed8; }
    .stSelectbox label,.stTextInput label,.stFileUploader label { color:#374151!important; }
    .stTabs [data-baseweb="tab"] { color:#374151; }
    [data-testid="stAlert"] { color:#1f2937; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown("### 🛡️ Risk Change Alert Report")

tab_home, tab_analyze, tab_compare, tab_tables = st.tabs(
    ["🏠 Home", "🔍 Analyze", "⚖️ Compare", "📊 Tables"]
)

with tab_home:
    from views.home import render as render_home
    render_home()

with tab_analyze:
    from views.analyze import render as render_analyze
    render_analyze()

with tab_compare:
    from views.compare import render as render_compare
    render_compare()

with tab_tables:
    from views.tables import render as render_tables
    render_tables()
