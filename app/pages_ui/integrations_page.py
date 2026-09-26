"""
integrations_page.py

Net-new: your platform currently has no ATS/HR integration layer at all.
This is a UI shell for when that gets built (likely via REST/webhook
connectors to Workday, Greenhouse, Lever, SAP SuccessFactors, etc.)
"""

import streamlit as st
from app.components import section_header, card, status_badge, placeholder_notice

CONNECTORS = [
    {"name": "Workday", "status": "Not Connected"},
    {"name": "Greenhouse", "status": "Not Connected"},
    {"name": "Lever", "status": "Not Connected"},
    {"name": "SAP SuccessFactors", "status": "Not Connected"},
]


def render():
    section_header("Integrations", "Connect to ATS and HR platforms to push shortlists and pull requisitions")
    for conn in CONNECTORS:
        with card():
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{conn['name']}**")
            c2.markdown(status_badge(conn["status"]), unsafe_allow_html=True)
            c3.button("Connect", key=f"connect_{conn['name']}")
    placeholder_notice("ATS/HR platform integrations (API keys, field mapping, webhook sync)")
