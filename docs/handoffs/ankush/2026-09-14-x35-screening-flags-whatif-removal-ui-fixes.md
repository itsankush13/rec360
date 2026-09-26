# X35 screening/flagging change, whatif propose removal, page-title/pagination/flash fixes — handoff for Subhadeep

Date: 2026-09-14. Acting developer: Ankush. Branch `consolidated`. Committed and pushed to
`origin/consolidated` at `463807c` (this slice) and `bd85ec4` (session-state note), on top of
`50231af` (a prior session's already-committed-but-unpushed B05 work, pushed at the same time).

Scope: five direct user-instructed changes, from a screenshot of `index.html`'s "Held, and
holding up" band plus written follow-up instructions. Full technical detail also lives in
`docs/plan/04-KNOWN-DEFECTS.md` **X35** and five rows in `docs/DECISIONS.md` dated 2026-09-14;
this document is the one-stop summary for pulling the branch cold.

## 1. Scanned CVs, no-identity CVs and duplicates are screened and flagged, not held (X35 / B01)

**Before:** a photographed/scanned CV with too little extracted text (`NO_TEXT_EXTRACTED`) and a
CV with no name, email or phone at all (`INCOMPLETE_CONTENT`) both hard-failed the processing
job (`ProcessingJob.status = FAILED`). No `Candidate` row was created, and
`evaluation_service._candidates_for_batch` only ever selects `COMPLETED`/`DUPLICATE` jobs — so
these CVs were **never scored**, only listed as an exception needing a manual "Send for
scanning" / "Read by hand" action. A duplicate application was already auto-merged into the
existing `Candidate` record server-side, but the UI still showed a "Merge them" button implying
pending manual work that didn't exist.

**After:** all three are screened along with every other CV.

- `app/core/document_intake.py::extract_document` — text under `MIN_TEXT_CHARS` (even after OCR)
  no longer raises `DocumentRejected`. Returns the `ExtractedDocument` with a new `low_text: bool`
  flag instead.
- `app/services/processing_service.py::process_job` — `low_text` sets
  `requires_review=True` + `error_code=NO_TEXT_EXTRACTED` and appends a plain-English note, but
  processing continues to candidate creation and evaluation. The previous
  `identity.is_empty` early-return (`FAILED`) is gone; it now falls into the same
  `Candidate`-creation path as the existing partial-identity case (a name but no email/phone),
  with `error_code=INCOMPLETE_CONTENT`. The duplicate branch's `error_message`/`requires_review`
  are now appended/OR'd rather than overwritten, so a file that is both low-text *and* a
  duplicate keeps every flag instead of the duplicate message silently replacing it.
- `app/core/analytics.py::kpis()` — new `exceptions.screened_by_reason`: same shape as the
  existing `by_reason`, but over jobs that are `requires_review` **and not** `FAILED` — i.e.
  screened anyway. `by_reason` is unchanged in shape but can now only ever contain genuinely
  blocking codes (`PASSWORD_PROTECTED`, `CORRUPT_FILE`, `UNSUPPORTED_FORMAT`, `EMPTY_FILE`,
  `FILE_TOO_LARGE`, `EXTRACTION_FAILED`, `STORAGE_FAILED`, `INTERNAL_ERROR`).
- `app/api/compat.py::serialize_run` (`GET /api/runs/{id}`, the contract `campaigns.html` and
  `leaderboard.html` read) — `held_files` narrowed to `status == FAILED` only (unchanged shape:
  `reason`/`action`/`can_retry`). New `flagged_files` list for `requires_review` jobs that
  aren't `FAILED` (`{id, filename, note, merged: bool}`, no action/retry field — there is
  nothing to do).
- `app/api/compat.py::extract_text` (`POST /api/documents/extract-text`, the **job description**
  file reader used by the compose box — a different endpoint, no screening concept) explicitly
  re-raises its own 422 for `extracted.low_text` now that `extract_document` itself no longer
  does. A JD still needs to be rejected outright: there's no downstream flagging step for it.
- `web/index.html`'s "Held, and holding up" band: `HELD_WORDS` (action-required, from
  `by_reason`) dropped `NO_TEXT_EXTRACTED`/`INCOMPLETE_CONTENT`; new `FLAG_WORDS` renders
  `screened_by_reason` as plain rows tagged "Flagged", no button. Duplicates render
  "…automatically merged into the existing profile(s)" tagged "Merged", no button.
- `web/campaigns.html`'s per-campaign held-files block reads the new `flagged_files` list
  separately (new `.flagged` CSS, muted `--ink-3`), never offering a retry link or action for an
  already-screened file.

