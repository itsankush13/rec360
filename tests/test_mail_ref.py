"""
B10 — the outbound/inbound subject-tagging contract.

The regex the inbound (reply-reading) half matches against is fixed:
    \\[REF-([0-9a-fA-F-]{36})(?::([0-9a-fA-F-]{36}))?\\]
so these tests check the tag this helper builds actually satisfies it, not
just that it "looks right".
"""
import re

from app.core.mail_ref import ref_tag

REF_PATTERN = re.compile(r"\[REF-([0-9a-fA-F-]{36})(?::([0-9a-fA-F-]{36}))?\]")

CAMPAIGN_ID = "11111111-2222-3333-4444-555555555555"
CANDIDATE_ID = "66666666-7777-8888-9999-000000000000"


def test_campaign_only_tag_matches_the_readers_regex():
    tag = ref_tag(CAMPAIGN_ID)
    match = REF_PATTERN.search(tag)
    assert match is not None
    assert match.group(1) == CAMPAIGN_ID
    assert match.group(2) is None


def test_campaign_and_candidate_tag_matches_the_readers_regex():
    tag = ref_tag(CAMPAIGN_ID, CANDIDATE_ID)
    match = REF_PATTERN.search(tag)
    assert match is not None
    assert match.group(1) == CAMPAIGN_ID
    assert match.group(2) == CANDIDATE_ID


def test_tag_leads_with_a_space_so_callers_can_concatenate():
    assert ref_tag(CAMPAIGN_ID).startswith(" ")
    assert ref_tag(CAMPAIGN_ID, CANDIDATE_ID).startswith(" ")


def test_a_falsy_candidate_id_is_treated_as_campaign_only():
    assert ref_tag(CAMPAIGN_ID, None) == ref_tag(CAMPAIGN_ID)
    assert ref_tag(CAMPAIGN_ID, "") == ref_tag(CAMPAIGN_ID)


def test_tag_appended_to_a_subject_stays_matchable():
    subject = "You have been shortlisted for Control Room Operator" + ref_tag(
        CAMPAIGN_ID, CANDIDATE_ID
    )
    match = REF_PATTERN.search(subject)
    assert match is not None
    assert match.group(1) == CAMPAIGN_ID
    assert match.group(2) == CANDIDATE_ID
