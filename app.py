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
    /* ── Global ────────────────────────────────────────── */
    .stApp { background-color: #f8f9fb; color: #1f2937; }
    section[data-testid="stSidebar"] { display: none !important; }
    h1,h2,h3,h4,h5,h6,p,span,li,label,div { color: #1f2937; }

    /* ── Top header bar ───────────────────────────────── */
    .top-bar {
        background: linear-gradient(135deg, #7dd3fc 0%, #3b82f6 40%, #2563eb 100%);
        padding: 1.4rem 2rem;
        border-radius: 12px;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .top-bar h1 {
        color: #ffffff !important;
        font-size: 2rem;
        margin: 0;
        font-weight: 800;
        text-shadow: 0 1px 4px rgba(30,58,138,0.25);
    }
    .top-bar .subtitle {
        color: #eff6ff;
        font-size: 1rem;
        margin: 0;
        font-weight: 500;
    }

    /* ── Navigation tabs ──────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 10px;
        padding: 4px;
        gap: 4px;
        margin-bottom: 1.2rem;
    }
    .stTabs [data-baseweb="tab"] {
        color: #6b7280;
        font-weight: 500;
        font-size: 0.95rem;
        padding: 0.6rem 1.5rem;
        border-radius: 8px;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: #f0f4ff;
        color: #2563eb;
    }
    .stTabs [aria-selected="true"] {
        background: #3b82f6 !important;
        color: #ffffff !important;
        font-weight: 600;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }

    /* ── Cards ─────────────────────────────────────────── */
    .card {
        background: #ffffff;
        border: 1px solid #e0e3e8;
        border-radius: 12px;
        padding: 1.4rem 1.5rem;
        margin-bottom: 1rem;
        color: #1f2937;
        transition: box-shadow 0.2s;
    }
    .card:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .card h4 { color: #111827; margin-bottom: 0.5rem; }
    .card p { color: #6b7280; font-size: 0.9rem; line-height: 1.5; }

    /* ── Feature cards for home ────────────────────────── */
    .feature-card {
        background: linear-gradient(135deg, #eff6ff 0%, #ffffff 100%);
        border: 1px solid #bfdbfe;
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        min-height: 140px;
    }
    .feature-card .step {
        font-size: 2rem;
        margin-bottom: 0.3rem;
    }
    .feature-card h4 {
        color: #1e40af;
        margin: 0.3rem 0;
    }
    .feature-card p {
        color: #6b7280;
        font-size: 0.85rem;
    }

    /* ── Metrics ───────────────────────────────────────── */
    [data-testid="stMetricLabel"] { font-size: .82rem; color: #6b7280!important; }
    [data-testid="stMetricValue"] { color: #111827!important; }

    /* ── Buttons ───────────────────────────────────────── */
    .stDownloadButton>button {
        background: #60a5fa; color: #fff!important; border: none; border-radius: 8px;
        font-weight: 500;
    }
    .stDownloadButton>button:hover { background: #3b82f6; }
    div.stButton>button[kind="primary"],
    div.stButton>button[data-testid="stBaseButton-primary"] {
        background: #2563eb !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px;
        font-weight: 500;
    }
    div.stButton>button[kind="primary"]:hover,
    div.stButton>button[data-testid="stBaseButton-primary"]:hover {
        background: #1d4ed8 !important;
    }

    /* ── Form inputs ──────────────────────────────────── */
    .stSelectbox label, .stTextInput label, .stFileUploader label {
        color: #374151 !important;
        font-weight: 500;
    }
    [data-testid="stAlert"] { color: #1f2937; border-radius: 8px; }

    /* ── Expander ─────────────────────────────────────── */
    .streamlit-expanderHeader {
        font-weight: 500;
        border-radius: 8px;
    }

    /* ── Section headers ──────────────────────────────── */
    .section-header {
        background: #f0f4ff;
        border-left: 4px solid #2563eb;
        padding: 0.6rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0 0.8rem 0;
        font-weight: 600;
        color: #1e40af;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Top header ──────────────────────────────────────────
st.markdown(
    """
    <div class="top-bar">
        <div>
            <h1>🛡️ Risk Change Alert Report</h1>
            <p class="subtitle">SEC 10-K Risk Factors Analysis & Comparison Tool</p>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Navigation tabs ─────────────────────────────────────
tab_home, tab_analyze, tab_compare, tab_tables = st.tabs(
    ["🏠  Home", "🔍  Analyze", "⚖️  Compare", "📊  Tables"]
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
