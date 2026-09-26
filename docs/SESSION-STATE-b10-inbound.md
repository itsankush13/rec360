# B10 inbound / B11 feedback-from-reply — session state

Written 2026-09-13. Per `CLAUDE.md`'s two-person transition note, `docs/SESSION-STATE.md`
is Subhadeep-owned; this is Ankush's own handoff file for this session's work, not an edit
to that one.

Worktree: `.claude/worktrees/agent-a2c350138f08364a9`, branch `worktree-agent-a2c350138f08364a9`,
based on `consolidated` at `af5f398` (see "Worktree base" below — this needed fixing first).
Not pushed, not merged. A second, parallel agent in a separate worktree was building the
outbound half (the hiring-manager report, the from-account fix, and the subject-tagging that
appends `[REF-{campaign_id}]` / `[REF-{campaign_id}:{candidate_id}]`) at the same time; this
session never saw that code, only the tagging contract described in the task brief.

## Worktree base was wrong — fixed before any work started

This worktree's `HEAD` was at `ed9f08a` ("phase 1") — the merge-base of `consolidated` and a
much older, unrelated commit history (an early Streamlit/Render prototype: no `app/main.py`,
no `docs/plan/`, no `app/core/outlook_adapter.py`). It was NOT actually on `consolidated`
despite the task brief's framing. The working tree was clean (nothing uncommitted to lose),
so it was reset to `consolidated`'s real tip (`af5f398`, confirmed identical to
`origin/consolidated`) before any B10 work began. Flagging this because it means whatever
process created this worktree did not check out what it intended to; worth checking whether
the same happened to any other agent's worktree for this task round.

## Python version: the task brief and the actual repo disagree

The task brief (and the `CLAUDE.md` shown at session start) said the repo targets **Python
3.13.15** and to recreate the venv with that interpreter. After fixing the worktree base
above, `CLAUDE.md` **as actually committed on `consolidated`** says the opposite: verified on
**Python 3.12** (`venv reports 3.12.10`), and explicitly "Do not run pip install". The shared
venv at `C:\Users\ankush.saxena\talent-intelligence-system\venv\Scripts\python.exe` confirms
3.12.10, with every dependency this repo needs already installed (fastapi, the full
`langchain`/`langchain-groq`/`langchain-openai` stack, `pywin32`, `pytest`, `sqlalchemy`, ...).

What happened this session, in order:
1. Created a fresh venv in this worktree with Python 3.13.15 (per the task brief) and started
   `pip install -r requirements.txt` into it, since this worktree had no venv at all
   (gitignored, not copied by whatever created the worktree).
2. The coordinator flagged that the shared venv already has everything and a fresh install
   shouldn't be needed. Confirmed the shared venv works from this worktree (an absolute path
   with forward slashes; an earlier attempt with backslashes and a leading `cd` was refused by
   this session's sandbox as looking like a cross-worktree git operation) and reports 3.12.10.
3. Switched to the shared venv for everything below. Deleted the local 3.13.15 venv (2.1 GB,
   gitignored, never committed) to stop wasting disk/time on an install that wasn't needed.

Net effect: **all evidence below is from the shared, committed-convention Python 3.12.10
venv**, not 3.13.15. Nothing in this session's code is 3.12-vs-3.13 sensitive (no `Self` type
misuse, no new stdlib-only-in-3.13 usage), so this is a process note, not a risk to the code —
but the task brief's "3.13.15" framing does not match what is actually checked into
`consolidated` right now, and that gap should be resolved (which of the two is meant to be
true) before anyone else hits the same confusion.

## What's committed and passing

New files:
- `app/core/reply_ingestion.py` — `InboxReader`, same `_dispatch_outlook()` DI shape as
  `outlook_adapter.py`/`calendar_adapter.py`. Reads `namespace.GetDefaultFolder(6)`, matches
  `[REF-...]` in the subject via `REF_TAG_RE`, extracts campaign/candidate ids, sender,
  received time and body, and strips a best-effort quoted-history block
  (`strip_quoted_text` — see "What quote-stripping does and doesn't handle" below). Real COM
  use is wrapped in `pythoncom.CoInitialize()`/`CoUninitialize()`; the fake-double test path
  never touches `pythoncom` (gated on `dispatch is _dispatch_outlook`, an identity check, not
  a mock-detection heuristic). Gated on `settings.email_backend == "outlook"` — no new setting.
