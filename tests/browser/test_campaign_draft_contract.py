"""Guards for defect X18: campaign setup must use one campaign, and a draft save
must report what the server actually did.

These read the shipped page source rather than driving a browser. That is a
weaker check than the browser run that verified the fix, and it is deliberate:
it needs no runner or dependency change, and it fails the moment the specific
shapes that caused X18 come back. The browser scenarios stay in the plan.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"


@pytest.fixture(scope="module")
def new_campaign() -> str:
    return (WEB / "new-campaign.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def campaigns() -> str:
    return (WEB / "campaigns.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js() -> str:
    """The next-step rule lives here, not on a page. Slice 2 of the campaign
    journey needs the same rule on new-campaign.html to know which step to
    open, and two copies of a rule are two rules."""
    return (WEB / "assets" / "app.js").read_text(encoding="utf-8")


def test_setup_creates_one_campaign(new_campaign: str) -> None:
    """X18 was two POSTs in one flow: one to read the description, one to approve."""
    creates = new_campaign.count("'POST', '/api/campaigns'")
    assert creates == 1, (
        f"{creates} campaign-create calls in new-campaign.html. Setup must create the "
        "campaign once and update it with PATCH from every later step."
    )


def test_later_steps_update_the_same_campaign(new_campaign: str) -> None:
    assert "'PATCH', '/api/campaigns/' + id" in new_campaign


def test_the_draft_id_outlives_the_page(new_campaign: str) -> None:
    """X19: a page variable alone let a reload lose the id, and a shared
    localStorage key let two tabs collide on one draft. The id now lives in
    this tab's own URL, stamped there by history.replaceState on create."""
    assert "history.replaceState" in new_campaign
    assert "searchParams.set('campaign_id'" in new_campaign


def test_no_shared_cross_tab_draft_key(new_campaign: str) -> None:
    """X19: two setup tabs must never share one draft id through localStorage."""
    assert "recruitment360.campaignDraft.v1" not in new_campaign


def test_no_localstorage_write_of_a_draft_id(new_campaign: str) -> None:
    """The only localStorage read left in the page is the unrelated api base."""
    assert "localStorage.setItem" not in new_campaign
    assert "localStorage.removeItem" not in new_campaign
    assert "localStorage.getItem('recruitment360.apiBase')" in new_campaign


def test_restore_reads_the_id_from_the_url_only(new_campaign: str) -> None:
    assert (
        "new URLSearchParams(location.search).get('campaign_id')" in new_campaign
    )


def test_saves_are_queued_not_concurrent(new_campaign: str) -> None:
    """Three handlers call the save and each disables only its own button, so two
    overlapping saves both created a campaign until the queue was added."""
    assert "var draftQueue = Promise.resolve();" in new_campaign
    assert "draftQueue.then(saveDraftNow, saveDraftNow)" in new_campaign


def test_save_as_draft_is_not_cosmetic(new_campaign: str) -> None:
    """The original handler set its own label and sent nothing."""
    cosmetic = (
        "document.getElementById('save-draft').addEventListener('click', function () {\n"
        "    this.textContent = 'Draft saved';"
    )
    assert cosmetic not in new_campaign
    assert "await saveDraft();" in new_campaign


def test_a_failed_save_does_not_claim_success(new_campaign: str) -> None:
    assert "Nothing was stored." in new_campaign


def test_setup_can_be_resumed(new_campaign: str) -> None:
    assert "campaign_id" in new_campaign
    assert "async function restoreDraft()" in new_campaign


def test_campaigns_lists_drafts_with_a_continue_link(campaigns: str) -> None:
    """The drafts band still exists and still deep-links back into setup. It is
    now filtered from the full list rather than fetched by its own query."""
    assert "new-campaign.html?campaign_id=" in campaigns
    assert "CampaignStatus.DRAFT" in campaigns or "'DRAFT'" in campaigns


def test_campaigns_asks_for_every_campaign_not_only_drafts(campaigns: str) -> None:
    """X22 remainder: the page asked for `?status=DRAFT` and `/api/runs` only, so
    a campaign that was set up and waiting for CVs fell between the two and
    appeared nowhere. `GET /api/campaigns` with no status returns every row —
    `status` is optional in app/api/campaigns.py.
    """
    assert "'/api/campaigns?status=DRAFT'" not in campaigns, (
        "campaigns.html still asks only for drafts. A campaign past setup and "
        "waiting for CVs then appears nowhere on the page."
    )
    assert "API_BASE + '/api/campaigns'" in campaigns, (
        "The page must ask for every campaign, whatever its status."
    )


