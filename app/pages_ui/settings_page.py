"""
settings_page.py — Screen 12: Audit & Administration

TODO integration: replace MOCK_AUDIT with real log entries. You already log
HR overrides per your README ("HR Override + audit log") — surface that
log here instead of / in addition to CSV or console output.
"""

import streamlit as st
import pandas as pd
from app.components import section_header, card

MOCK_AUDIT = pd.DataFrame(
    {
        "Date & Time": ["2026-04-28 14:32", "2026-04-28 11:15", "2026-04-26 09:10", "2026-04-25 18:22"],
        "User": ["Priya Nair", "Aarav Sharma", "Neha Gupta", "Rohan Das"],
        "Action": ["Rubric Approved", "Candidate Score Overridden", "Comments Added", "Shortlisted"],
        "Details": ["v1.2", "Rahul Sharma — adjusted +6", "For Priya Menon", "Amit Verma"],
    }
)


def render():
    section_header("Audit & Administration", "Configuration versions, overrides, and processing logs")

    tab_audit, tab_config = st.tabs(["Audit Logs", "Configuration"])

    with tab_audit:
        with card():
            c1, c2, c3 = st.columns(3)
            c1.selectbox("Action Type", ["All Actions", "Rubric Approved", "Score Overridden", "Shortlisted"])
            c2.selectbox("User", ["All Users", "Priya Nair", "Aarav Sharma", "Neha Gupta", "Rohan Das"])
            c3.date_input("Date range")
            st.dataframe(MOCK_AUDIT, use_container_width=True, hide_index=True)
            st.button("Export Logs")

    with tab_config:
        with card("Environment"):
            st.write("**LLM Provider:** Groq (Llama-3.3-70b)")
            st.write("**Embeddings:** all-MiniLM-L6-v2")
            st.write("**Vector DB:** FAISS (in-memory)")
        with card("Users & Roles"):
            st.dataframe(
                pd.DataFrame({"User": ["Aarav Sharma", "Priya Nair"], "Role": ["Recruiter", "Hiring Manager"]}),
                use_container_width=True,
                hide_index=True,
            )
