import networkx as nx
import plotly.graph_objects as go
from typing import List
import numpy as np

# Role node colors — each JD gets a unique vivid color
ROLE_PALETTE = [
    "#FF6B6B", "#4ECDC4", "#FFE66D", "#A29BFE",
    "#FD79A8", "#00CEC9", "#FDCB6E", "#6C5CE7",
    "#55EFC4", "#E17055", "#74B9FF", "#FF7675",
]

REC_COLORS = {
    "STRONG HIRE": "#00ff88",
    "HIRE":        "#4ECDC4",
    "MAYBE":       "#FFE66D",
    "NO HIRE":     "#FF6B6B",
}


def build_multi_jd_graph(results: List[dict]) -> nx.DiGraph:
    G = nx.DiGraph()

    # Collect all unique roles
    all_roles = []
    if results:
        for jd in results[0].get("all_jds", []):
            role = jd["role_name"]
            if role not in all_roles:
                all_roles.append(role)

    role_color_map = {role: ROLE_PALETTE[i % len(ROLE_PALETTE)]
                      for i, role in enumerate(all_roles)}

    # Add role nodes
    for role in all_roles:
        G.add_node(role, type="role", color=role_color_map[role])

    # Add candidate nodes + edges
    for r in results:
        s = r["score"]
        name = s.candidate_name
        rec = s.hire_recommendation
        G.add_node(name, type="candidate",
                   score=s.weighted_total,
                   recommendation=rec,
                   color=REC_COLORS.get(rec, "#aaaaaa"),
                   confidence=s.confidence)

        # Edge to best-fit role (strongest)
        jd_matches = r.get("jd_matches", [])
        for idx, match in enumerate(jd_matches):
            role = match["role_name"]
            sim = match["similarity"]
            is_best = (idx == 0)
            G.add_edge(name, role,
                       weight=sim,
                       is_best=is_best,
                       similarity=sim)

    return G, role_color_map


def plot_multi_jd_graph(results: List[dict]) -> go.Figure:
    G, role_color_map = build_multi_jd_graph(results)

    # Layout — roles in a circle, candidates spread around them
    pos = {}
    role_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "role"]
    cand_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "candidate"]

    # Place roles in a large circle
    n_roles = len(role_nodes)
    for i, role in enumerate(role_nodes):
        angle = 2 * np.pi * i / max(n_roles, 1)
        pos[role] = (2.5 * np.cos(angle), 2.5 * np.sin(angle))

    # Place candidates — pulled toward their best-fit role
    for cand in cand_nodes:
        best_role = None
        best_sim = -1
        for _, role, data in G.out_edges(cand, data=True):
            if data.get("is_best") and data["similarity"] > best_sim:
                best_sim = data["similarity"]
                best_role = role

        if best_role and best_role in pos:
            rx, ry = pos[best_role]
            # Spread candidates around their best role with jitter
            angle = np.random.uniform(0, 2 * np.pi)
            r = np.random.uniform(0.6, 1.2)
            pos[cand] = (rx + r * np.cos(angle), ry + r * np.sin(angle))
        else:
            pos[cand] = (np.random.uniform(-1, 1), np.random.uniform(-1, 1))

    traces = []

    # ── Draw edges ────────────────────────────────────────────
    # Faint edges for non-best matches
    for u, v, data in G.edges(data=True):
        if not data.get("is_best"):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            traces.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode="lines",
                line=dict(width=0.5, color="rgba(255,255,255,0.06)"),
                hoverinfo="none", showlegend=False
            ))

    # Bold glowing edges for best-fit matches
    for u, v, data in G.edges(data=True):
        if data.get("is_best"):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            role_color = role_color_map.get(v, "#ffffff")
            sim = data["similarity"]
            traces.append(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None],
                mode="lines",
                line=dict(width=2 + sim * 4, color=role_color),
                opacity=0.7,
                hoverinfo="none", showlegend=False
            ))

    # ── Draw ROLE nodes ───────────────────────────────────────
    for role in role_nodes:
        x, y = pos[role]
        color = role_color_map.get(role, "#ffffff")
        traces.append(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(
                size=42,
                color=color,
                symbol="hexagon",
                line=dict(width=3, color="white"),
                opacity=0.95,
            ),
            text=[f"<b>{role}</b>"],
            textposition="top center",
            textfont=dict(size=11, color="white", family="monospace"),
            hovertext=f"<b>📋 {role}</b>",
            hoverinfo="text",
            showlegend=False,
        ))

    # ── Draw CANDIDATE nodes ──────────────────────────────────
    for cand in cand_nodes:
        x, y = pos[cand]
        node_data = G.nodes[cand]
        color = node_data.get("color", "#aaaaaa")
        score = node_data.get("score", 0)
        rec = node_data.get("recommendation", "")
        conf = node_data.get("confidence", 0)

        # Size by score
        size = 18 + score * 2.5

        traces.append(go.Scatter(
            x=[x], y=[y],
            mode="markers+text",
            marker=dict(
                size=size,
                color=color,
                symbol="circle",
                line=dict(width=2, color="rgba(255,255,255,0.4)"),
                opacity=0.92,
            ),
            text=[f"{cand.split()[0]}"],  # First name only to avoid clutter
            textposition="bottom center",
            textfont=dict(size=9, color="rgba(255,255,255,0.8)"),
            hovertext=(
                f"<b>👤 {cand}</b><br>"
                f"Score: {score}/10<br>"
                f"Verdict: {rec}<br>"
                f"Confidence: {int(conf*100)}%"
            ),
            hoverinfo="text",
            showlegend=False,
        ))

    # ── Legend ────────────────────────────────────────────────
    for label, color in REC_COLORS.items():
        traces.append(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=12, color=color, symbol="circle"),
            name=label,
            showlegend=True,
        ))

    fig = go.Figure(data=traces, layout=go.Layout(
        title=dict(
            text="<b>Candidate × Role Fit Intelligence Graph</b>",
            font=dict(size=18, color="white", family="monospace"),
            x=0.5,
        ),
        paper_bgcolor="#080c14",
        plot_bgcolor="#080c14",
        font=dict(color="white"),
        hovermode="closest",
        showlegend=True,
        legend=dict(
            bgcolor="rgba(255,255,255,0.05)",
            bordercolor="rgba(255,255,255,0.1)",
            borderwidth=1,
            font=dict(color="white", size=10),
            x=0.01, y=0.99,
        ),
        margin=dict(l=10, r=10, t=60, b=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   showline=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False,
                   showline=False),
        height=580,
    ))

    return fig