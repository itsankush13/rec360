"""
theme.py — Central visual theme for the Talent Intelligence System dashboard.

Drop this file into app/theme.py and call inject_theme() once at the top of
app/dashboard.py (right after st.set_page_config(...)).

Design targets the reference mockup:
- Dark navy sidebar (#0f1729 / #16213a)
- Light, airy content area (#f4f6fb)
- White rounded cards with soft shadows
- Colored status badges (Strong Fit / Review Required / Not Recommended, etc.)
- Blue accent for primary actions and progress bars
"""

import streamlit as st

# ---------------------------------------------------------------------------
# Palette — change these to re-skin the whole app
# ---------------------------------------------------------------------------
COLORS = {
    "sidebar_bg": "#0f1729",
    "sidebar_bg_active": "#1d2b4a",
    "sidebar_text": "#aab4c9",
    "sidebar_text_active": "#ffffff",
    "content_bg": "#f4f6fb",
    "card_bg": "#ffffff",
    "border": "#e6e9f0",
    "text_primary": "#111827",
    "text_secondary": "#6b7280",
    "accent": "#2563eb",
    "accent_soft": "#e8efff",
    "success": "#16a34a",
    "success_soft": "#e7f7ec",
    "warning": "#d97706",
    "warning_soft": "#fef3e2",
    "danger": "#dc2626",
    "danger_soft": "#fdeaea",
    "info": "#0284c7",
    "info_soft": "#e3f3fb",
    "neutral_soft": "#eef0f4",
}

# Map a status label (as it appears throughout the product spec) to a badge style
STATUS_STYLE = {
    "strong fit": ("success", "success_soft"),
    "confirmed match": ("success", "success_soft"),
    "shortlisted": ("success", "success_soft"),
    "processed": ("success", "success_soft"),
    "potential fit": ("info", "info_soft"),
    "partial or adjacent match": ("info", "info_soft"),
    "in progress": ("info", "info_soft"),
    "review required": ("warning", "warning_soft"),
    "insufficient evidence": ("warning", "warning_soft"),
    "on hold": ("warning", "warning_soft"),
    "not recommended": ("danger", "danger_soft"),
    "not demonstrated": ("danger", "danger_soft"),
    "contradictory evidence": ("danger", "danger_soft"),
    "failed": ("danger", "danger_soft"),
    "rejected": ("danger", "danger_soft"),
    "duplicate": ("neutral", "neutral_soft"),
}


def inject_theme():
    """Injects global CSS. Call once, immediately after st.set_page_config()."""
    c = COLORS
    st.markdown(
        f"""
        <style>
        /* ---------- App shell ---------- */
        .stApp {{
            background-color: {c['content_bg']};
        }}
        [data-testid="stSidebar"] {{
            background-color: {c['sidebar_bg']};
            border-right: 1px solid #0a1120;
        }}
        [data-testid="stSidebar"] * {{
            color: {c['sidebar_text']};
        }}
        [data-testid="stSidebar"] .nav-title {{
            color: {c['sidebar_text_active']};
            font-weight: 700;
            font-size: 1.05rem;
            padding: 0.4rem 0 1.1rem 0;
        }}
        section.main > div {{
            padding-top: 1.2rem;
        }}

        /* ---------- Sidebar nav buttons ---------- */
        [data-testid="stSidebar"] .stButton > button {{
            width: 100%;
            text-align: left;
            background: transparent;
            border: none;
            color: {c['sidebar_text']};
            font-size: 0.92rem;
            padding: 0.5rem 0.7rem;
            border-radius: 8px;
            margin-bottom: 2px;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{
            background: {c['sidebar_bg_active']};
            color: {c['sidebar_text_active']};
        }}
        [data-testid="stSidebar"] .stButton > button:focus {{
            box-shadow: none !important;
        }}

        /* ---------- Cards ---------- */
        .tis-card {{
            background: {c['card_bg']};
            border: 1px solid {c['border']};
            border-radius: 14px;
            padding: 1.1rem 1.3rem;
            box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            margin-bottom: 1rem;
        }}
        .tis-card h4 {{
            margin: 0 0 0.6rem 0;
            font-size: 0.95rem;
            color: {c['text_primary']};
        }}

        /* ---------- KPI tiles ---------- */
        .tis-kpi-label {{
            color: {c['text_secondary']};
            font-size: 0.8rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}
        .tis-kpi-value {{
            color: {c['text_primary']};
            font-size: 1.9rem;
            font-weight: 700;
            line-height: 1.2;
        }}
        .tis-kpi-delta-up {{ color: {c['success']}; font-size: 0.82rem; font-weight: 600; }}
        .tis-kpi-delta-down {{ color: {c['danger']}; font-size: 0.82rem; font-weight: 600; }}

        /* ---------- Section headers ---------- */
        .tis-section-title {{
            font-size: 1.25rem;
            font-weight: 700;
            color: {c['text_primary']};
            margin-bottom: 0.9rem;
        }}
        .tis-section-sub {{
            color: {c['text_secondary']};
            font-size: 0.88rem;
            margin-top: -0.6rem;
            margin-bottom: 1rem;
        }}

        /* ---------- Badges ---------- */
        .tis-badge {{
            display: inline-block;
            padding: 0.18rem 0.65rem;
            border-radius: 999px;
            font-size: 0.76rem;
            font-weight: 600;
            white-space: nowrap;
        }}

        /* ---------- Progress bar ---------- */
        .tis-progress-track {{
            background: {c['neutral_soft']};
            border-radius: 999px;
            height: 8px;
            width: 100%;
            overflow: hidden;
        }}
        .tis-progress-fill {{
            background: {c['accent']};
            height: 8px;
            border-radius: 999px;
        }}

        /* ---------- Data table tweaks ---------- */
        [data-testid="stDataFrame"] {{
            border: 1px solid {c['border']};
            border-radius: 10px;
        }}

        /* Hide default Streamlit chrome for a more "product" feel */
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        </style>
        """,
        unsafe_allow_html=True,
    )
