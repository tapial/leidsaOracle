"""LeidsaOracle — Streamlit Dashboard Application."""

from __future__ import annotations

import os

import streamlit as st

API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="LeidsaOracle",
    page_icon="🎱",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Sidebar navigation
st.sidebar.title("LeidsaOracle")
st.sidebar.markdown(
    "LEIDSA Lottery Statistical Analysis\n\n"
    "*Probabilistic research tool — lottery draws are random.*"
)

page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Analysis", "Generator", "Backtest"],
    index=0,
)

if page == "Dashboard":
    from src.ui.pages.dashboard import render
    render(API_BASE)
elif page == "Analysis":
    from src.ui.pages.analysis import render
    render(API_BASE)
elif page == "Generator":
    from src.ui.pages.generator import render
    render(API_BASE)
elif page == "Backtest":
    from src.ui.pages.backtest import render
    render(API_BASE)
