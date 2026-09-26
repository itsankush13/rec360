"""The label a campaign wears in a chooser.

Every campaign select used to read `job_title + ' - ' + name`. In practice the
two fields are near-duplicates - "Process Engineer - E2E Verification - Process
Engineer" - and `name` is an internal label ("rail demo", "X22 verify") that
means nothing to a recruiter. The option said the role twice and helped with
neither choosing nor telling two campaigns apart.

These run the real function in node rather than reading the source, because the
part worth guarding is the behaviour: two campaigns must never wear the same
label.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
APP_JS = WEB / "assets" / "app.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not on PATH"
)


def labels(campaigns: list[dict]) -> list[str]:
    """Run campaignOptions() from the shipped app.js against these campaigns."""
    script = f"""
      global.window = global;
      global.document = {{
        querySelector: () => null,
        querySelectorAll: () => [],
        addEventListener: () => {{}},
        readyState: 'complete',
        // X32: app.js's B22 portal gate runs `document.documentElement.
        // classList.add('auth-pending')` at import, before this test's own
        // CampaignSteps/label logic ever runs. A stub here keeps this a real
        // test of that logic without a browser, rather than crashing on an
        // unrelated line these tests were never meant to exercise.
        documentElement: {{ classList: {{ add: () => {{}}, remove: () => {{}} }} }},
      }};
      global.localStorage = {{ getItem: () => null, setItem: () => {{}} }};
      global.sessionStorage = global.localStorage;
      global.location = {{ pathname: '/test.html', protocol: 'http:', search: '', replace: () => {{}} }};
      global.navigator = {{}};
      require({str(APP_JS).replace(chr(92), '/')!r});
      console.log(JSON.stringify(
        window.campaignOptions({json.dumps(campaigns)}).map(o => o.label)
      ));
    """
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_the_option_says_the_role_and_the_site() -> None:
    label = labels([
        {"id": "a", "job_title": "Process Engineer",
         "name": "E2E Verification - Process Engineer", "location": "North Plant"},
    ])[0]
    assert label.startswith("Process Engineer")
    assert "North Plant" in label
    assert "E2E Verification" not in label


def test_the_internal_name_is_not_repeated_at_the_recruiter() -> None:
    """'rail demo' and 'X22 verify' are how a campaign was set up, not how a
    recruiter recognises the role they are hiring for."""
    for label in labels([
        {"id": "a", "job_title": "Turnaround Planner", "name": "rail demo",
         "location": "North Plant"},
        {"id": "b", "job_title": "Pipeline Integrity Engineer", "name": "X22 verify",
         "location": "Mesaieed"},
    ]):
        assert "rail demo" not in label and "X22 verify" not in label


def test_two_campaigns_are_never_offered_under_one_label() -> None:
    """The same role at the same site is a real case - two intakes, two batches.
    Identical options are worse than a long one, so those get their internal
    name back, and only those."""
    result = labels([
        {"id": "a", "job_title": "Welder", "name": "January intake",
         "location": "Coastal Terminal"},
        {"id": "b", "job_title": "Welder", "name": "March intake",
         "location": "Coastal Terminal"},
        {"id": "c", "job_title": "Electrician", "name": "spare label",
         "location": "Coastal Terminal"},
    ])
    assert len(set(result)) == 3, "Two campaigns share a label: %s" % result
    assert "January intake" in result[0] and "Welder" in result[0]
    assert "March intake" in result[1]
    # Only the clashing pair pays for the extra words.
    assert "spare label" not in result[2]
    assert result[2].startswith("Electrician")


def test_a_campaign_with_no_site_still_has_a_name() -> None:
    assert labels([
        {"id": "a", "job_title": "Process Operator", "name": "intake", "location": None},
    ]) == ["Process Operator"]
    assert labels([
        {"id": "a", "job_title": None, "name": None, "location": None},
    ]) == ["Untitled role"]
