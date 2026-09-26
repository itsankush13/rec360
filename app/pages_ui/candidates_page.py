"""
candidates_page.py — Screens 5-10: Bulk CV Upload, Candidate Evaluation & Ranking,
Candidate 360 Assessment Report, Candidate Comparison, What-if Analysis, Decision & Export.

TODO integration:
- "Bulk Upload" tab: wire st.file_uploader(accept_multiple_files=True) to your
  existing app/utils/document_parser.py, looping through files and calling
  app/core/pipeline.py per file. Track per-file status in st.session_state.
- "Leaderboard" tab: replace MOCK_CANDIDATES with pipeline output
  (Resume Parser -> Scoring Agent -> Bias Audit Agent results).
- "Candidate 360" tab: map to your existing report_generator.py output —
  this just needs the same fields rendered on-screen instead of only to PDF.
- "Comparison" / "What-if": net-new — no backend yet, UI only for now.
"""

import streamlit as st
import pandas as pd
import os
import tempfile
from app.components import section_header, card, status_badge, status_badge_md, progress_bar, placeholder_notice
from app.core.pipeline import run_pipeline

MOCK_CANDIDATES = pd.DataFrame(
    {
        "#": [1, 2, 3, 4, 5, 6, 7, 8],
        "Candidate": ["Rahul Sharma", "Priya Menon", "Amit Verma", "Sneha Iyer", "Karan Mehta", "Rohan Das", "Neha Gupta", "Arjun Singh"],
        "Overall Score": [92, 88, 84, 78, 74, 68, 62, 58],
        "Confidence": ["96%", "92%", "88%", "80%", "80%", "72%", "68%", "60%"],
        "Status": ["Strong Fit", "Strong Fit", "Potential Fit", "Potential Fit", "Review Required", "Review Required", "Not Recommended", "Not Recommended"],
    }
)


def _status_for_recommendation(recommendation: str) -> str:
    return {
        "STRONG HIRE": "Strong Fit",
        "HIRE": "Potential Fit",
        "MAYBE": "Review Required",
        "NO HIRE": "Not Recommended",
    }.get(recommendation, "Review Required")


def _result_rows(results: list[dict]) -> pd.DataFrame:
    rows = []
    for index, result in enumerate(results, 1):
        score = result["score"]
        rows.append({
            "#": index,
            "Candidate": score.candidate_name,
            "Overall Score": round(score.weighted_total * 10),
            "Confidence": f"{int(score.confidence * 100)}%",
            "Status": _status_for_recommendation(score.hire_recommendation),
        })
    return pd.DataFrame(rows)


