import re
"""
Frontend integration tests.

These assert the contract the static Recruitment 360 UI under `web/` already
depends on. The field list is not invented: it was read out of
`web/leaderboard.html`, `web/campaigns.html` and `web/new-campaign.html`, so
each assertion here corresponds to a line of JavaScript that would otherwise
render blank or throw.

The point of these is regression protection in one specific direction: the
frontend is copied in byte-identical and must keep working while the Phase D
backend underneath it continues to change.
"""
import io
from unittest.mock import patch

import pytest

from tests.test_processing import FAKE_JD_EXTRACTION, PDF_MIME, make_pdf, upload
from tests.test_evaluations import STRONG_CV, WEAK_CV, make_cv_pdf


@pytest.fixture()
def screened_campaign(client):
    """A campaign with an approved rubric, two CVs uploaded, and a run scored."""
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Control Room Operator intake",
            "job_title": "Control Room Operator",
            "job_description": "Python and AWS backend engineer.",
            "location": "Coastal Terminal",
            "vacancies": 8,
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})

    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})

    upload(client, campaign_id, [
        ("haitham.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("rahul.pdf", make_cv_pdf(WEAK_CV), PDF_MIME),
    ])
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()
    return campaign_id, run["id"]


# ---------------------------------------------------------------------------
# POST /api/documents/extract-text  — new-campaign.html JD dropzone
# ---------------------------------------------------------------------------

def test_extract_text_returns_text_and_filename(client):
    """The dropzone reads body.text and body.filename."""
    response = client.post(
        "/api/documents/extract-text",
        files={"file": ("JD_Process_Engineer.pdf", io.BytesIO(make_pdf()), PDF_MIME)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "JD_Process_Engineer.pdf"
    assert body["text"].strip()
    assert body["char_count"] == len(body["text"])


def test_extract_text_uses_the_error_envelope(client):
    """
    The dropzone reads body.error.message. FastAPI's default {"detail": ...}
    would render as "The job description could not be read." with no reason.
    """
    response = client.post(
        "/api/documents/extract-text",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_FORMAT"
    assert error["message"]
    assert error["request_id"]


def test_extract_text_error_message_is_plain_english(client):
    """
    web/DATA.md's language rules: no error codes or jargon in anything a
    recruiter reads.
    """
    scanned = make_pdf(blank=True)
    response = client.post(
        "/api/documents/extract-text",
        files={"file": ("scan.pdf", io.BytesIO(scanned), PDF_MIME)},
    )
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "photograph" in message.lower()
    for jargon in ("OCR", "traceback", "Exception", "None"):
        assert jargon not in message


def test_extract_text_never_leaks_exception_text(client):
    response = client.post(
        "/api/documents/extract-text",
        files={"file": ("broken.pdf", io.BytesIO(b"not a pdf at all"), PDF_MIME)},
    )
    assert response.status_code == 422
    assert "Traceback" not in response.text
    assert "DocumentRejected" not in response.text


# ---------------------------------------------------------------------------
# GET /api/runs  — campaigns.html board
# ---------------------------------------------------------------------------

def test_list_runs_returns_a_runs_array(screened_campaign, client):
    body = client.get("/api/runs").json()
    assert isinstance(body["runs"], list)
    assert body["runs"], "the board reads runs[0]"


def test_run_carries_every_field_the_board_reads(screened_campaign, client):
    """run.run_id, .count, .submitted_count, .campaign, .results,
    .held_files, .submitted_files — all read by campaigns.html."""
    run = client.get("/api/runs").json()["runs"][0]
    for field in (
        "run_id", "count", "submitted_count", "campaign", "results",
        "held_files", "submitted_files",
    ):
        assert field in run, field
    assert run["campaign"]["title"] == "Control Room Operator"
    assert run["campaign"]["site"] == "Coastal Terminal"
    assert run["campaign"]["vacancies"] == 8


def test_submitted_files_are_the_real_uploaded_filenames(screened_campaign, client):
    """The board shows exact JD/CV filenames, not counts."""
    run = client.get("/api/runs").json()["runs"][0]
    assert sorted(run["submitted_files"]) == ["haitham.pdf", "rahul.pdf"]


def test_runs_are_newest_first(screened_campaign, client):
    campaign_id, _ = screened_campaign
    client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={})
    runs = client.get("/api/runs").json()["runs"]
    assert len(runs) >= 2
    assert runs[0]["created_at"] >= runs[1]["created_at"]


def test_runs_can_be_filtered_by_campaign(screened_campaign, client):
    campaign_id, _ = screened_campaign
    runs = client.get("/api/runs", params={"campaign_id": campaign_id}).json()["runs"]
    assert runs
    assert all(r["campaign_id"] == campaign_id for r in runs)


# ---------------------------------------------------------------------------
# GET /api/runs/{run_id}  — leaderboard.html
# ---------------------------------------------------------------------------

def test_get_run_by_id(screened_campaign, client):
    _, run_id = screened_campaign
    body = client.get(f"/api/runs/{run_id}").json()
    assert body["run_id"] == run_id
    assert body["count"] == len(body["results"])


def test_missing_run_uses_the_error_envelope(client):
    response = client.get("/api/runs/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_result_rows_carry_every_score_field_the_leaderboard_reads(screened_campaign, client):
    _, run_id = screened_campaign
    results = client.get(f"/api/runs/{run_id}").json()["results"]
    assert results
    for result in results:
        score = result["score"]
        for field in (
            "candidate_name", "weighted_total", "hiring_match_pct",
            "recommendation_code", "matched_skills", "missing_skills",
            "shortlist_reasoning",
        ):
            assert field in score, field
        assert result["profile"]["name"] == score["candidate_name"]


def test_recommendation_codes_are_the_four_the_ui_switches_on(screened_campaign, client):
    """
    verdictFor() in leaderboard.html maps exactly these four; anything else
    silently falls through to "Review required".
    """
    _, run_id = screened_campaign
    results = client.get(f"/api/runs/{run_id}").json()["results"]
    valid = {"STRONG_HIRE", "HIRE", "MAYBE", "NO_HIRE"}
    assert all(r["score"]["recommendation_code"] in valid for r in results)


def test_the_two_score_scales_agree(screened_campaign, client):
    """
    The leaderboard prefers hiring_match_pct (0-100) and falls back to
    weighted_total * 10. If the two disagree the displayed score changes
    depending on which branch runs, which is exactly the kind of silent
    10x bug this asserts against.
    """
    _, run_id = screened_campaign
    for result in client.get(f"/api/runs/{run_id}").json()["results"]:
        score = result["score"]
        assert score["hiring_match_pct"] == pytest.approx(
            score["weighted_total"] * 10, abs=0.15
        )
        assert 0 <= score["hiring_match_pct"] <= 100


def test_dimension_scores_are_on_the_uis_zero_to_ten_scale(screened_campaign, client):
    _, run_id = screened_campaign
    for result in client.get(f"/api/runs/{run_id}").json()["results"]:
        for dimension in result["score"]["dimensions"]:
            assert 0 <= dimension["score"] <= 10
            assert "criterion_key" in dimension


def test_dimensions_are_rubric_criteria_not_the_old_five(screened_campaign, client):
    """
    The whole point of Phase D reaching the UI: the leaderboard's dimension
    list is now the rubric's criteria, not skills/experience/education/
    portfolio/communication.
    """
    campaign_id, run_id = screened_campaign
    version = client.get(f"/api/campaigns/{campaign_id}/rubric/versions/1").json()
    active_keys = {w["criterion_key"] for w in version["weights"] if w["active"]}

    result = client.get(f"/api/runs/{run_id}").json()["results"][0]
    keys = {d["criterion_key"] for d in result["score"]["dimensions"]}
    assert keys == active_keys
    assert "communication_quality" not in keys


def test_phase_d_fields_ride_along_on_the_score(screened_campaign, client):
    """Confidence band, eligibility and evaluation id, for the newer screens."""
    _, run_id = screened_campaign
    score = client.get(f"/api/runs/{run_id}").json()["results"][0]["score"]
    assert score["confidence_band"] in {"HIGH", "MEDIUM", "LOW"}
    assert score["eligibility_status"] in {"ELIGIBLE", "DISQUALIFIED", "REVIEW_REQUIRED"}
    assert score["evaluation_id"]
    # And it resolves against the Phase D detail route the 360 screen needs.
    detail = client.get(f"/api/evaluations/{score['evaluation_id']}")
    assert detail.status_code == 200


def test_results_are_ranked_highest_first(screened_campaign, client):
    _, run_id = screened_campaign
    results = client.get(f"/api/runs/{run_id}").json()["results"]
    scores = [r["score"]["hiring_match_pct"] for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Held files — the exceptions panel
# ---------------------------------------------------------------------------

def test_scanned_files_are_flagged_not_held_with_a_plain_english_reason(client):
    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Held files", "job_title": "Engineer", "job_description": "x",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "x"})

    upload(client, campaign_id, [
        ("good.pdf", make_cv_pdf(STRONG_CV), PDF_MIME),
        ("scan.pdf", make_pdf(blank=True), PDF_MIME),
    ])
    run = client.post(f"/api/campaigns/{campaign_id}/evaluations/runs", json={}).json()

    body = client.get(f"/api/runs/{run['id']}").json()
    # A scanned CV is screened along with everything else now, not held out
    # of the batch — so it is a flag, not a held file.
    assert body["held_files"] == []
    flagged = body["flagged_files"]
    assert len(flagged) == 1
    assert flagged[0]["filename"] == "scan.pdf"
    assert flagged[0]["note"] == "Photographs of a CV, with no text to read"
    assert flagged[0]["merged"] is False
    # Submitted counts the file; count does not score it (no text to score).
    assert body["submitted_count"] == 2
    assert body["count"] == 1


def test_held_reasons_never_expose_error_codes(client):
    """DATA.md: "Photographs of a CV", never "OCR failure" or "E-204"."""
    from app.api.compat import _HELD_REASON

    for code, reason in _HELD_REASON.items():
        assert code.value not in reason
        assert reason[0].isupper()
        assert "_" not in reason


# ---------------------------------------------------------------------------
# Phase A-D routes are unaffected by the envelope handler
# ---------------------------------------------------------------------------

def test_existing_routes_keep_the_default_detail_shape(client):
    """
    The envelope handler must only unwrap details that are already
    envelopes, or every Phase A-C test asserting response.json()["detail"]
    would break.
    """
    response = client.get("/api/campaigns/nope")
    assert response.status_code == 404
    assert response.json()["detail"] == "Campaign not found"


def test_contract_version_is_declared(screened_campaign, client):
    _, run_id = screened_campaign
    assert client.get(f"/api/runs/{run_id}").json()["contract_version"] == "v1"
    assert client.get("/api/runs").json()["contract_version"] == "v1"


# ---------------------------------------------------------------------------
# The frontend itself
# ---------------------------------------------------------------------------

def test_frontend_is_present_and_unmodified():
    """
    All nine required screens plus Developer and Performance, and the single
    stylesheet that carries the theme.
    """
    from pathlib import Path

    web = Path(__file__).resolve().parent.parent / "web"
    assert web.is_dir()
    for page in (
        "index.html", "campaigns.html", "rubric.html", "leaderboard.html",
        "candidate.html", "compare.html", "whatif.html", "decisions.html",
        "audit.html", "developer.html", "performance.html",
    ):
        assert (web / page).is_file(), page
    assert (web / "assets" / "app.css").is_file()
    assert (web / "assets" / "app.js").is_file()


def test_theme_tokens_are_intact():
    """
    Any Phase D UI work must reuse these, not introduce new colours. This
    fails loudly if the palette is edited.
    """
    from pathlib import Path

    css = (Path(__file__).resolve().parent.parent / "web" / "assets" / "app.css").read_text(
        encoding="utf-8", errors="ignore"
    )
    for token in (
        "--maroon:#971A3E", "--sand:#F7F3ED", "--gold:#B8924E",
        "--v-strong:", "--v-potential:", "--v-review:", "--v-no:",
    ):
        assert token in css, token


# ---------------------------------------------------------------------------
# Phase I — wired screens
#
# These do not execute the JavaScript (that is verified separately in a DOM
# harness). They assert the contract between the page and the API: that the
# hooks the script needs exist, that it calls endpoints that are actually
# served, and above all that wiring a screen did not disturb the theme.
# ---------------------------------------------------------------------------

def _web(name: str) -> str:
    from pathlib import Path
    return (Path(__file__).resolve().parent.parent / "web" / name).read_text(
        encoding="utf-8", errors="ignore"
    )


def test_rubric_screen_has_its_render_hooks():
    html = _web("rubric.html")
    for hook in (
        'id="r-campaign"', 'id="r-approval"', 'id="r-musthave"', 'id="r-prefs"',
        'id="r-prefs-aside"', 'id="r-stackbar"', 'id="r-legend"', 'id="r-history"',
    ):
        assert hook in html, hook


def test_rubric_screen_calls_endpoints_that_exist(client):
    """
    The wiring reads weights and rules from /rubric/active, not from the
    versions list — the list is a summary and carries neither. Reading them
    off the list renders a silently empty rubric, which is the bug this
    guards against.
    """
    html = _web("rubric.html")
    assert "/rubric/versions" in html
    assert "/rubric/active" in html

    paths = client.app.openapi()["paths"]
    for path in (
        "/api/campaigns/{campaign_id}/rubric/versions",
        "/api/campaigns/{campaign_id}/rubric/active",
        "/api/campaigns/{campaign_id}",
        "/api/runs",
    ):
        assert path in paths, path


def test_rubric_active_endpoint_carries_weights_and_rules(client):
    """The shape the wiring depends on. If this changes, the screen blanks."""
    from unittest.mock import patch

    with patch("app.services.requirement_service.parse_jd", return_value=FAKE_JD_EXTRACTION):
        campaign_id = client.post("/api/campaigns", json={
            "name": "Rubric shape", "job_title": "Engineer", "job_description": "x",
        }).json()["id"]
        client.post(f"/api/campaigns/{campaign_id}/requirements/extract", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions",
                json={"seed_from_requirements": True})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/submit", json={})
    client.post(f"/api/campaigns/{campaign_id}/rubric/versions/1/approve",
                json={"approved_by": "Fatima Al-Rashid"})

    active = client.get(f"/api/campaigns/{campaign_id}/rubric/active").json()
    for field in ("weights", "disqualification_rules", "version_number",
                  "weight_total", "status", "approved_by", "approved_at"):
        assert field in active, field
    assert active["weights"]

    # And the list genuinely does not carry them — which is why the page
    # needs the second call.
    listed = client.get(f"/api/campaigns/{campaign_id}/rubric/versions").json()
    assert "weights" not in listed[0]


def test_wiring_did_not_change_the_rubric_stylesheet_block():
    """
    The theme lives in each page's <style> block and in app.css. Wiring adds
    id attributes and a script; it must not touch either.
    """
    html = _web("rubric.html")
    # The five stackbar classes are the house palette the script cycles
    # through. New colours would mean new classes here.
    for token in (".sb-mand{background:var(--maroon)}",
                  ".sb-skill{background:var(--maroon-mid)}",
                  ".sb-exp{background:var(--gold)}",
                  ".sb-qual{background:var(--teal)}",
                  ".sb-cert{background:var(--navy)}"):
        assert token in html, token
    # No hex colour may be introduced outside the theme-color meta tag.
    import re
    body = html.split("</head>", 1)[1]
    hexes = set(re.findall(r"#[0-9a-fA-F]{3,6}\b", body))
    assert not hexes, f"hard-coded colours introduced: {hexes}"


def test_wired_screens_use_plain_english_not_enum_values():
    """
    web/DATA.md's language rules. The script maps rule types and categories
    to words; the raw enum names appear only as lookup keys, never as output
    text, so no template literal may interpolate them directly.
    """
    html = _web("rubric.html")
    for phrase in (
        "Minimum length of experience", "Required skill",
        "Required qualification", "Required certification",
    ):
        assert phrase in html, phrase
    for banned in ("demo", "sample data", "placeholder", "Lorem", "mock"):
        assert banned.lower() not in html.lower(), banned


def test_wired_screen_keeps_the_shared_script():
    """app.js drives navigation, folds and the cascade on every page."""
    html = _web("rubric.html")
    # The src carries a cache-busting version (X50): pages used to load
    # app.js unversioned and browsers served it stale, hiding fixes.
    assert re.search(r'<script src="assets/app\.js(\?v=\d+)?"></script>', html)
    # And the page script runs before it, so folds it creates are picked up.
    assert html.index("resolveCampaign") < html.index('src="assets/app.js')
