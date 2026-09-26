from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable, PageBreak)
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from datetime import datetime
 
# ── Color palette ──────────────────────────────────────────────────────────────
DARK       = colors.HexColor("#07090f")
NAVY       = colors.HexColor("#1a1a2e")
TEAL       = colors.HexColor("#4ECDC4")
RED        = colors.HexColor("#e53e3e")
ORANGE     = colors.HexColor("#f39c12")
LIGHT_GREY = colors.HexColor("#f7f9fc")
MID_GREY   = colors.HexColor("#cccccc")
DARK_GREY  = colors.HexColor("#555555")
 
REC_COLOR = {
    "STRONG HIRE": colors.HexColor("#1a6b3c"),   # dark green bg
    "HIRE":        colors.HexColor("#1a4a6b"),   # dark blue bg
    "MAYBE":       colors.HexColor("#6b5a1a"),   # dark amber bg
    "NO HIRE":     colors.HexColor("#6b1a1a"),   # dark red bg
}
REC_TEXT_COLOR = {
    "STRONG HIRE": colors.HexColor("#00cc66"),
    "HIRE":        colors.HexColor("#4ECDC4"),
    "MAYBE":       colors.HexColor("#f97316"),   # orange — readable on dark/light
    "NO HIRE":     RED,
}
 
VERDICT_LABEL = {
    "STRONG HIRE": "SUITABLE FOR HIRING",
    "HIRE":        "SUITABLE FOR HIRING",
    "MAYBE":       "UNDER CONSIDERATION",
    "NO HIRE":     "NOT SUITABLE FOR HIRING",
}
 
 
def _styles():
    base = getSampleStyleSheet()
    wrap = dict(wordWrap='CJK')   # forces word wrap inside table cells
 
    return {
        "title":   ParagraphStyle("ReportTitle", parent=base["Title"],
                                   fontSize=20, textColor=NAVY,
                                   spaceAfter=4, fontName="Helvetica-Bold"),
        "h2":      ParagraphStyle("H2", parent=base["Heading2"],
                                   fontSize=12, textColor=NAVY,
                                   spaceBefore=12, spaceAfter=3,
                                   fontName="Helvetica-Bold"),
        "h3":      ParagraphStyle("H3", parent=base["Heading3"],
                                   fontSize=10, textColor=NAVY,
                                   spaceBefore=6, spaceAfter=2,
                                   fontName="Helvetica-Bold"),
        "body":    ParagraphStyle("Body", parent=base["Normal"],
                                   fontSize=8, leading=12),
        "small":   ParagraphStyle("Small", parent=base["Normal"],
                                   fontSize=7, leading=10,
                                   textColor=DARK_GREY),
        "cell":    ParagraphStyle("Cell", parent=base["Normal"],
                                   fontSize=7.5, leading=11,
                                   wordWrap='CJK'),       # ← wraps in cells
        "cell_b":  ParagraphStyle("CellB", parent=base["Normal"],
                                   fontSize=7.5, leading=11,
                                   fontName="Helvetica-Bold",
                                   wordWrap='CJK'),
    }
 
 
def _verdict_badge(rec: str, S: dict) -> Table:
    """Colored badge showing SUITABLE FOR HIRING / NOT SUITABLE FOR HIRING."""
    label  = VERDICT_LABEL.get(rec, rec)
    bg     = REC_COLOR.get(rec, colors.grey)
    fg     = REC_TEXT_COLOR.get(rec, colors.white)
 
    t = Table([[Paragraph(label, ParagraphStyle(
                    "Badge", fontSize=10, textColor=fg,
                    fontName="Helvetica-Bold", alignment=TA_CENTER))]],
              colWidths=[17*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), bg),
        ("ALIGN",      (0,0), (-1,-1), "CENTER"),
        ("PADDING",    (0,0), (-1,-1), 8),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return t
 
 
