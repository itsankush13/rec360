# Ankush handoff — 2026-09-12 X13/X15/X16

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
Continuing the same session as `2026-09-12-flaky-audit-ordering-fix.md` (that work is on its
own branch, `ankush/flaky-audit-ordering`, `61bf422`). Checked out `consolidated` again and
branched `ankush/x13-x15-x16-cv-source` (`313c069`) for the next items named in
`docs/SESSION-STATE.md`'s `next_session_start_with`: X13, X15, X16, in that order, then X11's
remainder. **Not pushed, no PR** — same local-only mode as the other six branches now sitting
locally.

### X13 — SharePoint link resolves on the path tail alone
Re-derived the actual bug rather than assuming the fix shape's two bullets were independent:
`_resolve_url`'s shrink-from-the-left search had no floor. It kept dropping leading URL
segments until *any* suffix matched *something* under a sync root — reproduced by hand with
`docs/plan/04-KNOWN-DEFECTS.md`'s own fabricated example
(`personal/x/Documents/Work/Resume-Screening/CV-Repository`), which still matched a real,
unrelated `CV-Repository` folder once the search shrank far enough.

Fix: `app/core/cv_source.py`'s new `_max_discardable_prefix()` recognises `personal/<user>`
and `sites/<name>` (also `teams/<name>`) as the URL's site identity — the one part that is
never mirrored as a literal local folder, because the sync client's local root already *is*
that library. The search may discard at most that marker pair, never further. Also refuses
outright (`CVSourceResolutionError`, "more than one") when two sync roots tie for the best
(longest) match, rather than silently taking whichever root was checked first.

**Not done**: verifying a sync root's own tenant/account identity against the URL's hostname
(the fix shape's other bullet). That needs the real OneDrive-for-Business registry shape
(`UrlNamespace`/`MountPoint` under `HKCU\Software\SyncEngines\Providers\OneDrive\<GUID>`, or
similar) read from an actual pilot machine to implement without guessing at a naming
convention that might not hold in the field. Flagging rather than guessing, per the project's
own evidence standard.

### X16 — UNC paths shape-recognised, not verified
`resolve()` now runs the same `is_dir()` existence check for a UNC path that a local path
already got, raising the same honest `CVSourceResolutionError` instead of accepting the shape
and failing later at listing or import. Tested with `monkeypatch.setattr(Path, "is_dir", ...)`
since no real network share is available here — this proves the code path, not that a real
share resolves; the X16 checkbox for a real network share is still open.

### X15 — ON_HOLD resume gate
The backend was already correct: `held_from_status` is stored (not derived) on
`CandidateLifecycle`, and `tests/test_lifecycle.py::test_a_hold_resumes_where_it_paused`
already exercises put-on-hold-and-resume against a real API-created candidate record — this
was not actually an untested backend path.

What was missing: `LifecycleOut` never exposed `held_from_status` to callers, only used it
internally to compute `next_steps`. `web/timeline.html` (Subhadeep's file, read only to
understand the gap — not edited) works around that by re-deriving "where did this hold come
from" itself, walking `transitions` backwards to find the last gate reached
(`web/timeline.html:317-321`). That is a real duplicate of stored state, and duplicating it
in JS is exactly the "derive current state on read" pattern `CLAUDE.md` and `X8` warn against
— it will disagree with the stored value the moment a candidate is held and resumed more than
once.

Fix: `LifecycleOut` now carries `held_from_status`/`held_from_label`, populated straight from
the stored column. Extended the existing real-record test to assert both fields on hold and
that they clear on resume.

## Verification
- `tests/test_cv_source.py`: 10 passed (4 new: fabricated-tail-not-matched, ambiguous two-root
  refusal, deeper-root-wins-without-ambiguity, UNC-does-not-exist).
- `tests/test_lifecycle.py`: 37 passed (extended, not new — same real hold/resume test).
- `tests/test_discovery.py`: 14 passed, unaffected by the `_resolve_url` change.
- Full suite once on this branch: **544 passed, 6 skipped, 6 failed** — 5 pre-existing
  `test_pptx_intake` `ModuleNotFoundError`, plus `test_messages_api`'s flaky ordering assertion.
  **That flake is expected here**: this branch was cut from `consolidated`, not from
  `ankush/flaky-audit-ordering`, so it does not carry that fix. Re-running just
  `tests/test_messages_api.py tests/test_interviews_api.py tests/test_approvals_api.py` on this
  branch passed clean (81/81) on a second run — consistent with the already-documented flake,
  not a new regression from this branch's changes.
- Observed, unrelated to this task: the venv's Python is actually **3.12.10**
  (`.\venv\Scripts\python.exe --version`), not the 3.13.5 `CLAUDE.md` names as verified. Noting
  it since it's a documentation/environment mismatch someone should reconcile, not something I
  changed or investigated further — out of scope for X13/X15/X16.

## Requested central-doc deltas (I don't edit these directly — Subhadeep-owned)
For `docs/plan/04-KNOWN-DEFECTS.md`:
- X13: check the "ambiguous match refused" box; leave "tenant and site checked" **partially**
  addressed (site-identity bound is fixed; tenant-vs-registry check still open, reason above)
  and the "screen shows which sync root was matched" box open (API returns `root_path`
  already; a display decision is Subhadeep's). Suggest keeping X13 open, not closing it, with
  a note pointing at this handoff for what's actually fixed.
- X15: check "resume from hold checked" (was already true, now also true at the API-contract
  level) and note the new `held_from_status`/`held_from_label` fields for whoever changes
  `web/timeline.html` to consume them instead of its own backward-walk. Leave the "real
  candidate... timeline checked" box open — that's a browser check against the actual screen.
- X16: check "existence checked at resolve time, with the same honest error a local path
  gets"; leave "tested against a real network share" open.

For `docs/SESSION-STATE.md` (Subhadeep-owned; not edited directly — the user has not said
"save the state" this turn): seven local branches now await the same merge/PR decision — the
six from before plus `ankush/x13-x15-x16-cv-source`.

## Not done yet (explicitly deferred)
- X13's tenant/registry identity check, X15's timeline-screen walkthrough, X16's real-share
  test — all need infrastructure or a UI change this session doesn't have/own.
- X11's remaining "dedicated outcome chart" item: re-checked `08-TWO-PERSON-DELIVERY.md`
  section 4 before starting — it names that remainder as Subhadeep's ("Ankush stage-order/count
  correctness; Subhadeep outcome chart/display remainder"), and Ankush's half is already
  checked done in `04-KNOWN-DEFECTS.md`. Not picked up this session; nothing left there for
  this lane.
- No decision yet on merging/pushing any of the seven local branches, or opening PRs.

## Next-session start pointer
Read `AGENT-START-HERE.md` → `docs/plan/08-TWO-PERSON-DELIVERY.md` → `docs/SESSION-STATE.md` →
this file and the flaky-ordering handoff. Backend `next_session_start_with` queue is now
empty; ask the user whether to (a) merge/PR some or all of the seven local `ankush/*` branches,
or (b) pick a new B-item from `00-MASTER-BACKLOG.md` before starting further new work.
