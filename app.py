import streamlit as st
from UI.page_analyze import render_analyze_page
from UI.page_compare import render_compare_page
from UI.components import render_header, render_sidebar_nav

st.set_page_config(page_title="Risk Change Alert", layout="wide")

def main():
    render_header()

    page = render_sidebar_nav(
        pages=[
            ("Analyze", "Single filing → structured JSON"),
            ("Compare", "Year-over-year risk change"),
        ]
    )

    if page == "Analyze":
        render_analyze_page()
    elif page == "Compare":
        render_compare_page()

if __name__ == "__main__":
    main()