def test_progress_is_read_from_the_campaign_not_the_capped_runs_list(campaigns: str) -> None:
    """The user requires an unbounded number of campaigns. `/api/runs` caps at
    100, so a campaign whose run falls off that list must not read as having no
    progress — that is X22's failure class, a real record shown as absent.

    `campaign.status` lives on the campaign row and is the progress signal. Run
    counts enrich a card only when that run is in hand.
    """
    assert "statusLabel" in campaigns, (
        "No status-to-words map. The card cannot state a campaign's progress "
        "without one, so it would fall back to the capped runs list."
    )
    assert "limit=" in campaigns, (
        "The runs query must pass an explicit limit rather than inherit the "
        "default of 20, which silently hides campaigns."
    )


def test_every_campaign_status_has_plain_words(campaigns: str) -> None:
    """Project convention: an enum value never reaches a reader. This also fails
    when a status is added to the backend and the card has no words for it —
    the card would otherwise print the enum or say nothing at all.
    """
    from app.db.models import CampaignStatus

    words = campaigns.split("var STATUS_WORDS = {", 1)[-1].split("};", 1)[0]
    for status in CampaignStatus:
        assert f"{status.value}:" in words, (
            f"{status.value} has no plain-words label in campaigns.html."
        )


def test_the_card_reads_its_label_from_the_map(campaigns: str) -> None:
    assert "statusLabel(campaign.status)" in campaigns, (
        "The card must render the mapped words, not the stored status."
    )


def test_the_next_step_is_derived_never_stored(campaigns: str, app_js: str) -> None:
    """07-CAMPAIGN-JOURNEY-UX-PROPOSAL.md, and 02-LIFECYCLE-MODEL.md before it:
    operative state is stored, and a suggested next task is presentation derived
    from it. A stored `current_step` would be a second workflow state that
    disagrees with `Campaign.status` the first time anything is edited out of
    order.
    """
    assert "function next(" in app_js, (
        "No next-step rule in assets/app.js. The card cannot say what to do next."
    )
    assert "function nextStep(" in campaigns, (
        "campaigns.html no longer reads the rule, so the card says nothing."
    )
    for source in (campaigns, app_js):
        assert not re.search(r"[.\['\"]current_step", source), (
            "A current_step field is read. The next step is derived from saved "
            "records, never stored."
        )


def test_the_next_step_rule_answers_for_every_status(app_js: str) -> None:
    """A status with no branch falls through and the card silently says nothing
    about what to do — the failure is invisible, which is why it is guarded."""
    from app.db.models import CampaignStatus

    rule = app_js.split("function next(", 1)[-1].split("\n  }", 1)[0]
    for status in CampaignStatus:
        assert status.value in rule, (
            f"nextStep() has no branch for {status.value}."
        )


def test_the_next_step_reaches_the_reader(campaigns: str) -> None:
    assert "nextStep(campaign" in campaigns, (
        "nextStep() is defined but never rendered onto a card."
    )


def test_the_sample_cards_go_when_any_real_campaign_exists(campaigns: str) -> None:
    """X23: six static sample cards sit in a `data-mock-only` band that was
    hidden only from `renderRuns`. A recruiter with real campaigns but no run
    yet — exactly the 'I will upload the CVs later' case — saw six fictional
    campaigns beside her own, and a Process Engineer card rendered twice.
    """
    assert campaigns.count("data-mock-only") >= 4, (
        "The sample bands lost their data-mock-only marker; nothing can hide them."
    )
    hide = "function hideMock()"
    assert hide in campaigns, (
        "Hiding the sample cards must not be reachable only from renderRuns. A "
        "campaign with no run must also clear them."
    )


def test_a_save_before_the_restore_lands_finds_the_id(new_campaign: str) -> None:
    """X19 follow-on. restoreDraft() is not awaited and the buttons are live at
    once. A save clicked while that GET is in the air must find the id in this
    tab's URL, or it creates a second campaign — X18 through a new door."""
    assert "draftCampaignId || urlDraftId()" in new_campaign, (
        "saveDraftNow must fall back to the campaign_id in this tab's URL. A page "
        "variable alone is empty until restoreDraft() answers."
    )


