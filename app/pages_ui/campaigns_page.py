"""
campaigns_page.py — Screens 2 (Campaign & Job Setup), 3 (Requirement Extraction),
4 (Rubric Configuration & Approval), 11 (Campaign Control Tower)

TODO integration:
- "New Campaign" tab: on submit, call app.agents.jd_agent to extract requirements
  from the pasted/uploaded JD, then populate the "Requirements" tab.
- "Rubric" tab: today your scoring weights are hardcoded in scoring_agent.py
  (Skills 30% / Experience 25% / Education 15% / Portfolio 20% / Comms 10%).
  This UI lets a recruiter edit + "approve" a rubric version — you'll need a
  small store (SQLite table, e.g. reuse tenants.db) to persist versions.
- "Control Tower" tab: wire to pipeline.py batch status once batch processing
  exists (see candidates_page.py TODO for bulk upload).
"""

import streamlit as st
import pandas as pd
from app.components import section_header, card, kpi_row, progress_bar, placeholder_notice
from app.agents.jd_agent import parse_jd

MOCK_SKILLS = ["Java", "Python", "SQL", "AWS", "Docker", "Kubernetes", "React", "Node.js"]

DEFAULT_RUBRIC = [
    {"Criterion": "Skills & Technical Expertise", "Weight": 25, "Type": "Mandatory"},
    {"Criterion": "Experience & Relevance", "Weight": 20, "Type": "Mandatory"},
    {"Criterion": "Education & Certifications", "Weight": 10, "Type": "Mandatory"},
    {"Criterion": "Industry Experience", "Weight": 10, "Type": "Preferred"},
    {"Criterion": "Role Seniority", "Weight": 10, "Type": "Preferred"},
    {"Criterion": "Cultural Fit", "Weight": 5, "Type": "Informational"},
]


def render():
    section_header("Campaigns", "Set up roles, extract requirements, configure and approve the scoring rubric")

    if "campaign" not in st.session_state:
        st.session_state["campaign"] = {
            "title": "Senior Software Engineer",
            "jd_text": "",
            "requirements": None,
            "rubric": pd.DataFrame(DEFAULT_RUBRIC),
        }
    campaign = st.session_state["campaign"]

    tab_list, tab_new, tab_req, tab_rubric, tab_tower = st.tabs(
        ["All Campaigns", "New Campaign", "Requirements", "Rubric", "Control Tower"]
    )

    # --- All Campaigns ---
    with tab_list:
        with card():
            df = pd.DataFrame(
                {
                    "Campaign": ["Senior Software Engineer", "Product Manager", "Data Analyst"],
                    "Business Unit": ["Engineering", "Product", "Analytics"],
                    "Recruiter": ["Aarav Sharma", "Priya Nair", "Neha Gupta"],
                    "Candidates": [1248, 340, 512],
                    "Status": ["Active", "Active", "Draft"],
                }
            )
            active_title = campaign.get("requirements", {}).get("role_title", campaign.get("title", "Senior Software Engineer"))
            df.loc[0, "Campaign"] = active_title
            st.dataframe(df, use_container_width=True, hide_index=True)

    # --- New Campaign (screen 2) ---
    with tab_new:
        with card("Job Details"):
            c1, c2 = st.columns(2)
            with c1:
                campaign["title"] = st.text_input("Job Title *", value=campaign.get("title", ""), placeholder="Senior Software Engineer")
                st.text_input("Location *", placeholder="Bangalore, India")
                st.text_input("Recruiter *", placeholder="Aarav Sharma")
            with c2:
                st.number_input("Vacancies *", min_value=1, value=10)
                st.text_input("Business Unit *", placeholder="Engineering")
                st.text_input("Hiring Manager *", placeholder="Priya Nair")
            st.date_input("Target Date")
            campaign["jd_text"] = st.text_area(
                "Paste Job Description", value=campaign.get("jd_text", ""), height=150,
                placeholder="Paste the JD here — the JD Agent will extract requirements automatically.",
            )
            if st.button("Extract Requirements", type="primary", key="extract_requirements"):
                if not campaign["jd_text"].strip():
                    st.warning("Add a job description before extracting requirements.")
                else:
                    with st.spinner("Extracting requirements with the JD agent..."):
                        try:
                            campaign["requirements"] = parse_jd(campaign["jd_text"])
                            st.success("Requirements extracted. Review them in the Requirements tab.")
                        except Exception as exc:
                            st.error(f"Requirement extraction failed: {exc}")

    # --- Requirements (screen 3) ---
    with tab_req:
        requirements = campaign.get("requirements") or {}
        with card("Extracted Skills"):
            skills = requirements.get("required_skills", MOCK_SKILLS)
            st.write(" · ".join(skills) if skills else "No required skills extracted yet.")
        c1, c2 = st.columns(2)
        with c1:
            with card("Experience"):
                st.write(f"Minimum Experience: **{requirements.get('min_experience_years', 'Not specified')} years**")
                st.write(f"Seniority: **{requirements.get('seniority_level', 'Not specified')}**")
                st.write(f"Role: **{requirements.get('role_title', campaign.get('title', 'Not specified'))}**")
        with c2:
            with card("Qualifications & Certifications"):
                st.write(requirements.get("education_requirement", "Not specified"))
                responsibilities = requirements.get("key_responsibilities", [])
                if responsibilities:
                    st.write("**Key responsibilities**")
                    for item in responsibilities[:5]:
                        st.write(f"- {item}")

    # --- Rubric (screen 4) ---
    with tab_rubric:
        with card("Evaluation Rubric — v1.2 (Draft)"):
            edited = st.data_editor(
                campaign.get("rubric", pd.DataFrame(DEFAULT_RUBRIC)),
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
            )
            campaign["rubric"] = edited
            total = edited["Weight"].sum() if not edited.empty else 0
            if total != 100:
                st.warning(f"Weights sum to {total}%, not 100%. Adjust before approving.")
            else:
                st.success("Weights sum to 100%.")
            b1, b2 = st.columns([1, 1])
            b1.button("Save Draft")
            b2.button("Submit for Approval", type="primary")
            st.caption("Rubric is kept in the active session and used as the review configuration for this campaign.")

    # --- Control Tower (screen 11) ---
    with tab_tower:
        kpi_row(
            [
                {"label": "Total Candidates", "value": "1,248"},
                {"label": "Processed", "value": "1,120 (90%)"},
                {"label": "In Progress", "value": "98 (8%)"},
                {"label": "Errors", "value": "30 (2%)"},
            ]
        )
        with card("Batch Progress"):
            for name, pct in [("Batch 1 (1–1,000)", 100), ("Batch 2 (1,001–2,000)", 76), ("Batch 3 (2,001–3,000)", 0)]:
                progress_bar(pct, label=f"{name} — {pct}%")
        placeholder_notice("Live batch processing + error trend charts")
