"""B12: the offer-letter template is deterministic — same inputs, same
letter, every time. No LLM involved (see the module docstring for why)."""
from app.core.offer_letter import render_offer_letter


def _letter(**overrides):
    payload = dict(
        candidate_name="Haitham Al-Otaibi", role="Control Room Operator",
        company="Acme Energy", base_salary=12000, currency="QAR",
        allowances={"housing": 1500, "transport": 500}, total_package=14000,
        grade="G7", start_date="2026-10-15", expiry_date="2026-09-25",
        notes="Strong console hours.", hr_name="Fatima Al-Rashid",
    )
    payload.update(overrides)
    return render_offer_letter(**payload)


def test_letter_names_the_candidate_role_and_company():
    letter = _letter()
    assert "Haitham Al-Otaibi" in letter
    assert "Control Room Operator" in letter
    assert "Acme Energy" in letter


def test_letter_states_the_full_compensation_breakdown():
    letter = _letter()
    assert "QAR 12,000.00" in letter
    assert "Housing: QAR 1,500.00" in letter
    assert "Transport: QAR 500.00" in letter
    assert "QAR 14,000.00" in letter


def test_letter_states_dates_and_declaration():
    letter = _letter()
    assert "2026-10-15" in letter
    assert "2026-09-25" in letter
    assert "Declaration" in letter
    assert "Acme Energy" in letter.split("Declaration")[1]


def test_letter_omits_grade_line_when_no_grade_given():
    with_grade = _letter(grade="G7")
    without_grade = _letter(grade="")
    assert "Grade: G7" in with_grade
    assert "Grade:" not in without_grade


def test_letter_is_identical_for_identical_input():
    assert _letter() == _letter()


def test_letter_reflects_a_changed_salary():
    cheaper = _letter(base_salary=9000, total_package=11000)
    assert "QAR 9,000.00" in cheaper
    assert "QAR 12,000.00" not in cheaper