- `app/core/reply_classifier.py` — `classify_reply(body) -> ReplySignal`. Deterministic rules
  first (explicit decline/approve words, an ISO or plain-text date/time, a `$`/`₹` amount);
  LLM fallback only when no rule fires, via `app.core.llm_provider.get_cached_chat_model`,
  built lazily. Structured output follows `app/agents/weight_suggestion_agent.py`'s pattern —
  prompt for JSON only, strip markdown fences, `json.loads`, validate with a pydantic model —
  rather than `langchain`'s `.with_structured_output`, which nothing else in this repo calls.
  Never raises: an LLM failure or a schema-invalid response returns `intent="unclear",
  confidence=0.0` rather than propagating.
- `app/services/reply_service.py` — `ingest_replies`, `pending_decisions`, `apply_decision`.
  Writes one `AuditAction.EMAIL_REPLY_RECEIVED` event per reply (idempotent by `message_id`,
  the Outlook `EntryID`); auto-applies only a hiring-manager approve/decline/need-more-info
  reply, only when the sender resolves to an active `User` with role `HIRING_MANAGER`/`ADMIN`
  and the candidate is currently `WITH_HIRING_MANAGER`, via the existing
  `lifecycle_service.record_manager_review`. Everything else is proposed-only, always,
  regardless of the setting — see `docs/DECISIONS.md` (B10) for exactly what and why.
- `app/api/replies.py` — `POST /api/replies/ingest`, `GET
  /api/campaigns/{campaign_id}/replies/pending`, `POST
  /api/campaigns/{campaign_id}/replies/{entity_id}/apply`. Registered in `app/main.py`.
- `tests/test_reply_ingestion.py` (18 tests), `tests/test_reply_classifier.py` (11 tests),
  `tests/test_replies_api.py` (12 tests).

