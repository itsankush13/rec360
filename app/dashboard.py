"""
dashboard.py — Main entry point for the Talent Intelligence System UI.

Run with:
    PYTHONPATH=. streamlit run app/dashboard.py

This file only handles page config, theme injection, and routing.
Each screen's actual content lives in app/pages_ui/*.py so this stays
readable as you wire in real agent output.

⚠️ Merge note: if you already have a dashboard.py with working pipeline
calls (JD Agent / Resume Parser / Scoring / Bias Audit), don't overwrite it —
instead:
  1. Keep your existing page functions/logic.
  2. Copy app/theme.py and app/components.py in as-is.
  3. Replace just the sidebar nav + st.set_page_config block below with your
     existing routing, calling inject_theme() right after set_page_config.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from app.theme import inject_theme
from app.components import sidebar_nav
from app.pages_ui import (
    dashboard_page,
    campaigns_page,
    candidates_page,
    reports_page,
    integrations_page,
    settings_page,
)

st.set_page_config(
    page_title="Talent Intelligence System",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

if "page" not in st.session_state:
    st.session_state["page"] = "dashboard"

current_page = sidebar_nav(st.session_state["page"])

PAGES = {
    "dashboard": dashboard_page.render,
    "campaigns": campaigns_page.render,
    "candidates": candidates_page.render,
    "reports": reports_page.render,
    "integrations": integrations_page.render,
    "settings": settings_page.render,
}

PAGES.get(current_page, dashboard_page.render)()
