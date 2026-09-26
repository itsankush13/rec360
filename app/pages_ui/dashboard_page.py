"""
dashboard_page.py — Screen 1: HR KPI Dashboard

TODO integration: replace MOCK_KPIS and the chart data with real aggregates
from app/core/pipeline.py once campaign/candidate persistence exists.
Currently your pipeline computes per-run scores but doesn't persist
campaign-level history, so these numbers are illustrative.
"""

import streamlit as st
import pandas as pd
from app.components import section_header, kpi_row, card, status_badge

MOCK_KPIS = [
    {"label": "Total Applications", "value": "1,248", "delta": "+12%", "up": True},
    {"label": "Avg. Time to Hire", "value": "6.2 days", "delta": "+18%", "up": True},
    {"label": "Screening Efficiency", "value": "92%", "delta": "+4%", "up": True},
    {"label": "Hires", "value": "48", "delta": "+20%", "up": True},
]

MOCK_THROUGHPUT = pd.DataFrame(
    {"Week": ["Apr 1", "Apr 7", "Apr 14", "Apr 21", "Apr 28"], "Applications": [18, 26, 22, 30, 27]}
)

MOCK_OUTCOMES = pd.DataFrame(
    {
        "Outcome": ["Shortlisted", "Rejected", "On Hold", "In Review"],
        "Share": [34, 52, 8, 6],
    }
)


def render():
    results = st.session_state.get("pipeline_results", [])
    if results:
        total = len(results)
        strong = sum(r["score"].hire_recommendation in {"STRONG HIRE", "HIRE"} for r in results)
        avg_score = sum(r["score"].weighted_total for r in results) / total
        kpis = [
            {"label": "Candidates Processed", "value": str(total), "delta": "Live run", "up": True},
            {"label": "Average Match", "value": f"{avg_score * 10:.0f}%", "delta": "Evidence based", "up": True},
            {"label": "Strong Matches", "value": str(strong), "delta": f"{strong / total:.0%} of run", "up": True},
            {"label": "Bias Audits", "value": str(total), "delta": "Completed", "up": True},
        ]
        throughput = pd.DataFrame({"Run": ["Current"], "Applications": [total]})
        outcomes = pd.DataFrame({"Outcome": ["Strong Fit", "Potential Fit", "Review Required", "Not Recommended"], "Share": [
            sum(r["score"].hire_recommendation == "STRONG HIRE" for r in results),
            sum(r["score"].hire_recommendation == "HIRE" for r in results),
            sum(r["score"].hire_recommendation == "MAYBE" for r in results),
            sum(r["score"].hire_recommendation == "NO HIRE" for r in results),
        ]})
    else:
        kpis = MOCK_KPIS
        throughput = MOCK_THROUGHPUT
        outcomes = MOCK_OUTCOMES
    section_header("HR KPI Dashboard", "Workload, throughput and screening outcomes — last 30 days")
    kpi_row(kpis)

    col1, col2 = st.columns([2, 1])
    with col1:
        with card("Workload & Throughput"):
            st.line_chart(throughput.set_index(throughput.columns[0]))
    with col2:
        with card("Application Outcomes"):
            st.bar_chart(outcomes.set_index("Outcome"))

    with card("Recent Activity"):
        activity = pd.DataFrame(
            {
                "Time": ["14:32", "11:15", "27 Apr", "26 Apr", "25 Apr"],
                "User": ["Priya Nair", "Aarav Sharma", "System", "Neha Gupta", "Rohan Das"],
                "Action": ["Rubric Approved", "Candidate Override", "Batch Completed", "Comments Added", "Shortlisted"],
                "Status": ["Confirmed match", "Review Required", "Processed", "In Progress", "Strong Fit"],
            }
        )
        for _, row in activity.iterrows():
            c1, c2, c3, c4 = st.columns([1, 2, 3, 2])
            c1.write(row["Time"])
            c2.write(row["User"])
            c3.write(row["Action"])
            c4.markdown(status_badge(row["Status"]), unsafe_allow_html=True)
