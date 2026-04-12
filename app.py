"""
RiskLens AI — SEC 10-K Risk Intelligence Platform
Entry point: streamlit run app.py
"""

import streamlit as st
from core.global_context import ensure_global_context
from core.i18n import (
    ensure_language_state,
    inject_dom_translation,
    nav_text,
)

st.set_page_config(
    page_title="RiskLens AI · 10-K Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Design System ──────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Inter Font + Material Icons ──────────────────────────────────────── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons+Round');

    /* ── Base ─────────────────────────────────────────────────────────────── */
    html, body, .stApp, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    }
    .stApp { background-color: #f1f5f9 !important; }
    h1,h2,h3,h4,h5,h6 { color: #0f172a !important; font-family: 'Inter', sans-serif !important; }
    p, li, label, div { font-family: 'Inter', sans-serif !important; }
    /* Restore Material Icons / Symbols font — exception to the Inter override above */
    span.material-icons,
    span.material-icons-round,
    span.material-icons-outlined,
    span[class*="material-icons"],
    span[class*="material-symbols"] {
        font-family: 'Material Symbols Rounded', 'Material Icons Round', 'Material Icons' !important;
    }
    .main .block-container {
        padding: 2.0rem 2.4rem 3rem !important;
        max-width: 100% !important;
    }
    .block-container {
        padding-top: 2.0rem !important;
    }
    .block-container > div:first-child {
        margin-top: 0 !important;
    }

    /* ── Dark Sidebar ──────────────────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: #1e293b !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
        min-width: 248px !important;
        max-width: 248px !important;
        transition: min-width 0.3s cubic-bezier(0.4,0,0.2,1),
                    max-width 0.3s cubic-bezier(0.4,0,0.2,1) !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    section[data-testid="stSidebar"].sb-collapsed {
        min-width: 0 !important;
        max-width: 0 !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-top: 0 !important;
    }
    /* Footer sticks to bottom of the scrollable sidebar */
    .sb-footer {
        position: sticky !important;
        bottom: 0 !important;
    }

    /* Sidebar scrollbar */
    section[data-testid="stSidebar"]::-webkit-scrollbar { width: 4px; }
    section[data-testid="stSidebar"]::-webkit-scrollbar-track { background: transparent; }
    section[data-testid="stSidebar"]::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

    /* Hide Streamlit's native sidebar collapse button */
    [data-testid="stSidebarCollapseButton"],
    [data-testid="stSidebarCollapsedControl"] {
        display: none !important;
    }

    /* Smooth toggle pill handle */
    #sb-toggle {
        position: fixed;
        top: 50%;
        transform: translateY(-50%);
        left: 248px;
        z-index: 99999;
        width: 16px;
        height: 48px;
        background: #1e293b;
        border: 1px solid rgba(255,255,255,0.15);
        border-left: none;
        border-radius: 0 8px 8px 0;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 2px 0 8px rgba(0,0,0,0.18);
        transition: left 0.3s cubic-bezier(0.4,0,0.2,1), background 0.15s;
        padding: 0;
    }
    #sb-toggle:hover { background: #334155; }
    #sb-toggle .sb-arrow {
        color: rgba(255,255,255,0.6);
        font-size: 13px;
        font-family: -apple-system, sans-serif;
        line-height: 1;
        font-weight: 300;
        user-select: none;
        transition: color 0.15s;
    }
    #sb-toggle:hover .sb-arrow { color: #ffffff; }

    /* Active nav item — left border indicator via :has() */
    section[data-testid="stSidebar"] div[data-testid="stButton"]:has([data-testid="stBaseButton-primary"]) {
        border-left: 2.5px solid #ffffff;
        border-radius: 0 !important;
    }

    /* Sidebar nav buttons — inactive */
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
        background: transparent !important;
        border: none !important;
        color: rgba(255,255,255,0.6) !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        font-weight: 400 !important;
        font-size: 13.5px !important;
        padding: 7px 14px 7px 12px !important;
        border-radius: 6px !important;
        letter-spacing: 0.01em !important;
        transition: background 0.15s, color 0.15s !important;
        width: 100% !important;
    }
    section[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
        background: rgba(255,255,255,0.1) !important;
        color: #ffffff !important;
        border: none !important;
    }

    /* Sidebar nav buttons — active */
    section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
        background: rgba(255,255,255,0.15) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: none !important;
        text-align: left !important;
        justify-content: flex-start !important;
        font-weight: 600 !important;
        font-size: 13.5px !important;
        padding: 7px 14px 7px 10px !important;
        border-radius: 0 6px 6px 0 !important;
        letter-spacing: 0.01em !important;
        width: 100% !important;
    }

    /* ── Sidebar button overrides (must come after global rules) ─────────────── */
    section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-secondary"] {
        background: transparent !important;
        border: none !important;
        color: rgba(255,255,255,0.7) !important;
        box-shadow: none !important;
        font-weight: 400 !important;
        font-size: 13.5px !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 7px 14px 7px 12px !important;
        border-radius: 6px !important;
        letter-spacing: 0.01em !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-secondary"]:hover {
        background: rgba(255,255,255,0.12) !important;
        border: none !important;
        color: #ffffff !important;
    }
    section[data-testid="stSidebar"] div.stButton > button[data-testid="stBaseButton-primary"] {
        background: rgba(255,255,255,0.18) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: none !important;
        font-weight: 600 !important;
        font-size: 13.5px !important;
        text-align: left !important;
        justify-content: flex-start !important;
        padding: 7px 14px 7px 10px !important;
        border-radius: 0 6px 6px 0 !important;
        letter-spacing: 0.01em !important;
    }

    /* ── Page header ───────────────────────────────────────────────────────── */
    .page-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.6rem;
        padding-bottom: 1.2rem;
        border-bottom: 1px solid #e2e8f0;
    }
    .page-header-left { display: flex; align-items: center; gap: 0.85rem; }
    .page-icon {
        font-size: 1.5rem;
        background: #eef2ff;
        border: 1px solid #c7d2fe;
        padding: 0.4rem 0.5rem;
        border-radius: 10px;
        line-height: 1;
        flex-shrink: 0;
    }
    .page-title {
        font-size: 1.3rem !important;
        font-weight: 800 !important;
        color: #0f172a !important;
        margin: 0 !important;
        line-height: 1.2 !important;
        letter-spacing: -0.02em !important;
    }
    .page-subtitle {
        font-size: 0.8rem !important;
        color: #64748b !important;
        margin: 0.15rem 0 0 !important;
        font-weight: 400 !important;
    }

    /* ── Cards ──────────────────────────────────────────────────────────────── */
    .card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1.3rem 1.5rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.04), 0 1px 2px rgba(15,23,42,0.02);
        margin-bottom: 1rem;
        transition: box-shadow 0.2s ease, transform 0.2s ease;
    }
    .card:hover {
        box-shadow: 0 4px 16px rgba(15,23,42,0.08), 0 2px 4px rgba(15,23,42,0.04);
        transform: translateY(-1px);
    }

    /* Record cards in Library */
    .record-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 1rem 1.1rem;
        margin-bottom: 0.4rem;
        transition: border-color 0.15s, box-shadow 0.15s;
    }
    .record-card:hover {
        border-color: #c7d2fe;
        box-shadow: 0 2px 8px rgba(99,102,241,0.08);
    }
    .record-card.active {
        border-color: #6366f1;
        background: #fafafe;
    }

    /* ── Badges ────────────────────────────────────────────────────────────── */
    .badge {
        display: inline-block;
        padding: 0.13rem 0.55rem;
        border-radius: 20px;
        font-size: 0.68rem;
        font-weight: 600;
        white-space: nowrap;
        letter-spacing: 0.01em;
    }
    .badge-indigo { background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; }
    .badge-blue   { background: #eff6ff; color: #1e40af; }
    .badge-gray   { background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }
    .badge-green  { background: #f0fdf4; color: #166534; }
    .badge-red    { background: #fef2f2; color: #b91c1c; }
    .badge-amber  { background: #fffbeb; color: #92400e; }

    /* ── Metric cards ───────────────────────────────────────────────────────── */
    .metric-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 0.9rem 1rem;
        text-align: center;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04);
    }
    .metric-label {
        font-size: 0.6rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin: 0;
    }
    .metric-value {
        font-size: 1.3rem;
        font-weight: 800;
        color: #0f172a;
        margin: 0.2rem 0 0;
        line-height: 1.2;
        letter-spacing: -0.02em;
    }

    /* ── Stepper ───────────────────────────────────────────────────────────── */
    .stepper {
        display: flex;
        align-items: center;
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin-bottom: 1.6rem;
        box-shadow: 0 1px 3px rgba(15,23,42,0.04);
    }
    .step-item { display: flex; align-items: center; gap: 0.55rem; flex: 1; }
    .step-circle {
        width: 26px; height: 26px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.7rem; font-weight: 700; flex-shrink: 0;
    }
    .step-circle.active  { background: #6366f1; color: #fff; }
    .step-circle.done    { background: #22c55e; color: #fff; }
    .step-circle.pending { background: #e2e8f0; color: #94a3b8; }
    .step-text { font-size: 0.8rem; font-weight: 500; }
    .step-text.active  { color: #4338ca; font-weight: 600; }
    .step-text.done    { color: #166534; }
    .step-text.pending { color: #94a3b8; }
    .step-connector { flex: 0 0 1.5rem; height: 2px; background: #e2e8f0; margin: 0 0.3rem; }
    .step-connector.done { background: #22c55e; }

    /* ── Section headers ────────────────────────────────────────────────────── */
    .section-label {
        font-size: 0.65rem;
        font-weight: 700;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        margin: 1.5rem 0 0.65rem;
    }
    .section-header {
        background: #eef2ff;
        border-left: 3px solid #6366f1;
        padding: 0.55rem 1rem;
        border-radius: 0 8px 8px 0;
        margin: 1.2rem 0 0.85rem;
        font-weight: 600;
        font-size: 0.85rem;
        color: #3730a3;
    }

    /* ── Empty state ────────────────────────────────────────────────────────── */
    .empty-state {
        text-align: center;
        padding: 4rem 2rem;
        background: #ffffff;
        border: 1.5px dashed #e2e8f0;
        border-radius: 16px;
    }
    .empty-state-icon { font-size: 2.4rem; margin-bottom: 0.6rem; }
    .empty-state-title { font-size: 1rem; font-weight: 600; color: #334155; margin: 0; }
    .empty-state-sub { font-size: 0.82rem; color: #94a3b8; margin: 0.35rem 0 0; font-weight: 400; }

    /* ── Buttons ────────────────────────────────────────────────────────────── */
    div.stButton > button[data-testid="stBaseButton-primary"] {
        background: #3b82f6 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        letter-spacing: 0.01em !important;
        box-shadow: 0 1px 3px rgba(59,130,246,0.3) !important;
        transition: background 0.15s, box-shadow 0.15s !important;
    }
    div.stButton > button[data-testid="stBaseButton-primary"]:hover {
        background: #2563eb !important;
        box-shadow: 0 4px 12px rgba(59,130,246,0.35) !important;
    }
    div.stButton > button[data-testid="stBaseButton-secondary"] {
        background: #ffffff !important;
        border: 1px solid #e2e8f0 !important;
        color: #374151 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        box-shadow: 0 1px 2px rgba(15,23,42,0.04) !important;
    }
    div.stButton > button[data-testid="stBaseButton-secondary"]:hover {
        background: #f8fafc !important;
        border-color: #c7d2fe !important;
        color: #3730a3 !important;
    }

    .stDownloadButton > button {
        background: #ffffff !important;
        color: #374151 !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        font-size: 0.83rem !important;
        box-shadow: 0 1px 2px rgba(15,23,42,0.03) !important;
    }
    .stDownloadButton > button:hover {
        background: #f8fafc !important;
        border-color: #c7d2fe !important;
    }

    /* ── Form inputs ────────────────────────────────────────────────────────── */
    .stSelectbox label, .stTextInput label, .stFileUploader label {
        font-size: 0.79rem !important;
        font-weight: 500 !important;
        color: #374151 !important;
        letter-spacing: 0.01em !important;
    }
    [data-baseweb="select"] { border-radius: 8px !important; }
    [data-baseweb="input"]  { border-radius: 8px !important; }

    /* ── Tabs ───────────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 3px; gap: 2px;
        margin-bottom: 1rem;
    }
    .stTabs [data-baseweb="tab"] {
        color: #64748b; font-weight: 500;
        font-size: 0.85rem; padding: 0.45rem 1.1rem;
        border-radius: 8px; background: transparent;
        letter-spacing: 0.01em;
    }
    .stTabs [data-baseweb="tab"]:hover { background: #eef2ff; color: #4338ca; }
    .stTabs [aria-selected="true"] {
        background: #6366f1 !important;
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"],
    .stTabs [data-baseweb="tab-border"] { display: none; }

    /* ── Alerts & metrics ───────────────────────────────────────────────────── */
    [data-testid="stAlert"] {
        border-radius: 10px !important;
        font-size: 0.85rem !important;
        font-family: 'Inter', sans-serif !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem !important;
        color: #64748b !important;
        font-weight: 500 !important;
    }
    [data-testid="stMetricValue"] {
        color: #0f172a !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
    }

    /* ── Expander ───────────────────────────────────────────────────────────── */
    .streamlit-expanderHeader {
        font-weight: 500 !important;
        font-size: 0.85rem !important;
        border-radius: 8px !important;
        color: #334155 !important;
    }

    /* ── Fix dropdown caret font in BaseWeb selects to avoid overlapping arrow text ─ */
    [data-baseweb="select"] span[aria-hidden="true"] {
        font-family: 'Material Symbols Rounded', 'Material Icons Round', 'Material Icons' !important;
    }

    /* ── Segmented control ─────────────────────────────────────────────────── */
    [data-testid="stSegmentedControl"] { border-radius: 8px !important; }

    /* ── Divider ────────────────────────────────────────────────────────────── */
    hr { border-color: #e2e8f0 !important; }

    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "home"
ensure_global_context()
ensure_language_state()

from core.chat_widget import render_chat_widget


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:

    # Brand
    st.markdown(
        """
        <div style="padding:1.4rem 1.1rem 1.1rem; border-bottom:1px solid rgba(255,255,255,0.12);
             margin-bottom:0.4rem;">
            <div style="display:flex; align-items:center; gap:0.65rem;">
                <div style="width:32px; height:32px; background:linear-gradient(135deg,#2563eb,#3b82f6);
                     border-radius:8px; display:flex; align-items:center; justify-content:center;
                     flex-shrink:0; font-size:1rem;">📊</div>
                <div>
                    <p style="font-size:1.1rem; font-weight:800; color:#ffffff; margin:0;
                       line-height:1.2; letter-spacing:-0.02em;">
                        RiskLens<span style="color:#93c5fd;">AI</span>
                    </p>
                    <p style="font-size:0.7rem; color:rgba(255,255,255,0.55); margin:0.1rem 0 0; letter-spacing:0.02em;">
                        10-K Risk Intelligence
                    </p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cur = st.session_state["current_page"]

    def _nav(label, key):
        if st.button(label, key=f"nav_{key}", use_container_width=True,
                     type="primary" if cur == key else "secondary"):
            st.session_state["current_page"] = key
            st.rerun()

    # DATA group
    st.markdown(
        '<p style="font-size:0.58rem; font-weight:700; color:rgba(255,255,255,0.6);'
        'letter-spacing:0.1em; text-transform:uppercase; padding:0 0.9rem;'
        f'margin:1rem 0 0.25rem;">{nav_text("DATA")}</p>',
        unsafe_allow_html=True,
    )
    _nav(f"🏠  {nav_text('Home')}", "home")
    _nav(f"➕  {nav_text('Upload')}", "upload")
    _nav(f"📈  {nav_text('Dashboard')}", "dashboard")
    _nav(f"💹  {nav_text('Stock')}", "stock")
    _nav(f"📰  {nav_text('News')}", "news")
    _nav(f"📚  {nav_text('Library')}", "library")

    # ANALYSIS group
    st.markdown(
        '<p style="font-size:0.58rem; font-weight:700; color:rgba(255,255,255,0.6);'
        'letter-spacing:0.1em; text-transform:uppercase; padding:0 0.9rem;'
        f'margin:1.1rem 0 0.25rem;">{nav_text("ANALYSIS")}</p>',
        unsafe_allow_html=True,
    )
    _nav(f"⚖️  {nav_text('Compare')}", "compare")
    _nav(f"📊  {nav_text('Tables')}", "tables")

    # AI group
    st.markdown(
        '<p style="font-size:0.58rem; font-weight:700; color:rgba(255,255,255,0.6);'
        'letter-spacing:0.1em; text-transform:uppercase; padding:0 0.9rem;'
        f'margin:1.1rem 0 0.25rem;">{nav_text("INTELLIGENCE")}</p>',
        unsafe_allow_html=True,
    )
    _nav(f"🤖  {nav_text('Agent')}", "agent")

    # Footer — absolutely positioned at bottom of sidebar
    st.markdown(
        """
        <div class="sb-footer" style="padding:0.9rem 1.1rem;
             border-top:1px solid rgba(255,255,255,0.12);
             background:#1e293b; white-space:nowrap;">
            <div style="display:flex; align-items:center; gap:0.5rem;">
                <div style="width:6px; height:6px; background:#22c55e; border-radius:50%;
                     box-shadow:0 0 6px #22c55e; flex-shrink:0;"></div>
                <p style="font-size:0.65rem; color:rgba(255,255,255,0.45); margin:0; letter-spacing:0.02em;">
                    © 2026 SCU · AWS Team 1
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Sidebar toggle (pure JS/CSS, no rerun) ────────────────────────────────────
import streamlit.components.v1 as components
components.html(
    """
    <script>
    (function() {
        var pdoc = window.parent.document;
        var pwin = window.parent;
        var SB_WIDTH = 248;

        function getSidebar() {
            return pdoc.querySelector('section[data-testid="stSidebar"]');
        }

        function applyState(collapsed, animate) {
            var sb = getSidebar();
            var btn = pdoc.getElementById('sb-toggle');
            var arrow = btn ? btn.querySelector('.sb-arrow') : null;
            if (!sb || !btn) return;

            if (!animate) {
                sb.style.transition = 'none';
                btn.style.transition = 'none';
            }
            if (collapsed) {
                sb.classList.add('sb-collapsed');
                btn.style.left = '0px';
                if (arrow) arrow.textContent = '\\u203a'; /* › */
            } else {
                sb.classList.remove('sb-collapsed');
                btn.style.left = SB_WIDTH + 'px';
                if (arrow) arrow.textContent = '\\u2039'; /* ‹ */
            }
            if (!animate) {
                setTimeout(function() {
                    sb.style.transition = '';
                    btn.style.transition = '';
                }, 30);
            }
        }

        function initSidebarToggle() {
            if (pdoc.getElementById('sb-toggle')) {
                // Already exists — just sync state on rerun
                var collapsed = pwin.localStorage.getItem('sb-collapsed') === '1';
                applyState(collapsed, false);
                return;
            }

            var btn = pdoc.createElement('button');
            btn.id = 'sb-toggle';
            btn.setAttribute('aria-label', 'Toggle navigation');
            var arrow = pdoc.createElement('span');
            arrow.className = 'sb-arrow';
            btn.appendChild(arrow);
            pdoc.body.appendChild(btn);

            var collapsed = pwin.localStorage.getItem('sb-collapsed') === '1';
            applyState(collapsed, false);

            btn.addEventListener('click', function() {
                collapsed = !collapsed;
                pwin.localStorage.setItem('sb-collapsed', collapsed ? '1' : '0');
                applyState(collapsed, true);
            });
        }

        function waitForSidebar() {
            if (pdoc.querySelector('section[data-testid="stSidebar"]')) {
                initSidebarToggle();
            } else {
                var obs = new MutationObserver(function() {
                    if (pdoc.querySelector('section[data-testid="stSidebar"]')) {
                        obs.disconnect();
                        initSidebarToggle();
                    }
                });
                obs.observe(pdoc.body, { childList: true, subtree: true });
            }
        }

        waitForSidebar();
    })();
    </script>
    """,
    height=0,
)

# ── Route to page ──────────────────────────────────────────────────────────────
page = st.session_state["current_page"]

if page == "home":
    from views.home import render as _render
    _render()
elif page == "dashboard":
    from views.dashboard import render as _render
    _render()
elif page == "stock":
    from views.stock import render as _render
    _render()
elif page == "news":
    from views.news import render as _render
    _render()
elif page == "library":
    from views.library import render as _render
    _render()
elif page == "upload":
    from views.upload import render as _render
    _render()
elif page == "compare":
    from views.compare import render as _render
    _render()
elif page == "tables":
    from views.tables import render as _render
    _render()
elif page == "agent":
    from views.agent import render as _render
    _render()

# ── Global floating assistant (all pages) ─────────────────────────────────────
render_chat_widget(page)

# ── Apply global DOM translation for zh mode ──────────────────────────────────
inject_dom_translation()
