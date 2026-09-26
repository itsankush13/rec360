import json
import re
from pathlib import Path


def parse_linkedin_json_export(file_path: str) -> dict:
    """Parse LinkedIn's official Profile.json data export."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Name
    name = (data.get("firstName", "") + " " + data.get("lastName", "")).strip()
    if not name:
        name = data.get("name", "Unknown")

    # Headline + summary
    headline = data.get("headline", "")
    summary  = data.get("summary", "")

    # Experience
    experiences = (
        data.get("positions", {}).get("values", [])
        or data.get("experience", [])
        or []
    )
    exp_texts, total_months = [], 0
    for exp in experiences:
        title   = exp.get("title", "")
        company = exp.get("company", {})
        company = company.get("name", "") if isinstance(company, dict) else company
        start   = exp.get("startDate", {}) or {}
        end     = exp.get("endDate",   {}) or {}
        sy, sm  = int(start.get("year",  2020)), int(start.get("month", 1))
        ey, em  = int(end.get("year",    2025)), int(end.get("month",   1))
        total_months += max(0, (ey - sy) * 12 + (em - sm))
        desc = exp.get("description", "")
        exp_texts.append(f"{title} at {company} ({sy}–{ey}): {desc}")

    exp_text       = "\n".join(exp_texts)
    experience_yrs = round(total_months / 12, 1)

    # Education
    educations = (
        data.get("educations", {}).get("values", [])
        or data.get("education", [])
        or []
    )
    edu_text = "; ".join(
        f"{e.get('degree','')} in {e.get('fieldOfStudy','')} — {e.get('schoolName', e.get('school',''))}"
        for e in educations
    )

    # Skills
    skills_raw = (
        data.get("skills", {}).get("values", [])
        or data.get("skills", [])
        or []
    )
    skills = [s.get("name", s) if isinstance(s, dict) else s for s in skills_raw]

    # Certifications
    certs_raw = (
        data.get("certifications", {}).get("values", [])
        or data.get("certifications", [])
        or []
    )
    certs = [c.get("name", "") for c in certs_raw if isinstance(c, dict)]

    # Projects
    projects_raw = (
        data.get("projects", {}).get("values", [])
        or data.get("projects", [])
        or []
    )
    projects = [
        f"{p.get('title','')}: {p.get('description','')}"
        for p in projects_raw if isinstance(p, dict)
    ]

    raw_text = f"""
Name: {name}
Headline: {headline}
Summary: {summary}
Experience: {exp_text}
Education: {edu_text}
Skills: {', '.join(skills)}
Certifications: {', '.join(certs)}
Projects: {'; '.join(projects)}
""".strip()

    return {
        "name": name, "headline": headline, "summary": summary,
        "experience_text": exp_text, "experience_years": experience_yrs,
        "education": edu_text, "skills": skills,
        "certifications": certs, "projects": projects,
        "raw_text": raw_text,
    }


def parse_linkedin_text_paste(text: str, override_name: str = "") -> dict:
    """
    Parse plain text copy-pasted from a LinkedIn profile page.
    Ctrl+A on profile page → Ctrl+C → paste here.
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return {}

    name     = override_name.strip() if override_name.strip() else lines[0]
    headline = lines[1] if len(lines) > 1 else ""

    SECTION_KEYWORDS = {
        "experience":     ["experience", "work experience"],
        "education":      ["education"],
        "skills":         ["skills", "top skills"],
        "certifications": ["certifications", "licenses & certifications"],
        "projects":       ["projects"],
        "summary":        ["about", "summary"],
    }

    section_text   = {k: [] for k in SECTION_KEYWORDS}
    current_section = "other"

    for line in lines[2:]:
        matched = False
        for section, keywords in SECTION_KEYWORDS.items():
            if any(line.lower() == kw or line.lower().startswith(kw) for kw in keywords):
                current_section = section
                matched = True
                break
        if not matched and current_section in section_text:
            section_text[current_section].append(line)

    exp_text = "\n".join(section_text["experience"])

    # Estimate experience years from years mentioned
    year_matches = re.findall(r"\b(19|20)\d{2}\b", exp_text)
    exp_years = 0.0
    if len(year_matches) >= 2:
        years = sorted(int(y) for y in year_matches)
        exp_years = float(years[-1] - years[0])

    raw_text = f"""
Name: {name}
Headline: {headline}
Summary: {' '.join(section_text['summary'])}
Experience: {exp_text}
Education: {' '.join(section_text['education'])}
Skills: {', '.join(section_text['skills'][:30])}
Certifications: {', '.join(section_text['certifications'])}
""".strip()

    return {
        "name": name, "headline": headline,
        "summary": " ".join(section_text["summary"]),
        "experience_text": exp_text,
        "experience_years": exp_years,
        "education": " ".join(section_text["education"]),
        "skills": section_text["skills"][:30],
        "certifications": section_text["certifications"],
        "projects": section_text["projects"],
        "raw_text": raw_text,
    }