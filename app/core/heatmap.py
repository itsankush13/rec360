import plotly.graph_objects as go
import numpy as np
from typing import List

DIMENSIONS = [
    "Skills Match",
    "Experience Relevance", 
    "Education & Certs",
    "Project Portfolio",
    "Communication Quality",
]

COLORSCALE = [
    [0.0,  "#1a1a4e"],
    [0.2,  "#2563eb"],
    [0.4,  "#60a5fa"],
    [0.5,  "#f1f5f9"],
    [0.65, "#fbbf24"],
    [0.8,  "#ef4444"],
    [1.0,  "#7f1d1d"],
]


def build_heatmap(results: List[dict]) -> go.Figure:
    candidate_names = []
    score_matrix    = []

    for r in results:
        s = r["score"]
        # Short name to avoid overlap
        name = s.candidate_name.split()[0] if s.candidate_name else "?"
        candidate_names.append(f"{name} ({s.weighted_total}/10)")
        row = []
        for dim_name in DIMENSIONS:
            matched = next(
                (d.score for d in s.dimensions
                 if d.name.lower().replace(" & "," ").replace(" ","") ==
                    dim_name.lower().replace(" & "," ").replace(" ","")),
                0.0
            )
            row.append(matched)
        score_matrix.append(row)

    candidate_names = candidate_names[::-1]
    score_matrix    = score_matrix[::-1]
    z = np.array(score_matrix)

    hover_text = []
    for r_idx, r in enumerate(results[::-1]):
        s = r["score"]
        row_hover = []
        for d_idx, dim_name in enumerate(DIMENSIONS):
            sv = z[r_idx][d_idx]
            level = ("🔴 Excellent" if sv >= 8 else
                     "🟠 Good"      if sv >= 6 else
                     "🟡 Average"   if sv >= 4 else
                     "🔵 Below Avg" if sv >= 2 else "⚫ Poor")
            row_hover.append(
                f"<b>{s.candidate_name}</b><br>"
                f"{dim_name}<br>"
                f"Score: {sv}/10  |  {level}"
            )
        hover_text.append(row_hover)

    # Dynamic height so rows never squash
    n_candidates = len(candidate_names)
    row_height   = 55   # px per candidate row
    fig_height   = max(320, 100 + n_candidates * row_height)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=DIMENSIONS,
        y=candidate_names,
        colorscale=COLORSCALE,
        zmin=0, zmax=10,
        # Only show score numbers — no text overlap because cells are big enough
        text=[[f"{v:.0f}" for v in row] for row in score_matrix],
        texttemplate="%{text}",
        textfont=dict(
            size=14,          # bigger = readable
            color="white",
            family="monospace"
        ),
        hovertext=hover_text,
        hoverinfo="text",
        xgap=3,   # gap between cells avoids blur
        ygap=3,
        colorbar=dict(
            title=dict(text="Score", font=dict(color="white", size=10)),
            tickfont=dict(color="white", size=9),
            tickvals=[0, 2, 4, 6, 8, 10],
            ticktext=["0", "2", "4", "6", "8", "10"],
            thickness=12,
            len=0.85,
        ),
    ))

    # Short x-axis labels to prevent collision
    short_labels = ["Skills", "Experience", "Education", "Projects", "Communication"]

    fig.update_layout(
        title=dict(
            text="<b>Competency Heatmap</b>  —  Red = Strong  ·  Blue = Weak",
            font=dict(size=15, color="white", family="monospace"),
            x=0.5,
        ),
        paper_bgcolor="#07090f",
        plot_bgcolor="#07090f",
        font=dict(color="white", family="monospace"),
        xaxis=dict(
            ticktext=short_labels,
            tickvals=DIMENSIONS,
            tickfont=dict(size=11, color="#a0aec0"),
            side="top",
            tickangle=0,        # horizontal labels — no overlap
        ),
        yaxis=dict(
            tickfont=dict(size=10, color="#a0aec0"),
            automargin=True,    # auto-expands margin so y labels never clip
        ),
        margin=dict(l=20, r=20, t=80, b=20),
        height=fig_height,
    )

    return fig