def generate_pdf_report(results: list, jd_structured: dict, output_path: str) -> str:
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.8*cm, bottomMargin=1.8*cm
    )
    S        = _styles()
    elements = []
    PAGE_W   = 17*cm   # usable width
 
    # ── Cover header ──────────────────────────────────────────
    elements.append(Paragraph("Talent Intelligence System", S["title"]))
    elements.append(Paragraph(
        f"AI-Powered Shortlist Report  ·  {datetime.now().strftime('%d %b %Y, %H:%M')}",
        S["body"]))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=2, color=TEAL))
    elements.append(Spacer(1, 0.4*cm))
 
    # ── JD summary ────────────────────────────────────────────
    elements.append(Paragraph("Primary Job Description", S["h2"]))
    req_skills = ", ".join(jd_structured.get("required_skills", [])[:10])
    jd_rows = [
        [Paragraph("Role",             S["cell_b"]), Paragraph(jd_structured.get("role_title","N/A"),            S["cell"])],
        [Paragraph("Seniority",        S["cell_b"]), Paragraph(jd_structured.get("seniority_level","N/A"),       S["cell"])],
        [Paragraph("Min Experience",   S["cell_b"]), Paragraph(str(jd_structured.get("min_experience_years","?"))+" yrs", S["cell"])],
        [Paragraph("Required Skills",  S["cell_b"]), Paragraph(req_skills or "N/A",                              S["cell"])],
    ]
    jd_table = Table(jd_rows, colWidths=[3.5*cm, 13.5*cm])
    jd_table.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (0,-1), colors.HexColor("#eef2ff")),
        ("FONTNAME",    (0,0), (0,-1), "Helvetica-Bold"),
        ("GRID",        (0,0), (-1,-1), 0.4, MID_GREY),
        ("PADDING",     (0,0), (-1,-1), 6),
        ("VALIGN",      (0,0), (-1,-1), "TOP"),
    ]))
    elements.append(jd_table)
    elements.append(Spacer(1, 0.5*cm))
 
    # ── Summary stats ─────────────────────────────────────────
    elements.append(Paragraph("Screening Summary", S["h2"]))
    total   = len(results)
    strong  = sum(1 for r in results if r["score"].hire_recommendation == "STRONG HIRE")
    hire    = sum(1 for r in results if r["score"].hire_recommendation == "HIRE")
    maybe   = sum(1 for r in results if r["score"].hire_recommendation == "MAYBE")
    no_hire = sum(1 for r in results if r["score"].hire_recommendation == "NO HIRE")
    avg_sc  = sum(r["score"].weighted_total for r in results) / max(total, 1)
 
    stat_rows = [
        [Paragraph(h, ParagraphStyle("sh", fontSize=8, fontName="Helvetica-Bold",
                                      textColor=colors.white, alignment=TA_CENTER))
         for h in ["Total", "Strong Hire", "Hire", "Maybe", "No Hire", "Avg Score"]],
        [Paragraph(v, ParagraphStyle("sv", fontSize=9, fontName="Helvetica-Bold",
                                      alignment=TA_CENTER))
         for v in [str(total), str(strong), str(hire), str(maybe), str(no_hire), f"{avg_sc:.1f}/10"]],
    ]
    cw = [PAGE_W/6]*6
    stat_t = Table(stat_rows, colWidths=cw)
    stat_t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0), NAVY),
        ("GRID",        (0,0), (-1,-1), 0.4, MID_GREY),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT_GREY]),
        ("PADDING",     (0,0), (-1,-1), 7),
        ("ALIGN",       (0,0), (-1,-1), "CENTER"),
    ]))
    elements.append(stat_t)
    elements.append(Spacer(1, 0.5*cm))
 
    # ── Master ranking table ──────────────────────────────────
    elements.append(Paragraph("Candidate Rankings", S["h2"]))
 
    primary_role = jd_structured.get("role_title", "Primary Role")
 
    hdr_style = ParagraphStyle("Hdr", fontSize=7.5, fontName="Helvetica-Bold",
                                textColor=colors.white, alignment=TA_CENTER)
    rank_rows = [[
        Paragraph("#",          hdr_style),
        Paragraph("Candidate",  hdr_style),
        Paragraph("Score",      hdr_style),
        Paragraph("Conf.",      hdr_style),
        Paragraph("Verdict",    hdr_style),
        Paragraph("Best-Fit Role", hdr_style),
        Paragraph("Hiring Match",  hdr_style),
    ]]
 
    for i, r in enumerate(results, 1):
        s        = r["score"]
        best     = r["jd_matches"][0]["role_name"] if r.get("jd_matches") else "—"
        verdict  = VERDICT_LABEL.get(s.hire_recommendation, s.hire_recommendation)
        vc       = REC_TEXT_COLOR.get(s.hire_recommendation, colors.black)
 
        match_pct = getattr(s, 'hiring_match_pct', 0)
        match_color = (colors.HexColor("#16a34a") if match_pct >= 70
                       else colors.HexColor("#c2410c") if match_pct >= 50
                       else colors.HexColor("#dc2626"))
        rank_rows.append([
            Paragraph(str(i),                  S["cell"]),
            Paragraph(s.candidate_name,        S["cell"]),
            Paragraph(f"{s.weighted_total}/10",S["cell"]),
            Paragraph(f"{int(s.confidence*100)}%", S["cell"]),
            Paragraph(verdict, ParagraphStyle("vc", fontSize=7, fontName="Helvetica-Bold",
                                               textColor=vc, wordWrap='CJK')),
            Paragraph(best,                    S["cell"]),
            Paragraph(f"{match_pct}%", ParagraphStyle("hm", fontSize=8,
                       fontName="Helvetica-Bold", textColor=match_color,
                       wordWrap='CJK')),
        ])
 
    rank_t = Table(rank_rows, colWidths=[0.8*cm, 3.2*cm, 1.6*cm, 1.3*cm, 3.8*cm, 3.5*cm, 2.8*cm])
    rts = TableStyle([
        ("BACKGROUND",     (0,0), (-1,0), NAVY),
        ("GRID",           (0,0), (-1,-1), 0.3, MID_GREY),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
        ("PADDING",        (0,0), (-1,-1), 5),
        ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ("ALIGN",          (2,0), (4,0),   "CENTER"),
    ])
    rank_t.setStyle(rts)
    elements.append(rank_t)
    elements.append(Spacer(1, 0.8*cm))
 
    # ── Per-candidate detail ──────────────────────────────────
    elements.append(Paragraph("Detailed Candidate Analysis", S["h2"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=MID_GREY))
 
    for rank, r in enumerate(results, 1):
        s         = r["score"]
        jd_matches= r.get("jd_matches", [])
        audit     = r.get("bias_audit", {})
        rec       = s.hire_recommendation
        verdict   = VERDICT_LABEL.get(rec, rec)
 
        elements.append(Spacer(1, 0.4*cm))
 
        # Candidate name header
        name_color = {
            "STRONG HIRE": colors.HexColor("#16a34a"),
            "HIRE":        colors.HexColor("#0891b2"),
            "MAYBE":       colors.HexColor("#c2410c"),
            "NO HIRE":     colors.HexColor("#dc2626"),
        }.get(rec, NAVY)

        elements.append(Paragraph(
            f"#{rank}  {s.candidate_name}",
            ParagraphStyle("CH", parent=S["h2"], fontSize=12,
                           textColor=name_color,
                           spaceBefore=4)))
 
        # Verdict badge
        elements.append(Spacer(1, 0.15*cm))
        elements.append(_verdict_badge(rec, S))
        elements.append(Spacer(1, 0.15*cm))
 
        # Meta line
        match_pct = getattr(s, 'hiring_match_pct', 0)
        match_color = (colors.HexColor("#22c55e") if match_pct >= 70
                       else colors.HexColor("#f59e0b") if match_pct >= 50
                       else RED)

        elements.append(Paragraph(
            f"Score: {s.weighted_total}/10  |  "
            f"Confidence: {int(s.confidence*100)}%  |  "
            f"Source: {s.file_name}",
            S["small"]))

        # Hiring match badge
        elements.append(Spacer(1, 0.15*cm))
        match_row = [[
            Paragraph("Hiring Match %", ParagraphStyle("hml", fontSize=8,
                       fontName="Helvetica-Bold", textColor=colors.HexColor("#94a3b8"))),
            Paragraph(f"{match_pct}%", ParagraphStyle("hmv", fontSize=16,
                       fontName="Helvetica-Bold", textColor=match_color)),
            Paragraph("Semantic alignment + skill coverage + overall score",
                       ParagraphStyle("hms", fontSize=7.5, textColor=colors.HexColor("#64748b"))),
        ]]
        match_table = Table(match_row, colWidths=[3.5*cm, 3*cm, 10.5*cm])
        match_table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#0b0f1a")),
            ("PADDING",    (0,0), (-1,-1), 8),
            ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
            ("ROUNDEDCORNERS", [4]),
        ]))
        elements.append(match_table)
        elements.append(Spacer(1, 0.2*cm))
        elements.append(Spacer(1, 0.2*cm))
 
        # Dimension scores — justification wraps inside cell
        elements.append(Paragraph("Scoring Breakdown", S["h3"]))
        dim_hdr = [
            Paragraph(h, ParagraphStyle("dh", fontSize=7.5, fontName="Helvetica-Bold",
                                         textColor=colors.white))
            for h in ["Dimension", "Score", "Weight", "Justification"]
        ]
        dim_rows = [dim_hdr]
        for dim in s.dimensions:
            dim_rows.append([
                Paragraph(dim.name,                     S["cell"]),
                Paragraph(f"{dim.score}/10",            S["cell"]),
                Paragraph(f"{int(dim.weight*100)}%",    S["cell"]),
                Paragraph(dim.justification or "—",     S["cell"]),  # wraps!
            ])
        dim_t = Table(dim_rows, colWidths=[3.5*cm, 1.6*cm, 1.5*cm, 10.4*cm])
        dim_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0), (-1,0), colors.HexColor("#2c3e50")),
            ("FONTNAME",       (0,0), (-1,0), "Helvetica-Bold"),
            ("GRID",           (0,0), (-1,-1), 0.3, MID_GREY),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
            ("PADDING",        (0,0), (-1,-1), 5),
            ("VALIGN",         (0,0), (-1,-1), "TOP"),
        ]))
        elements.append(dim_t)
        elements.append(Spacer(1, 0.2*cm))
 
        # Skills — wrap long lists
        matched_str = ", ".join(s.matched_skills) if s.matched_skills else "None detected"
        missing_str = ", ".join(s.missing_skills) if s.missing_skills else "None — full match"
        elements.append(Paragraph(f"<b>Matched Skills:</b> {matched_str}", S["body"]))
        elements.append(Paragraph(f"<b>Missing Skills:</b> {missing_str}", S["body"]))
        elements.append(Spacer(1, 0.1*cm))
        elements.append(Paragraph(
            f"<b>REASON :</b> {s.shortlist_reasoning or '—'}", S["body"]))
        elements.append(Spacer(1, 0.25*cm))
 
        # Role fit analysis
        elements.append(Paragraph("Role Fit Analysis — All Open Positions", S["h3"]))
 
        if jd_matches:
            best_role    = jd_matches[0]["role_name"]
            not_primary  = (best_role != primary_role)
 
            if not_primary:
                elements.append(Paragraph(
                    f"Warning: {s.candidate_name} shows LOW fit for the primary role "
                    f"({primary_role}) but is a better match for: {best_role}",
                    ParagraphStyle("Warn", parent=S["body"],
                                   textColor=ORANGE, fontName="Helvetica-Bold")))
            else:
                elements.append(Paragraph(
                    f"Best fit for the primary role: {primary_role}",
                    ParagraphStyle("Ok", parent=S["body"],
                                   textColor=colors.HexColor("#1a6b3c"),
                                   fontName="Helvetica-Bold")))
 
            elements.append(Spacer(1, 0.12*cm))
 
            jd_hdr = [Paragraph(h, ParagraphStyle("jh", fontSize=7.5,
                                                    fontName="Helvetica-Bold",
                                                    textColor=colors.white))
                      for h in ["Rank", "Role", "Similarity", "Fit Level"]]
            jd_data = [jd_hdr]
            for idx, m in enumerate(jd_matches):
                sim = m["similarity"]
                fit = ("Excellent" if sim > 0.75 else
                       "Good"      if sim > 0.55 else
                       "Partial"   if sim > 0.35 else "Poor")
                jd_data.append([
                    Paragraph(f"#{idx+1}",      S["cell"]),
                    Paragraph(m["role_name"],   S["cell"]),
                    Paragraph(f"{sim:.4f}",     S["cell"]),
                    Paragraph(fit,              S["cell"]),
                ])
            jd_t = Table(jd_data, colWidths=[1.5*cm, 7*cm, 3.5*cm, 5*cm])
            jmts = TableStyle([
                ("BACKGROUND",     (0,0), (-1,0), NAVY),
                ("GRID",           (0,0), (-1,-1), 0.3, MID_GREY),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT_GREY]),
                ("PADDING",        (0,0), (-1,-1), 5),
                ("VALIGN",         (0,0), (-1,-1), "TOP"),
            ])
            # Highlight best-fit row green
            jmts.add("BACKGROUND", (0,1), (-1,1), colors.HexColor("#e8f8f5"))
            jmts.add("FONTNAME",   (0,1), (-1,1), "Helvetica-Bold")
            jd_t.setStyle(jmts)
            elements.append(jd_t)
 
            elements.append(Spacer(1, 0.12*cm))
            if not_primary:
                elements.append(Paragraph(
                    f"HR Recommendation: Consider {s.candidate_name} for "
                    f"{best_role} instead of the primary role.",
                    S["body"]))
 
        # Bias
        elements.append(Spacer(1, 0.15*cm))
        bias_risk  = audit.get("bias_risk_level","N/A")
        bias_found = audit.get("bias_detected", False)
        elements.append(Paragraph(
            f"<b>Bias Audit:</b> Risk: {bias_risk}  |  "
            f"Detected: {'Yes — ' + ', '.join(audit.get('bias_types',[])) if bias_found else 'No'}",
            S["body"]))
 
        elements.append(Spacer(1, 0.3*cm))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
 
    doc.build(elements)
    return output_path