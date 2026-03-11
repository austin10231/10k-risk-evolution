"""Home / Introduction page."""

import streamlit as st


def render():
    # Hero section
    st.markdown(
        """
        <div style="text-align:center; padding: 1.5rem 0 1rem 0;">
            <p style="font-size:1.1rem; color:#374151; max-width:750px; margin:0 auto; line-height:1.6;">
                Upload SEC 10-K filings to automatically extract Item 1A risk factors,
                generate AI-powered summaries, compare year-over-year risk changes,
                extract core financial tables, and run an intelligent risk agent — all in one place.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # How it works - 5 steps
    st.markdown('<p style="font-size:1.5rem; font-weight:700; color:#1f2937; margin-bottom:0.8rem;">How It Works</p>', unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(
            '<div class="feature-card">'
            '<div class="step">📤</div>'
            "<h4>① Upload</h4>"
            "<p>Upload a 10-K filing (HTML or PDF) from SEC EDGAR.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="feature-card">'
            '<div class="step" style="margin-top:0.3rem; margin-bottom:0.1rem;">🔍</div>'
            "<h4>② Extract</h4>"
            "<p>Item 1 overview & Item 1A risks are extracted into structured JSON, with AI-powered executive summary.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="feature-card">'
            '<div class="step" style="margin-top:0.3rem; margin-bottom:0.1rem;">⚖️</div>'
            "<h4>③ Compare</h4>"
            "<p>Compare years to find NEW and REMOVED risks, with AI-powered change analysis, then export JSON.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            '<div class="feature-card">'
            '<div class="step">📊</div>'
            "<h4>④ Tables</h4>"
            "<p>Extract financial tables from PDF filings via AWS Textract.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            '<div class="feature-card" style="background:linear-gradient(135deg,#f0fdf4 0%,#ffffff 100%); border-color:#bbf7d0;">'
            '<div class="step">🤖</div>'
            '<h4 style="color:#166534;">⑤ Agent</h4>'
            "<p>Ask natural language questions. The AI agent scores, prioritizes, and generates a full risk intelligence report.</p>"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()

    # Features
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            """
            <div class="card" style="min-height:340px; height:340px;">
                <h4 style="text-align:center;">✅ Current Features</h4>
                <div style="display:grid; grid-template-columns:1fr 1fr; gap:0 1.2rem; font-size:0.95rem; color:#6b7280; line-height:2.2; padding-left:1.5rem;">
                    <span>• 10-K upload (HTML &amp; PDF)</span>
                    <span>• Item 1 &amp; 1A risk extraction</span>
                    <span>• AI risk summarization</span>
                    <span>• YoY / multi-year comparison</span>
                    <span>• Cross-company comparison</span>
                    <span>• AI-powered change analysis</span>
                    <span>• Financial table extraction</span>
                    <span>• JSON &amp; CSV export</span>
                    <span>• AWS S3 persistent storage</span>
                    <span>• Risk prioritization agent</span>
                    <span>• Priority scoring (H/M/L)</span>
                    <span>• Natural language queries</span>
                    <span>• Structured agent reports</span>
                    <span>• Risk intelligence report</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            """
            <div class="card" style="min-height:340px; height:340px;">
                <h4 style="text-align:center;">🔮 Future Features</h4>
                <div style="font-size:0.95rem; color:#6b7280; line-height:2.2; padding-left:1.5rem;">
                    <div>• 10-Q support</div>
                    <div>• EDGAR direct download by CIK / ticker</div>
                    <div>• Risk trend dashboard across years</div>
                    <div>• Multi-company portfolio risk view</div>
                    <div>• Automated alerts for new filings</div>
                    <div>• Risk heatmap visualization</div>
                    <div>• Peer benchmarking by industry</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Copyright footer
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background:#f0f4ff; border-radius:10px; padding:0.8rem 1.2rem; text-align:center;">
            <span style="font-size:0.8rem; color:#6b7280;">
                © 2026 · SCU · AWS Team 1 &nbsp;|&nbsp;
                Mutian He · Yuhan Luan · Jiaoqing Lu · Jiayi Yan
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
