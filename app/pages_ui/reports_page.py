"""
reports_page.py

TODO integration: list actual generated reports from app/core/report_generator.py
(e.g. store generated PDF paths per campaign) instead of the static mock list.
"""

import streamlit as st
import pandas as pd
import os
import tempfile
from app.components import section_header, card
from app.core.report_generator import generate_pdf_report

MOCK_REPORTS = pd.DataFrame(
    {
        "Report": ["Senior Software Engineer — Shortlist", "Product Manager — Shortlist", "Data Analyst — Full Report"],
        "Generated": ["2026-04-28", "2026-04-20", "2026-04-15"],
        "Candidates": [48, 12, 30],
    }
)


def render():
    section_header("Reports", "Download generated shortlist and full assessment reports")
    results = st.session_state.get("pipeline_results", [])
    campaign = st.session_state.get("campaign", {})
    with card():
        report_df = MOCK_REPORTS.copy()
        if results:
            report_df = pd.DataFrame({
                "Report": [f"{campaign.get('title', 'Active campaign')} - Shortlist"],
                "Generated": [pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")],
                "Candidates": [len(results)],
            })
        st.dataframe(report_df, use_container_width=True, hide_index=True)
        if st.button("Generate New Report", type="primary", disabled=not results):
            output_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
            try:
                generate_pdf_report(results, campaign.get("requirements", {}), output_path)
                with open(output_path, "rb") as report_file:
                    st.download_button(
                        "Download PDF",
                        report_file.read(),
                        file_name="talent-intelligence-shortlist.pdf",
                        mime="application/pdf",
                    )
            except Exception as exc:
                st.error(f"Report generation failed: {exc}")
            finally:
                if os.path.exists(output_path):
                    os.unlink(output_path)
        elif not results:
            st.caption("Process candidates from the Candidates page to generate a report.")
