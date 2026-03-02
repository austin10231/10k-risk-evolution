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
                and extract core financial tables — all in one place.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # How it works - 4 steps
    st.markdown('<p style="font-size:1.5rem; font-weight:700; color:#1f2937; margin-bottom:0.8rem;">How It Works</p>', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
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

    st.markdown("<br>", unsafe_allow_html=True)
    st.divider()

    # Features
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            """
            <div class="card" style="min-height:300px; height:300px;">
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
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            """
            <div class="card" style="min-height:300px; height:300px;">
                <h4 style="text-align:center;">🔮 Future Features</h4>
                <div style="font-size:0.95rem; color:#6b7280; line-height:2.2; padding-left:1.5rem;">
                    <div>• 10-Q support</div>
                    <div>• Risk trend dashboard</div>
                    <div>• EDGAR direct download by CIK / ticker</div>
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
