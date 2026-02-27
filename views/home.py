"""Home / Introduction page."""

import streamlit as st


def render():
    # Hero section
    st.markdown(
        """
        <div style="text-align:center; padding: 1.5rem 0 1rem 0;">
            <p style="font-size:1.1rem; color:#374151; max-width:700px; margin:0 auto; line-height:1.6;">
                Automatically extract, structure, and compare SEC 10-K Risk Factors (Item 1A)
                across filing years — producing a memo-ready risk change report.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # How it works - 4 steps
    st.markdown('<p style="font-size:1.2rem; font-weight:700; color:#1f2937; margin-bottom:0.8rem;">How It Works</p>', unsafe_allow_html=True)

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
            '<div class="step">🔍</div>'
            "<h4>② Extract</h4>"
            "<p>Item 1 overview & Item 1A risks are extracted into structured JSON.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            '<div class="feature-card">'
            '<div class="step">⚖️</div>'
            "<h4>③ Compare</h4>"
            "<p>Compare years to find NEW and REMOVED risks, then export JSON.</p>"
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
            <div class="card">
                <h4>✅ Current Features</h4>
                <p>
                    • 10-K filing upload (HTML & PDF)<br>
                    • Item 1 overview + Item 1A hierarchical risk extraction<br>
                    • PDF text extraction via AWS Textract<br>
                    • Financial statement table extraction (PDF)<br>
                    • AI-powered risk summarization (AWS Bedrock)<br>
                    • YoY / multi-year NEW & REMOVED comparison<br>
                    • AI-powered change analysis<br>
                    • JSON & CSV export<br>
                    • AWS S3 persistent storage
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_b:
        st.markdown(
            """
            <div class="card">
                <h4>🔮 Phase 2</h4>
                <p>
                    • 10-Q support<br>
                    • Cross-company risk comparison<br>
                    • Risk trend dashboard<br>
                    • EDGAR direct download by CIK / ticker
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # Tech stack footer
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        """
        <div style="background:#f0f4ff; border-radius:10px; padding:0.8rem 1.2rem; text-align:center;">
            <span style="font-size:0.8rem; color:#6b7280;">
                <strong>Tech Stack:</strong> Python · Streamlit · BeautifulSoup · PyPDF2 · boto3 &nbsp;|&nbsp;
                <strong>AWS:</strong> S3 · Textract · Bedrock · IAM &nbsp;|&nbsp;
                <strong>Deploy:</strong> Streamlit Cloud + GitHub
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
