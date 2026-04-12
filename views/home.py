"""Home page — RiskLens AI landing."""

import streamlit as st
from core.i18n import current_language, render_language_switcher


def _navigate(page: str):
    if page == "upload_records":
        st.session_state["upload_open_records"] = True
        st.session_state["current_page"] = "upload"
    else:
        st.session_state["current_page"] = page
    st.rerun()


def render():
    current_language()

    # ── Hero banner ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div class="home-hero-banner" style="position:relative; background:linear-gradient(135deg,#7dd3fc 0%,#3b82f6 40%,#2563eb 100%); border-radius:16px;
             overflow:hidden; padding:3rem 3rem 2.5rem; margin-bottom:2rem;">
            <div style="position:absolute; inset:0;
                 background-image:radial-gradient(rgba(255,255,255,0.12) 1px, transparent 1px);
                 background-size:22px 22px;"></div>
            <div style="position:absolute; top:-60px; right:-60px; width:320px; height:320px;
                 background:radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
                 pointer-events:none;"></div>
            <div style="position:relative; z-index:1;">
                <div style="display:inline-flex; align-items:center; gap:6px;
                     background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                     border-radius:20px; padding:4px 12px; margin-bottom:1.4rem;">
                    <span style="width:6px; height:6px; background:#bfdbfe; border-radius:50%;
                          display:inline-block; box-shadow:0 0 6px rgba(191,219,254,0.8);"></span>
                    <span style="font-size:11px; font-weight:600; color:#ffffff;
                          letter-spacing:0.05em; text-transform:uppercase;">
                        SEC 10-K Analysis Platform
                    </span>
                </div>
                <div style="margin-bottom:0.75rem; line-height:1.1;">
                    <span style="font-size:2.5rem; font-weight:900; color:#ffffff;
                         letter-spacing:-0.04em; display:inline;">RiskLens</span>
                    <span style="font-size:2.5rem; font-weight:900; color:#bfdbfe;
                         letter-spacing:-0.04em; display:inline;"> AI</span>
                </div>
                <p style="font-size:1.05rem; color:rgba(255,255,255,0.85); margin:0 0 0.4rem;
                   line-height:1.65; font-weight:400; white-space:nowrap;">
                    Turn 10-K filings into structured risk intelligence — extract, compare,
                    and analyze with AI in minutes.
                </p>
                <div style="display:flex; align-items:center; gap:6px; margin-top:1.1rem; flex-wrap:wrap;">
                    <span style="font-size:10.5px; color:rgba(255,255,255,0.6); letter-spacing:0.04em; font-weight:500;
                          text-transform:uppercase;">Powered by</span>
                    <span style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                          border-radius:6px; padding:2px 8px; font-size:11px; font-weight:500; color:#ffffff;">
                        AWS Bedrock
                    </span>
                    <span style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                          border-radius:6px; padding:2px 8px; font-size:11px; font-weight:500; color:#ffffff;">
                        Textract
                    </span>
                    <span style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.3);
                          border-radius:6px; padding:2px 8px; font-size:11px; font-weight:500; color:#ffffff;">
                        S3
                    </span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Overlay language switcher inside hero (stable CSS-only placement)
    st.markdown(
        """
        <style>
        .main .block-container {
            position: relative !important;
        }
        .st-key-home_hero_lang_switch {
            position: absolute !important;
            top: 4.4rem !important;
            right: 1.45rem !important;
            margin: 0 !important;
            z-index: 18;
            width: 152px !important;
        }
        .st-key-home_hero_lang_switch div[data-testid="stSegmentedControl"] {
            width: 152px !important;
            margin: 0 !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] {
            background: rgba(2, 6, 23, 0.56) !important;
            border: 1px solid rgba(148, 163, 184, 0.42) !important;
            border-radius: 9px !important;
            padding: 2px !important;
            backdrop-filter: blur(3px) !important;
            box-shadow: 0 5px 16px rgba(2, 6, 23, 0.32) !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button {
            min-height: 1.52rem !important;
            border-radius: 7px !important;
            font-size: 0.72rem !important;
            font-weight: 700 !important;
            color: rgba(203, 213, 225, 0.96) !important;
            letter-spacing: 0.01em !important;
            padding: 0.01rem 0.52rem !important;
            border: 1px solid rgba(100, 116, 139, 0.48) !important;
            background: rgba(15, 23, 42, 0.68) !important;
            box-shadow: none !important;
            transition: background 0.18s ease, border-color 0.18s ease, box-shadow 0.18s ease, color 0.18s ease !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-pressed="false"],
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-selected="false"] {
            background: rgba(15, 23, 42, 0.68) !important;
            border-color: rgba(71, 85, 105, 0.55) !important;
            color: rgba(203, 213, 225, 0.96) !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-pressed="true"],
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-selected="true"] {
            background: rgba(30, 41, 59, 0.95) !important;
            border-color: rgba(148, 163, 184, 0.62) !important;
            color: #ffffff !important;
            text-shadow: 0 1px 1px rgba(2, 6, 23, 0.50) !important;
            box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.22), 0 0 0 1px rgba(59, 130, 246, 0.14) !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button:hover {
            background: rgba(15, 23, 42, 0.82) !important;
            color: #f1f5f9 !important;
        }
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-pressed="true"]:hover,
        .st-key-home_hero_lang_switch [data-baseweb="button-group"] button[aria-selected="true"]:hover {
            background: rgba(30, 41, 59, 0.95) !important;
            color: #ffffff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    render_language_switcher("home_hero_lang")

    # ── Quick Actions ─────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1.1rem;">
            <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                 border-radius:2px; flex-shrink:0;"></div>
            <div>
                <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                   letter-spacing:-0.02em; line-height:1.2;">Quick Start</p>
                <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                    Choose where to begin across 6 core modules
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    quick_cards = [
        {
            "key": "upload",
            "icon": "📤",
            "accent": "#6366f1",
            "title": "Upload & Auto-Fetch",
            "desc": "Ingest new filings and manage saved Records in one place.",
            "buttons": [
                ("Open Upload →", "upload", "primary"),
                ("Open Records →", "upload_records", "secondary"),
            ],
        },
        {
            "key": "compare",
            "icon": "⚖️",
            "accent": "#f59e0b",
            "title": "Compare Risks",
            "desc": "Run year-over-year or cross-company comparisons to detect structural risk changes.",
            "buttons": [("Open Compare →", "compare", "secondary")],
        },
        {
            "key": "tables",
            "icon": "📊",
            "accent": "#10b981",
            "title": "Financial Tables",
            "desc": "Extract 5 core statements via Textract and store JSON/CSV for downstream analysis.",
            "buttons": [("Open Tables →", "tables", "secondary")],
        },
        {
            "key": "agent",
            "icon": "🤖",
            "accent": "#8b5cf6",
            "title": "AI Risk Agent",
            "desc": "Generate priority scores, key findings, recommendations, and full analyst-ready reports.",
            "buttons": [("Open Agent →", "agent", "secondary")],
        },
        {
            "key": "insight_hub",
            "icon": "📈",
            "accent": "#2563eb",
            "title": "Dashboard + Stock",
            "desc": "Monitor portfolio risk and market movement together in one linked workflow.",
            "buttons": [
                ("Dashboard →", "dashboard", "secondary"),
                ("Stock →", "stock", "secondary"),
            ],
        },
        {
            "key": "news",
            "icon": "📰",
            "accent": "#0ea5e9",
            "title": "News Intelligence",
            "desc": "Track recent company headlines with pressure scoring and risk-linked summaries.",
            "buttons": [
                ("Open News →", "news", "secondary"),
            ],
        },
    ]

    for row_start in range(0, len(quick_cards), 3):
        quick_cols = st.columns(3, gap="medium")
        for col, card in zip(quick_cols, quick_cards[row_start:row_start + 3]):
            with col:
                accent = card["accent"]
                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;
                         padding:1.15rem 1.05rem 0.95rem; margin-bottom:0.42rem;
                         box-shadow:0 1px 3px rgba(15,23,42,0.05);
                         border-top:3px solid {accent}; min-height:150px;">
                        <p style="font-size:1.56rem; margin:0 0 0.58rem; line-height:1;">{card['icon']}</p>
                        <p style="font-weight:700; color:#0f172a; margin:0 0 0.3rem;
                           font-size:0.97rem; letter-spacing:-0.01em;">{card['title']}</p>
                        <p style="font-size:0.81rem; color:#64748b; margin:0; line-height:1.48;">
                            {card['desc']}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                if len(card["buttons"]) == 1:
                    label, page, btn_type = card["buttons"][0]
                    if st.button(
                        label,
                        key=f"qa_{card['key']}_{page}",
                        use_container_width=True,
                        type=btn_type,
                    ):
                        _navigate(page)
                else:
                    button_cols = st.columns(len(card["buttons"]), gap="small")
                    for bcol, (label, page, btn_type) in zip(button_cols, card["buttons"]):
                        with bcol:
                            if st.button(
                                label,
                                key=f"qa_{card['key']}_{page}",
                                use_container_width=True,
                                type=btn_type,
                            ):
                                _navigate(page)
        if row_start + 3 < len(quick_cards):
            st.markdown("<div style='height:0.42rem;'></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── How It Works ──────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1.1rem;">
            <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                 border-radius:2px; flex-shrink:0;"></div>
            <div>
                <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                   letter-spacing:-0.02em; line-height:1.2;">How It Works</p>
                <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                    Keep the same 6-step flow, now with market and news linkage
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        ("1", "#6366f1", "📥", "Ingest Filing", "Use manual upload or SEC EDGAR auto-fetch to create a new filing record."),
        ("2", "#0ea5e9", "🧠", "Extract Risks", "Parse Item 1/1A with Standard rules or AI-enhanced Bedrock extraction."),
        ("3", "#10b981", "📊", "Extract Tables", "Run Textract to capture key financial statements and persist outputs."),
        ("4", "#f59e0b", "⚖️", "Compare Changes", "Detect NEW / REMOVED / MODIFIED risks across years or companies."),
        ("5", "#8b5cf6", "🤖", "Run Agent", "Score impact/likelihood/urgency and generate structured analyst guidance."),
        ("6", "#2563eb", "📰", "Link Market + News", "Overlay risk ratings with stock context and ranked recent news evidence."),
    ]

    for row_start in range(0, len(steps), 3):
        row_cols = st.columns(3, gap="medium")
        for col, (idx, color, icon, title, desc) in zip(row_cols, steps[row_start:row_start + 3]):
            with col:
                st.markdown(
                    f"""
                    <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;
                         padding:0.95rem 0.95rem 0.9rem; box-shadow:0 1px 2px rgba(15,23,42,0.04);
                         min-height:132px;">
                        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:0.45rem;">
                            <span style="font-size:0.68rem; font-weight:700; color:{color}; letter-spacing:0.05em;">
                                STEP {idx}
                            </span>
                            <div style="width:32px; height:32px; background:{color}12; border:1px solid {color}33;
                                 border-radius:9px; display:flex; align-items:center; justify-content:center;
                                 font-size:1rem;">{icon}</div>
                        </div>
                        <p style="font-size:0.84rem; font-weight:700; color:#0f172a; margin:0 0 0.22rem;
                           letter-spacing:-0.01em;">{title}</p>
                        <p style="font-size:0.75rem; color:#64748b; margin:0; line-height:1.45;">
                            {desc}
                        </p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        if row_start + 3 < len(steps):
            st.markdown("<div style='height:0.45rem;'></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Features & Roadmap ────────────────────────────────────────────────────
    col_a, col_b = st.columns(2, gap="large")

    with col_a:
        st.markdown(
            """
            <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1.1rem;">
                <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                     border-radius:2px; flex-shrink:0;"></div>
                <div>
                    <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                       letter-spacing:-0.02em; line-height:1.2;">Current Features</p>
                    <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                        What's available today
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        features = [
            ("End-to-end 10-K workflow", "Ingest → Extract → Compare → Agent"),
            ("Dual risk extraction modes", "Standard + AI-Enhanced"),
            ("Financial table pipeline", "Textract + JSON/CSV persistence"),
            ("Structured risk storage and reusable records", "S3-backed"),
            ("Cross-year and cross-company change detection", "NEW / REMOVED / MODIFIED"),
            ("AI agent scoring and recommendations", "Impact / Likelihood / Urgency"),
            ("Risk monitoring dashboard", "Heatmap + ranking + risk/return"),
            ("Dedicated stock analytics page", "Search + price/volume charts"),
            ("News intelligence module", "Headline pressure + risk linkage"),
            ("Global configuration sync across core workflows", "Company / Year / Industry / Ticker"),
            ("Cloud persistence and analyst export views", "JSON / CSV / report"),
        ]
        rows = "".join(
            f'<div style="display:flex; justify-content:space-between; align-items:center;'
            f'padding:0.45rem 0; border-bottom:1px solid #f1f5f9;">'
            f'<span style="font-size:0.81rem; color:#334155; display:flex; align-items:center; gap:6px;">'
            f'<span style="color:#6366f1; font-weight:700;">✓</span>{feat}</span>'
            f'<span style="font-size:0.69rem; color:#94a3b8; font-weight:500; white-space:nowrap;">{tag}</span>'
            f'</div>'
            for feat, tag in features
        )
        st.markdown(
            f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;'
            f'padding:1rem 1.3rem; box-shadow:0 1px 3px rgba(15,23,42,0.04);">{rows}</div>',
            unsafe_allow_html=True,
        )

    with col_b:
        st.markdown(
            """
            <div style="display:flex; align-items:center; gap:0.75rem; margin:0 0 1.1rem;">
                <div style="width:4px; height:28px; background:linear-gradient(180deg,#3b82f6,#2563eb);
                     border-radius:2px; flex-shrink:0;"></div>
                <div>
                    <p style="font-size:1.05rem; font-weight:800; color:#0f172a; margin:0;
                       letter-spacing:-0.02em; line-height:1.2;">Future Releases</p>
                    <p style="font-size:0.75rem; color:#64748b; margin:0; font-weight:400;">
                        Next optimization priorities
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        roadmap = [
            ("Higher extraction consistency and confidence calibration", "Accuracy"),
            ("Stronger risk-market-news linkage scoring", "Correlation"),
            ("Lower page latency via warm cache and lazy loading", "Performance"),
            ("Better evidence ranking and duplicate-news suppression", "Signal Quality"),
            ("More explainable agent reasoning trace for analysts", "Trust"),
        ]
        rows = "".join(
            f'<div style="display:flex; justify-content:space-between; align-items:center;'
            f'padding:0.45rem 0; border-bottom:1px solid #f1f5f9;">'
            f'<span style="font-size:0.81rem; color:#64748b; display:flex; align-items:center; gap:6px;">'
            f'<span style="color:#c7d2fe; font-size:0.65rem;">◆</span>{feat}</span>'
            f'<span style="font-size:0.69rem; color:#94a3b8; font-weight:500; white-space:nowrap;">{tag}</span>'
            f'</div>'
            for feat, tag in roadmap
        )
        # Future releases card
        st.markdown(
            f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;'
            f'overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.04);">'
            f'<div style="background:linear-gradient(90deg,#2563eb,#3b82f6); padding:0.7rem 1.3rem;">'
            f'<p style="font-size:0.72rem; font-weight:600; color:#a5b4fc; margin:0; letter-spacing:0.04em;">'
            f'🔮 Planned next</p></div>'
            f'<div style="padding:0.4rem 1.3rem 0.6rem;">{rows}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            """
            <div style="margin-top:0.75rem; background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;
                 padding:0.9rem 1.15rem; box-shadow:0 1px 2px rgba(15,23,42,0.04);">
                <p style="font-size:0.77rem; color:#64748b; margin:0; line-height:1.55;">
                    Current modules are feature-complete for the end-to-end workflow. Future iterations focus on
                    improving accuracy, cross-signal relevance, and interaction speed as company coverage expands.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── Footer ────────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:10px;
             padding:0.8rem 1.3rem; display:flex; align-items:center; justify-content:space-between;
             box-shadow:0 1px 2px rgba(15,23,42,0.03);">
            <span style="font-size:0.75rem; color:#64748b; font-weight:500;">
                RiskLens<span style="color:#6366f1; font-weight:700;">AI</span>
                &nbsp;·&nbsp; SCU × AWS Team 1
            </span>
            <span style="font-size:0.72rem; color:#94a3b8;">
                Mutian He · Yuhan Luan · Jiaoqing Lu · Jiayi Yan &nbsp;·&nbsp; © 2026
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