Changed files:
- `app/db/models.py` — new `AuditAction.EMAIL_REPLY_RECEIVED`.
- `web/audit.html` and `app/api/decisions.py` — label for the new action (the former is
  enforced by `tests/test_audit_trail.py::test_audit_page_maps_every_action_to_plain_english`;
  the latter isn't enforced the same way — see the gap noted below).
- `app/core/config.py` — new `settings.auto_apply_reply_decisions: bool = False`.
- `app/main.py` — registers the two new routers.
- `docs/plan/00-MASTER-BACKLOG.md`, `docs/DECISIONS.md`, `docs/plan/01-DEMO-MONDAY.md` — see
  the diffs in this commit for exactly what was ticked/added; not repeated here.

Evidence, all from this session, all from the shared 3.12.10 venv:
- `pytest -q tests/test_reply_ingestion.py tests/test_reply_classifier.py` → 26 passed
  (after two fixes made during this session: the amount regex was over-greedy about trailing
  whitespace, and an empty reply body was falling through to the LLM instead of returning
  "unclear" immediately — both fixed, both now covered by a test).
- `pytest -q tests/test_replies_api.py` → 12 passed.
- `pytest -q tests/test_audit_trail.py tests/test_interviews_api.py tests/test_lifecycle.py tests/test_outlook_adapter.py tests/test_calendar_adapter.py tests/test_decisions.py`
  → 131 passed (checking nothing touched by this change regressed: the new `AuditAction`, the
  audit label test, the interview/lifecycle flows this reuses).
- Full suite, `pytest -q` → **744 passed, 6 skipped, 0 failed, 271.78s**. The 6 skips are
  pre-existing and not from this change (not investigated further — out of scope for B10).

## What's explicitly out of scope, by design

- **No auto-application beyond a hiring-manager verdict.** A schedule confirmation, a
  reschedule request, a budget mention extracted from a reply, or a reply from a sender with
  no matching `User` row, is always recorded as a proposed decision only — never auto-applied,
  even with `auto_apply_reply_decisions=True`. There is no existing service call this module
  can point at for "reschedule to this new time" (the exact fields — duration, mode, location
  — aren't reliably in an email) or "auto-send an offer" without guessing, and guessing is
  exactly what this was asked not to do.
- **Interview feedback (`app/api/interviews.py`'s `/feedback` endpoint) is never auto-filled.**
  It needs `scores`/`strengths`/`concerns`, none of which a free-text email reliably carries.
  A "declined" reply on an interview thread is recorded and classified, but a person still
  fills in the structured feedback form themselves.
- **A campaign-level reply (`[REF-{campaign_id}]`, no candidate) is never auto-applied and its
  proposed decision cannot be applied through `POST .../replies/{entity_id}/apply`** — that
  endpoint only reaches `record_manager_review`, which needs a candidate. The endpoint refuses
  with a message saying so rather than guessing which candidate a reply naming none was about.

## What's unverified

- **Live mailbox.** Same caveat as the existing `outlook_adapter.py`/`calendar_adapter.py`:
  every test here uses a fake COM double (`dispatch=...`). Nothing in this session ran against
  a real, signed-in Outlook profile. `pythoncom.CoInitialize`/`CoUninitialize` around the real
  path is new (the two existing send-side adapters don't do this) and untested beyond "the
  code path that isn't exercised by tests looks right" — it should be run once against a real
  inbox before anyone treats it as working.
- **Quote-stripping (`strip_quoted_text`) is a heuristic, not a MIME-aware parser.** It handles
  Outlook's "-----Original Message-----" banner, the plain-text "From:/Sent:/To:/Subject:"
  header block, "On ... wrote:", and a trailing run of `>`-quoted lines. It does **not**
  handle: HTML-only bodies (moot for COM-read Outlook mail, whose `.Body` is plain text, but
  would matter if this reader is ever pointed at anything else), inline replies interleaved
  with quoted text rather than appended below it, a forwarded thread with multiple nested
  quote blocks (only the first marker found is used as the cut point), or a quoting style
  particular to a non-Outlook client not covered above. Where no marker matches, the full body
  is passed through unchanged rather than guessed at.
- **No real LLM call was made in any test.** The deterministic-rule tests assert the model
  builder was never invoked; the LLM-fallback tests mock the model's `.invoke()`. The prompt
  and JSON-parsing path have not been run against a real Groq/Azure response.

## A gap noticed while in here, not fixed (out of scope for B10)

`app/api/decisions.py`'s `ACTION_WORDS` dict (the Python-side label map used by
`GET /api/audit/actions`) is missing labels for several `AuditAction` values added since it was
last touched — `INTERVIEW_SCHEDULED`, `INTERVIEW_FEEDBACK_RECORDED`, every `APPROVAL_*` and
`OFFER_*` value, `CANDIDATE_HIRED`, `MESSAGE_SENT`, `SLA_REMINDER_SENT`, `SLA_ESCALATED` — all
of them fall back to the generic `"Action recorded"` string rather than failing, so nothing
catches this in CI (`test_the_filter_list_covers_every_action` only asserts a label exists and
differs from the raw enum value, which `"Action recorded"` satisfies trivially).
`web/audit.html`'s own `ACTION_WORDS` map — the one the actual audit screen reads, and the one
`test_audit_page_maps_every_action_to_plain_english` enforces — is complete. `EMAIL_REPLY_RECEIVED`
was added to both maps by this session for consistency, but the pre-existing gap in
`decisions.py` for the other actions was left alone as out of scope.

Also noticed: `Campaign.hiring_manager` (`app/db/models.py`) is a free-text `String` column —
a name, not an email, and there is no email field on `Campaign` at all. The real
hiring-manager identity/email used for anything that actually needs to reach them (
`lifecycle_service.send_to_hiring_manager`'s `manager_id`, `ManagerReview.reviewer_id`) comes
from the `User` table instead. This session's auto-apply resolves the reply's sender against
`User.email` for exactly that reason. Relevant to whoever is building the outbound
hiring-manager report in parallel: if that report's recipient address is meant to come from
`Campaign.hiring_manager`, it will need a real email somewhere, because that column isn't one.

## Next steps (not started this session)

- Wire an "ingest replies" button and a pending-decisions list into a `web/*.html` screen —
  no UI was touched this session, by design (see the task's scope).
- Verify `pythoncom.CoInitialize`/`CoUninitialize` and the real `EntryID`/`SenderEmailAddress`/
  `Body` field reads against an actual signed-in Outlook profile.
- Resolve the Python 3.12 vs 3.13 discrepancy above — pick one and make `CLAUDE.md`,
  `runtime.txt`, `.python-version` and the task-briefing material agree.