def render():
    section_header("Candidates", "Screen, rank, and drill into evidence-backed assessments")

    if "pipeline_results" not in st.session_state:
        st.session_state["pipeline_results"] = []
    results = st.session_state["pipeline_results"]
    campaign = st.session_state.get("campaign", {})

    tab_upload, tab_rank, tab_360, tab_compare, tab_whatif, tab_decision = st.tabs(
        ["Bulk Upload", "Leaderboard", "Candidate 360", "Comparison", "What-if Analysis", "Decision & Export"]
    )

    # --- Bulk Upload (screen 5) ---
    with tab_upload:
        with card("Bulk CV Upload"):
            files = st.file_uploader(
                "Drag & drop files or folders here (PDF, DOCX, max 50MB each)",
                type=["pdf", "docx"],
                accept_multiple_files=True,
            )
            if files:
                st.success(f"{len(files)} file(s) received.")
                rows = []
                for f in files:
                    rows.append({"File Name": f.name, "Status": "Queued", "Size (KB)": round(f.size / 1024, 1), "Issues": "-"})
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                if st.button("Process files", type="primary", key="process_candidate_files"):
                    jd_text = campaign.get("jd_text", "").strip()
                    if not jd_text:
                        st.warning("Create a campaign and add a job description before processing candidates.")
                    else:
                        temp_paths = []
                        try:
                            for uploaded in files:
                                suffix = os.path.splitext(uploaded.name)[1].lower() or ".pdf"
                                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                                temp_file.write(uploaded.getvalue())
                                temp_file.close()
                                temp_paths.append(temp_file.name)
                            with st.spinner("Running JD, resume, scoring, and bias agents..."):
                                st.session_state["pipeline_results"] = run_pipeline(jd_text, temp_paths)
                            st.success(f"Processed {len(st.session_state['pipeline_results'])} candidate(s).")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Candidate processing failed: {exc}")
                        finally:
                            for path in temp_paths:
                                try:
                                    os.unlink(path)
                                except OSError:
                                    pass
            else:
                st.caption("No files uploaded yet.")

    # --- Leaderboard (screen 6) ---
    with tab_rank:
        candidate_df = _result_rows(results) if results else MOCK_CANDIDATES
        with card():
            c1, c2, c3 = st.columns(3)
            selected_status = c1.selectbox("Status", ["All Status", "Strong Fit", "Potential Fit", "Review Required", "Not Recommended"])
            search = c2.text_input("Search candidate, skills...")
            sort_by = c3.selectbox("Sort by", ["Score", "Confidence", "Name"])

            filtered = candidate_df.copy()
            if selected_status != "All Status":
                filtered = filtered[filtered["Status"] == selected_status]
            if search:
                filtered = filtered[filtered["Candidate"].str.contains(search, case=False, na=False)]
            sort_column = {"Score": "Overall Score", "Confidence": "Confidence", "Name": "Candidate"}[sort_by]
            filtered = filtered.sort_values(sort_column, ascending=False if sort_by != "Name" else True)
            for _, row in filtered.iterrows():
                cols = st.columns([0.5, 2.5, 1.2, 1.2, 1.5, 1])
                cols[0].write(row["#"])
                cols[1].write(f"**{row['Candidate']}**")
                cols[2].write(f"{row['Overall Score']}")
                cols[3].write(row["Confidence"])
                with cols[4]:
                    status_badge_md(row["Status"])
                cols[5].button("View", key=f"view_{row['#']}")

    # --- Candidate 360 (screen 7) ---
    with tab_360:
        selected_index = st.selectbox("Candidate", range(len(results)), format_func=lambda index: results[index]["score"].candidate_name) if results else None
        selected_result = results[selected_index] if selected_index is not None else None
        selected_score = selected_result["score"] if selected_result else None
        candidate_name = selected_score.candidate_name if selected_score else "Rahul Sharma"
        with card(f"{candidate_name} — Candidate 360"):
            c1, c2, c3 = st.columns(3)
            score_value = selected_score.weighted_total * 10 if selected_score else 92
            confidence = selected_score.confidence * 100 if selected_score else 96
            c1.metric("Overall Score", f"{score_value:.0f}%")
            c2.metric("Confidence", f"{confidence:.0f}%")
            c3.markdown(status_badge(_status_for_recommendation(selected_score.hire_recommendation) if selected_score else "Strong Fit"), unsafe_allow_html=True)

            st.markdown("##### Score Breakdown")
            if selected_score:
                for dimension in selected_score.dimensions:
                    progress_bar(dimension.score * 10, label=f"{dimension.name} — {dimension.score:.1f}/10")
            else:
                for label, pct in [("Mandatory Requirements", 95), ("Skills", 90), ("Experience", 88), ("Education", 85), ("Certifications", 80)]:
                    progress_bar(pct, label=f"{label} — {pct}%")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### Strengths")
                if selected_result:
                    st.write("- " + ", ".join(selected_score.matched_skills[:5]) if selected_score.matched_skills else "- Evidence-backed match found")
                    st.write(f"- {selected_result['profile'].experience_years:g} years of experience")
                    st.write("- " + (selected_result["profile"].certifications[0] if selected_result["profile"].certifications else "No certification listed"))
                else:
                    st.write("- 5+ years relevant experience")
                    st.write("- AWS certified")
                    st.write("- Strong project portfolio")
            with c2:
                st.markdown("##### Gaps / Risks")
                if selected_score and selected_score.missing_skills:
                    st.write("- Missing: " + ", ".join(selected_score.missing_skills[:5]))
                else:
                    st.write("- Less experience in Kubernetes")
                    st.write("- No industry-specific experience")

            st.markdown("##### Recommendation")
            if selected_score:
                st.info(selected_score.shortlist_reasoning or "Review the score dimensions before making a decision.")
                if selected_result.get("bias_audit"):
                    st.caption(f"Bias audit: {selected_result['bias_audit']}")
            else:
                st.info("**Strong Fit** — proceed to interview. Suggested focus: system design, Kubernetes depth.")

    # --- Comparison (screen 8) ---
    with tab_compare:
        candidate_names = candidate_df["Candidate"].tolist()
        with card("Compare Candidates"):
            selected_names = st.multiselect("Select candidates (max 3)", candidate_names, default=candidate_names[:3])
            if results:
                selected = [result for result in results if result["score"].candidate_name in selected_names[:3]]
                comp = pd.DataFrame({
                    "Criteria": ["Overall Score", "Experience (yrs)", "Skills Match", "Education", "Certifications"],
                    **{result["score"].candidate_name: [
                        f"{result['score'].weighted_total * 10:.0f}%",
                        result["profile"].experience_years,
                        f"{result['score'].hiring_match_pct:.0f}%",
                        result["profile"].education or "Not listed",
                        ", ".join(result["profile"].certifications) or "None",
                    ] for result in selected},
                })
            else:
                comp = pd.DataFrame({"Criteria": ["Overall Score", "Experience (yrs)", "Skills Match", "Education", "Certifications"], "Rahul Sharma": [92, 5.5, "90%", "B.Tech (CS)", "AWS"]})
            st.dataframe(comp, use_container_width=True, hide_index=True)

    # --- What-if (screen 9) ---
    with tab_whatif:
        with card("Adjust Weights (Simulation Only)"):
            st.slider("Skills & Technical Expertise", 0, 100, 30)
            st.slider("Experience & Relevance", 0, 100, 20)
            st.slider("Education & Certifications", 0, 100, 10)
            st.slider("Industry Experience", 0, 100, 10)
            st.slider("Role Seniority", 0, 100, 10)
            st.slider("Cultural Fit", 0, 100, 10)
            st.button("Apply (Simulation Only)", type="primary")
            placeholder_notice("Live re-rank preview without touching the approved rubric")

    # --- Decision & Export (screen 10) ---
    with tab_decision:
        decision_df = _result_rows(results) if results else MOCK_CANDIDATES
        with card("Shortlist & Actions"):
            b1, b2, b3, b4 = st.columns(4)
            b1.button("Shortlist", type="primary")
            b2.button("Reject")
            b3.button("Hold")
            b4.button("Export")
            st.dataframe(
                decision_df[["Candidate", "Overall Score", "Status"]],
                use_container_width=True,
                hide_index=True,
            )
            st.caption("TODO: wire Export to report_generator.py (PDF) and add ATS push once an integration exists.")
