"""
The offer letter — B12.

A single, deterministic template. Unlike `jd_templates.py` (B06), there is no
optional LLM layer here: this is the one document in the product with money
and a legal declaration in it, and an approved offer letter must not vary by
model sampling. Every field is drawn from the draft payload, the candidate,
the campaign and `settings.company_name` — nothing is free text a sender
supplies at send time, so there is no placeholder that can go unresolved.
"""
from __future__ import annotations


def render_offer_letter(
    *,
    candidate_name: str,
    role: str,
    company: str,
    base_salary: float,
    currency: str,
    allowances: dict[str, float],
    total_package: float,
    grade: str,
    start_date: str,
    expiry_date: str,
    notes: str,
    hr_name: str = "Human Resources",
) -> str:
    allowance_lines = "\n".join(
        f"- {name.replace('_', ' ').title()}: {currency} {amount:,.2f} per month"
        for name, amount in allowances.items()
    ) or "- None"
    grade_line = f"Grade: {grade}\n" if grade else ""
    notes_block = f"\n{notes}\n" if notes else ""

    return f"""Dear {candidate_name},

We are pleased to offer you the position of {role} at {company}, subject to the terms set out below.

Compensation:
- Base salary: {currency} {base_salary:,.2f} per month
{allowance_lines}
- Total package: {currency} {total_package:,.2f} per month
{grade_line}
Start date: {start_date}
This offer is open for acceptance until: {expiry_date}
{notes_block}
Declaration: By accepting this offer, you confirm that the information you provided during the recruitment process is accurate and complete, and you agree to {company}'s standard terms of employment, which will be provided with your onboarding documents.

Please confirm your acceptance by replying before the expiry date above. We look forward to welcoming you to the team.

Best regards,
{hr_name}
{company}"""