def test_a_save_cannot_run_before_the_restore_settles(new_campaign: str) -> None:
    """X20: the page ships prefilled demo values, so a save clicked on a
    `?campaign_id=` page before the restoring GET answers used to PATCH a real
    draft with 'Control Room Operator' and an empty job description. Observed
    2026-09-12 through a proxy that held that GET open for four seconds.

    Every save already goes through `draftQueue`. Seeding that queue with the
    restore makes an early click wait and then save the restored values, which
    closes the window for all three save callers at once.
    """
    assert "draftQueue = restoreDraft()" in new_campaign, (
        "The save queue must start from restoreDraft(), or a save clicked "
        "during the restore overwrites the draft with the form's defaults."
    )


def test_the_restore_promise_is_not_dropped(new_campaign: str) -> None:
    """X20: calling restoreDraft() as a bare statement throws the promise away,
    and nothing can wait for it."""
    assert not re.search(r"^\s*restoreDraft\(\);", new_campaign, re.MULTILINE), (
        "restoreDraft() is called without keeping its promise. The save queue "
        "then has nothing to wait for."
    )


def test_restore_does_not_give_up_on_a_campaign_past_setup(new_campaign: str) -> None:
    """X22: `restoreDraft()` used to return early unless the campaign was still
    a DRAFT. The form then kept its prefilled sample values, and the next save
    overwrote a real approved campaign with them. CV upload saves the role
    fields before posting the batch, so 'I will upload the CVs later' was the
    journey that destroyed the record.

    Never PATCH a record that was not read. The campaign is loaded whatever its
    status; what may then be edited is a separate question, decided per field
    in docs/DECISIONS.md.
    """
    assert "campaign.status !== 'DRAFT'" not in new_campaign, (
        "restoreDraft() still gives up on a campaign past setup. The form then "
        "keeps its sample values and the next save overwrites the campaign."
    )


def test_the_status_is_shown_when_setup_is_reopened_past_draft(new_campaign: str) -> None:
    """X22: restoring a non-draft campaign silently would hide that this role is
    already approved. The recruiter has to be told which campaign she is in."""
    assert "campaign.status" in new_campaign, (
        "The campaign's stored status is never read, so the page cannot tell "
        "the recruiter that this role is already past setup."
    )


def test_every_step_the_rule_names_has_somewhere_to_go(app_js: str) -> None:
    """Slice 2: a campaign card links to the step the rule names. A step id with
    no anchor and no URL sends the recruiter nowhere, and the failure is silent
    — the link simply reopens the top of the form.
    """
    labels = app_js.split("var LABEL = {", 1)[-1].split("};", 1)[0]
    anchors = app_js.split("var ANCHOR = {", 1)[-1].split("};", 1)[0]
    steps = re.findall(r"^\s*(\w+):", labels, re.M)
    assert steps, "The rule names no steps at all."
    routed = set(re.findall(r"^\s*(\w+):", anchors, re.M))
    # `assess` has nothing to act on and `shortlist` goes to the ranked list.
    routed |= {"assess", "shortlist"}
    for step in steps:
        assert step in routed, (
            f"Step '{step}' has no anchor and no URL. A card naming it would "
            "link nowhere."
        )
    assert "leaderboard.html?run_id=" in app_js, (
        "The shortlist step has no ranked-results URL."
    )


def test_the_landing_step_is_a_real_url(new_campaign: str) -> None:
    """AGENT-START-HERE.md section 5: preserve deep-link context and browser
    Back. The step is a hash, so both are the browser's own behaviour — but only
    if the page reacts to a hash that changes without a load.
    """
    for anchor in ('id="role"', 'id="jd"', 'id="cvs"'):
        assert anchor in new_campaign, (
            f"new-campaign.html has no {anchor} for a step link to land on."
        )
    assert "addEventListener('hashchange'" in new_campaign, (
        "Back between two steps of one campaign changes only the hash. Without "
        "a hashchange listener the URL moves and the page does not."
    )


def test_the_landing_opens_the_band_it_scrolls_to(new_campaign: str) -> None:
    """The bands are collapsed by default. Scrolling to a closed one lands the
    recruiter on a shut accordion, which reads as an empty page."""
    assert "__r360OpenBand" in new_campaign, (
        "The landing scrolls to a band without opening it."
    )


def test_finishing_setup_drops_the_step_from_the_url(new_campaign: str) -> None:
    """Setup complete means the next visit starts a new role, so neither the
    campaign id nor the step it stopped on may survive in the URL."""
    done = new_campaign.split("doneUrl.searchParams.delete('campaign_id')", 1)[-1][:200]
    assert "doneUrl.hash = ''" in done, (
        "The campaign id is dropped when setup finishes but the step is not."
    )