**If you're touching `discover.html`, `new-campaign.html`'s upload step, or anything else that
reads `held_files`/`GET /api/runs/{id}`:** check whether it needs the same `flagged_files`
treatment — `held_files` no longer includes `DUPLICATE`/`requires_review` jobs, only true
`FAILED` ones. `index.html` and `campaigns.html` are the only two frontend consumers today (both
updated); nothing else in `web/**` reads `held_files`.

Tests: `tests/test_processing.py`, `tests/test_document_quality.py`, `tests/test_analytics.py`,
`tests/test_frontend_integration.py` — renamed/rewritten where the old test asserted the old
hard-fail behaviour. Full suite: 766 passed, 6 skipped, 9 pre-existing `X32` failures (unrelated
Node-harness issue, documented).

**Not verified live against a restarted API process** — the shared dev server on port 8000
during this session belonged to another session and wasn't restarted. Verified by the pytest
suite only. If you pull this and your own `api` process is still running old code, restart it
before judging the Today page's "Held, and holding up" numbers.

## 2. `web/whatif.html` — removed the "Propose these weights for approval" section (B17)

On direct instruction: the whole propose UI (actor/approver `<select>`s, propose button,
confirm/error text, and the JS calling `POST .../what-if/proposals`) is gone. The page is
preview-only now — move a slider, watch the two ranked lists move, nothing else.

**Backend is untouched.** `whatif_service.propose/approve/reject/create_rubric_draft` and the
five `/api/campaigns/{id}/what-if/proposals` routes still exist and are fully tested; no screen
calls them anymore. If a future slice wants this back (a different page, a different flow), the
API is ready — nothing to rebuild there.

## 3. `web/compare.html` — page size 10, explicit "Page X of Y" (B16)

`PAGE_SIZE` 25 → 10. Pager now reads e.g. `1–7 of 7 · Page 1 of 1` (browser-verified against the
real 7-candidate HSE OF campaign). The `pages = Math.ceil(total / PAGE_SIZE)` formula was
already correct for any page size — nothing else changed. A 12+-candidate campaign wasn't
available to verify the 2-page split live; the math is unchanged from the already-tested
25/page version, so this is a formula-level guarantee, not a live-verified one.

## 4. Page-title styling reverted on `candidate.html`/`compare.html`/`leaderboard.html` (B08)

A 2026-09-13 change had bumped these three pages' `.page-state .kicker` to 46px/800 and
uppercased it ("CANDIDATE 360"). On direct instruction ("make these look like the Start Campaign
page — same text, same boldness"), reverted to the sitewide `.arch h1` treatment used
everywhere else (42px/600, mixed case: "Candidate 360", "Compare Candidates", "Candidate
shortlist"). The maroon/lattice banner background itself is unchanged — only the title's
size/weight/casing.

## 5. Removed the pre-load flash of fake data (B08)

Reported as: "a page shows static frontend for 1-2 seconds, then the real values." Two pages had
fully-written, realistic-looking sample data baked into their HTML that a live fetch would
unconditionally overwrite once it resolved — a visible flash on every load.

- `web/leaderboard.html`: ten fake candidate rows, fake headline numbers, and two whole sections
  ("How all 622 came out", "Why these 24…") plus a `.sig` line that turned out to be **always**
  hidden by `render()` once real data loads (dead sample content, never actually shown live) —
  all replaced with a neutral loading placeholder / `hidden` by default.
- `web/decisions.html`: ten fake shortlist rows, but this page has a real second purpose for
  that markup — `renderRows()` deliberately leaves it in place, labelled "the shipped example",
  when the live fetch fails. Couldn't just delete it. Instead: `hidden` by default, revealed only
  once the real outcome (success *or* failure) is known — flash gone, fallback still works.
- `web/candidate.html` has the identical shipped-example-on-failure shape (static
  "Haitham Al-Otaibi" / score "91", with `renderUnavailable()` as the fallback path) and was
  **deliberately not touched** — distinguishing "still loading" from "showing the example" here
  needs more care across a much bigger page than this slice had room for safely. If you pick
  this up: the pattern to copy is decisions.html's (`hidden` by default, unhidden in both the
  success path and the `renderUnavailable()`/failure path).

Both fixed pages browser-verified live against the real HSE OF campaign: no fake row ever
appears, real data lands directly into the loading placeholder's place.

## What to check before building on top of this

- If your work reads `ProcessingJob.status`/`error_code`/`requires_review` anywhere not listed
  above, check whether it assumed `NO_TEXT_EXTRACTED`/`INCOMPLETE_CONTENT` implies `FAILED` —
  that assumption is no longer true.
- `whatif.html` no longer has any UI path to `POST .../what-if/proposals` — don't assume a
  recruiter can reach that endpoint from the app today.
- `web/index.html`'s live "Held, and holding up" numbers will look very different (much smaller
  "held" count) the moment the API process running against your database is restarted onto this
  code — that's expected, not a regression.
