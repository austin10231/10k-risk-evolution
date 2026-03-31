"""Home page — RiskLens AI landing."""

import streamlit as st


def _navigate(page: str):
    st.session_state["current_page"] = page
    st.rerun()


def render():

    # ── Hero banner ───────────────────────────────────────────────────────────
    st.markdown(
        """
        <div style="position:relative; background:linear-gradient(135deg,#7dd3fc 0%,#3b82f6 40%,#2563eb 100%); border-radius:16px;
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
                    Choose where to begin
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
            "title": "Upload & Extract",
            "desc": "Analyze a new 10-K filing (HTML or PDF) or auto-fetch from SEC EDGAR.",
            "buttons": [("Start Analyzing →", "upload", "primary")],
        },
        {
            "key": "library",
            "icon": "📚",
            "accent": "#0ea5e9",
            "title": "Browse Library",
            "desc": "View, filter, and load previously analyzed filings and saved table results.",
            "buttons": [("Open Library →", "library", "secondary")],
        },
        {
            "key": "agent",
            "icon": "🤖",
            "accent": "#8b5cf6",
            "title": "Run AI Agent",
            "desc": "Ask questions in plain English and get prioritized risk insights instantly.",
            "buttons": [("Open Agent →", "agent", "secondary")],
        },
        {
            "key": "monitor",
            "icon": "📈",
            "accent": "#10b981",
            "title": "Monitor Risk + Market",
            "desc": "Track risk trend and stock context together across Dashboard and Stock tabs.",
            "buttons": [
                ("Open Dashboard →", "dashboard", "secondary"),
                ("Open Stock →", "stock", "secondary"),
            ],
        },
    ]

    quick_cols = st.columns(4, gap="medium")
    for col, card in zip(quick_cols, quick_cards):
        with col:
            accent = card["accent"]
            st.markdown(
                f"""
                <div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;
                     padding:1.2rem 1.15rem 1rem; margin-bottom:0.45rem;
                     box-shadow:0 1px 3px rgba(15,23,42,0.05);
                     border-top:3px solid {accent}; min-height:158px;">
                    <p style="font-size:1.62rem; margin:0 0 0.62rem; line-height:1;">{card['icon']}</p>
                    <p style="font-weight:700; color:#0f172a; margin:0 0 0.34rem;
                       font-size:1rem; letter-spacing:-0.01em;">{card['title']}</p>
                    <p style="font-size:0.83rem; color:#64748b; margin:0; line-height:1.5;">
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
                for label, page, btn_type in card["buttons"]:
                    if st.button(
                        label,
                        key=f"qa_{card['key']}_{page}",
                        use_container_width=True,
                        type=btn_type,
                    ):
                        _navigate(page)

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
                    From ingestion to monitoring in 6 steps
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    steps = [
        ("1", "#6366f1", "📥", "Ingest Filing", "Manual upload or SEC EDGAR auto-fetch."),
        ("2", "#0ea5e9", "🧠", "Extract Risks", "Standard parser or AI-enhanced Nova Pro mode."),
        ("3", "#10b981", "📊", "Extract Tables", "Run Textract to capture 5 core financial statements."),
        ("4", "#f59e0b", "⚖️", "Compare Changes", "Detect NEW / REMOVED / MODIFIED risks across years."),
        ("5", "#8b5cf6", "🤖", "Run Agent", "Generate priority score, findings, and recommendations."),
        ("6", "#2563eb", "📈", "Monitor & Trade Context", "Track in Dashboard + Stock with market linkage."),
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
            ("10-K upload (HTML & PDF)", "Extraction"),
            ("SEC EDGAR auto-fetch (Analyze + Tables)", "Direct ingest"),
            ("Item 1 & 1A risk parsing", "Structured JSON"),
            ("AI-enhanced extraction mode", "Nova Pro"),
            ("AI risk classification", "Amazon Bedrock"),
            ("AI executive summary", "Auto-generated"),
            ("Year-over-year comparison", "Multi-year"),
            ("Cross-company risk diff", "Side-by-side"),
            ("AI change analysis", "Trend detection"),
            ("Financial table extraction (Textract)", "5 statements"),
            ("Library table persistence + one-click extract", "Reusable"),
            ("Risk heatmap dashboard", "Visual matrix"),
            ("Industry-group category ranking", "By industry"),
            ("Risk vs return analytics", "Market linked"),
            ("Dedicated stock tab (search + charts)", "Live market"),
            ("Risk prioritization agent", "H / M / L scoring"),
            ("Natural language queries", "Free-text Q&A"),
            ("JSON & CSV export", "Full download"),
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
                        Coming in future releases
                    </p>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        roadmap = [
            ("10-Q support", "Quarterly filings"),
            ("Portfolio risk view", "Multi-company"),
            ("Automated alerts", "New filing notifications"),
            ("Peer benchmarking upgrade", "Cross-industry"),
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

        st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)

        news_rows = "".join(
            f'<div style="display:flex; justify-content:space-between; align-items:center;'
            f'padding:0.5rem 0; border-bottom:1px solid #f1f5f9;">'
            f'<span style="font-size:0.81rem; color:#334155; display:flex; align-items:center; gap:6px;">'
            f'<span style="color:#3b82f6; font-size:0.78rem;">●</span>{title}</span>'
            f'<span style="font-size:0.69rem; color:#94a3b8; font-weight:500; white-space:nowrap;">{tag}</span>'
            f'</div>'
            for title, tag in [
                ("Company major news feed", "Real-time"),
                ("Ticker + company watchlist headlines", "Personalized"),
                ("Event impact summary (market + risk)", "AI digest"),
                ("News-to-risk link markers in dashboard", "Context layer"),
            ]
        )
        st.markdown(
            f'<div style="background:#ffffff; border:1px solid #e2e8f0; border-radius:12px;'
            f'overflow:hidden; box-shadow:0 1px 3px rgba(15,23,42,0.04);">'
            f'<div style="background:linear-gradient(90deg,#0ea5e9,#2563eb); padding:0.7rem 1.3rem;">'
            f'<p style="font-size:0.72rem; font-weight:600; color:#dbeafe; margin:0; letter-spacing:0.04em;">'
            f'📰 News Intelligence (Planned)</p></div>'
            f'<div style="padding:0.55rem 1.3rem 0.75rem;">{news_rows}'
            f'<p style="font-size:0.72rem; color:#64748b; margin:0.55rem 0 0; line-height:1.55;">'
            f'Goal: surface recent major news for selected companies so analysts can quickly connect'
            f' filing risk changes with external events.</p></div>'
            f'</div>',
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
