# B10 local Outlook mail adapter — handoff for Subhadeep

Date: 2026-09-12. Acting developer: Ankush. Branch: `ankush/b10-outlook-adapter`
(`b4fc4c1`, off `consolidated` at this session's `4703233`) — **not merged into
`consolidated`, not pushed, no PR**, same local-only mode as `ankush/b06-jd-generation`.
User explicitly authorized adding and installing `pywin32` into the verified venv for this
slice; no other environment change was made.

Important environment note unrelated to this feature: this venv's Python is actually
**3.12.10**, not the 3.13.5 CLAUDE.md describes as verified. Worth reconciling — I did not
investigate further or touch the venv beyond installing `pywin32`.

## What was built

Per the agreed execution order's item 5 (`B10`/`B11`/`B12` proxy→real), scoped to just B10's
"use the local Outlook mailbox through pywin32" line, since no real Outlook profile was
confirmed available here and B11 (calendar)/B12 (offer letters) are separate slices.

- `app/core/outlook_adapter.py` — new. `MailAdapter` interface, `SimulatedMailAdapter`
  (default, byte-for-byte the pre-existing behavior: records intent, transmits nothing), and
  `OutlookMailAdapter` (COM automation via `win32com.client`, dispatch function injected so
  tests never touch real COM). `get_mail_adapter()` picks between them from
  `settings.email_backend` — defaults to `"simulated"`; only an explicit `"outlook"` value
  attempts a real send, and falls back to simulated if the adapter can't be constructed.
- `app/core/config.py` — new `email_backend: str = "simulated"` setting.
- `app/api/messages.py` — `send_message` now calls the adapter for `EMAIL` sends only
  (SMS/PHONE_NOTE have no adapter, stay simulated). The audit row's `after.simulated` and new
  `after.send_detail` reflect what actually happened instead of a hardcoded `True`. `MessageOut`
  gained additive `simulated`/`send_detail` fields, populated in both the send response and the
  log-reading endpoints (`_as_message`), so a future UI can show the honest transmission state
  per the "visible simulation labels" UX rule in `AGENT-START-HERE.md` section 5.
- `requirements.txt` — `pywin32>=306; sys_platform == "win32"`, installed into the venv.
- Tests: `tests/test_outlook_adapter.py` (7 new — simulated adapter, Outlook adapter against a
  fake COM double for both success and failure, adapter-selection logic including the
  fallback-when-unconstructable path) and two new tests in `tests/test_messages_api.py`
  (real-send-through-fake-adapter marks `simulated=False` end to end; SMS never reaches the
  mail adapter even when `email_backend="outlook"`).
- Verified: `test_outlook_adapter.py` + `test_messages_api.py` 19 passed. Full suite once:
  **567 passed** (up from 559 at last baseline), same 5 pre-existing pptx-module-gap failures,
  6 skipped — no regression.

## Explicitly NOT built / not verified

- **Never run against a real Outlook mailbox.** Every test uses a fake COM double
  (`OutlookMailAdapter(dispatch=...)`). `email_backend` defaults to `"simulated"`, so nothing
  changes for anyone until someone deliberately sets it to `"outlook"` on a machine with a
  signed-in Outlook profile and confirms it actually sends. Treat the real-COM path as
  unverified until that happens.
- Reply parsing / candidate-stage-update-from-reply (B10's other two checklist lines) — not
  started. Reading a real mailbox is a materially different, harder problem than sending, and
  needs the same real-mailbox access this session didn't have.
- Recruitment/application ID in the subject — blocked on `B20` (identifier model), which has
  nothing built yet; the subject line uses whatever the caller (eventually `web/comms.html`)
  passes today.
- `web/comms.html` — Subhadeep's file — doesn't surface `simulated`/`send_detail` yet; the API
  contract is ready for it.
- B11 (calendar invites) and B12 (offer-letter template) — not touched this session.

## Suggested `00-MASTER-BACKLOG.md` B10 delta

- [~] Use the local Outlook mailbox through `pywin32` — adapter built and unit-tested against a
      fake COM double; **not exercised against a real mailbox.** Off by default
      (`email_backend=simulated`); opt-in via `email_backend=outlook`.
- [ ] Send the shortlisted-candidate report to the hiring manager — unchanged, not built.
- [ ] Put the recruitment/application ID in the subject — blocked on `B20`.
- [ ] Parse replies where the subject is unchanged — not started.
- [ ] Update the candidate stage from the reply — not started.

## Next

No instruction on what's next after this. Candidates: (a) continue to B11 (calendar invite via
the same pywin32 path — same real-mailbox caveat applies), (b) build reply parsing for B10 once
a real mailbox is available to test against, (c) something else.
