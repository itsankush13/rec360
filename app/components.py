"""
components.py — Reusable UI building blocks for the dashboard.

Import these into app/dashboard.py and any page module:

    from app.components import sidebar_nav, kpi_row, status_badge, card, section_header, progress_bar
"""

import streamlit as st
from app.theme import COLORS, STATUS_STYLE

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
NAV_ITEMS = [
    ("dashboard", "📊", "Dashboard"),
    ("campaigns", "🗂️", "Campaigns"),
    ("candidates", "👥", "Candidates"),
    ("reports", "📄", "Reports"),
    ("integrations", "🔌", "Integrations"),
    ("settings", "⚙️", "Settings"),
]


def sidebar_nav(current_page: str) -> str:
    """
    Renders the sidebar nav and returns the selected page key.
    Keeps selection in st.session_state["page"] so it persists across reruns.
    """
    with st.sidebar:
        st.markdown('<div class="nav-title">🧠 Talent Intelligence</div>', unsafe_allow_html=True)
        for key, icon, label in NAV_ITEMS:
            active = key == current_page
            prefix = "●  " if active else ""
            if st.button(f"{prefix}{icon}  {label}", key=f"nav_{key}", use_container_width=True):
                st.session_state["page"] = key
        st.markdown("---")
        st.caption("v0.1 · Talent Intelligence System")
    return st.session_state.get("page", current_page)


# ---------------------------------------------------------------------------
# Section header
# ---------------------------------------------------------------------------
def section_header(title: str, subtitle: str | None = None):
    st.markdown(f'<div class="tis-section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="tis-section-sub">{subtitle}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# KPI tiles — pass a list of dicts: {"label", "value", "delta" (optional, e.g. "+4%"), "up" (bool)}
# ---------------------------------------------------------------------------
def kpi_row(items: list[dict]):
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            delta_html = ""
            if item.get("delta"):
                cls = "tis-kpi-delta-up" if item.get("up", True) else "tis-kpi-delta-down"
                arrow = "▲" if item.get("up", True) else "▼"
                delta_html = f'<div class="{cls}">{arrow} {item["delta"]}</div>'
            st.markdown(
                f"""
                <div class="tis-card">
                    <div class="tis-kpi-label">{item['label']}</div>
                    <div class="tis-kpi-value">{item['value']}</div>
                    {delta_html}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# Status badge — e.g. status_badge("Strong Fit")
# ---------------------------------------------------------------------------
def status_badge(label: str) -> str:
    """Returns an HTML span. Use with st.markdown(..., unsafe_allow_html=True)
    or embed inside a larger markdown string / dataframe column render."""
    key = label.strip().lower()
    color_key, bg_key = STATUS_STYLE.get(key, ("info", "info_soft"))
    color = COLORS[color_key] if color_key != "neutral" else COLORS["text_secondary"]
    bg = COLORS[bg_key]
    return f'<span class="tis-badge" style="color:{color}; background:{bg};">{label}</span>'


def status_badge_md(label: str):
    """Convenience: renders the badge directly."""
    st.markdown(status_badge(label), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Progress bar — value 0-100
# ---------------------------------------------------------------------------
def progress_bar(value: float, label: str | None = None, color: str | None = None):
    color = color or COLORS["accent"]
    value = max(0, min(100, value))
    label_html = f'<div style="font-size:0.8rem; color:{COLORS["text_secondary"]}; margin-bottom:4px;">{label}</div>' if label else ""
    st.markdown(
        f"""
        {label_html}
        <div class="tis-progress-track">
            <div class="tis-progress-fill" style="width:{value}%; background:{color};"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Card container — use as a context manager:
#   with card("Title"):
#       st.write(...)
# ---------------------------------------------------------------------------
class card:
    def __init__(self, title: str | None = None):
        self.title = title

    def __enter__(self):
        st.markdown('<div class="tis-card">', unsafe_allow_html=True)
        if self.title:
            st.markdown(f"#### {self.title}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        st.markdown("</div>", unsafe_allow_html=True)


def placeholder_notice(feature_name: str):
    """Use on stub pages for capabilities the client asked for but that aren't built yet."""
    st.info(
        f"🚧 **{feature_name}** is on the roadmap — this screen is a UI placeholder so the "
        f"navigation and layout are in place. Wire up real data/logic when ready.",
    )
