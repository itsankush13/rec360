# B12 offer-letter template + B06/B10 merge status — handoff for Subhadeep

Date: 2026-09-12. Acting developer: Ankush, confirmed explicitly this session (not
inferred). Demo is 2026-09-14 — two days out.

## Housekeeping first: `b06` and `b10` are now merged into `consolidated`

Both branches named "unmerged" in the last `SESSION-STATE.md` save
(`ankush/b06-jd-generation`, `ankush/b10-outlook-adapter`) were merged into
`consolidated` this session, `--no-ff`, zero conflicts, single Alembic head
(`7a12e4f9c3d6`) — commits `1a4...`/`...` (see `git log --oneline -5` on
`consolidated`). Reasoning: unmerged code doesn't help Monday's demo, and both were
already full-suite-verified on their own branches last session. Still **not pushed**
to `origin/consolidated` (`consolidated` is now well ahead of it) — no push without
your/the user's explicit authorization, per `08-TWO-PERSON-DELIVERY.md`.

Correction to the prior session-state note: `ankush/b03-relevance-ranking` was
**already** an ancestor of `consolidated` (it was in the earlier eight-branch batch
merge) — the "three branches unmerged" line in that save was stale/wrong on that one
branch; only b06 and b10 were actually still separate.

Their own handoffs (`2026-09-12-b06-jd-generation.md`, `2026-09-12-b10-outlook-adapter.md`)
already carry the suggested backlog deltas for those items — nothing new to add there
beyond "now integrated, not just branch-complete."

## What was built this slice: B12 offer-letter template

Per the agreed execution order (`B10`/`B11`/`B12` proxy→real). Chose B12 over B11
(calendar invites) because B12 needs no live external system to build against —
B10 and B11 both need a real Outlook profile to move past "unit-tested against a fake
COM double," which isn't confirmed available here; B12 is pure template + audit + the
adapter B10 already built.

- `app/core/offer_letter.py` — new. `render_offer_letter(...)`, a single deterministic
  template (candidate, role, company, base salary, allowance breakdown, total package,
  grade, start/expiry dates, notes, a standard declaration). Deliberately **no LLM
  layer** unlike B06's JD generation — this is the one document with money and a legal
  declaration in it, and the wording must not vary by model sampling.
- `app/api/offers.py`:
  - `draft_offer`/`revise_offer` now render the letter (using `settings.company_name`,
    the campaign's `job_title`, the candidate's `full_name`, the acting user's
    `full_name` as `hr_name`) and carry it as `after.letter` in the `OFFER_DRAFTED`
    audit event and in the `OfferOut.letter` response field — that response **is** the
    "draft for HR review" B12 asks for; there's still no separate offer table, per the
    module's existing no-new-table design.
  - `send_offer` now actually calls `outlook_adapter.get_mail_adapter().send(...)`
    (B10's adapter) with the rendered letter as the body, instead of only recording
    `recipient_email`. `simulated`/`send_detail` are folded into the `OFFER_SENT` audit
    row and into `OfferSentOut`, the same shape B10 used for messages. Default
    (`email_backend=simulated`) behavior is unchanged: nothing is transmitted, an
    honest audit row is written — same as before this slice.
  - No new `AuditAction` — reused `OFFER_DRAFTED`/`OFFER_SENT`, so **no `web/audit.html`
    label change is needed** for this slice.
- Tests: `tests/test_offer_letter.py` (6 new, the template in isolation) +
  `tests/test_offers_api.py` (2 new/1 renamed: letter appears in draft/revise
  responses and changes with a revision; send now asserts `simulated` explicitly and a
  new test drives a fake real-adapter send end to end, mirroring
  `test_messages_api.py`'s pattern).
- Verified: `test_offer_letter.py` + `test_offers_api.py` + `test_messages_api.py` +
  `test_outlook_adapter.py` — 42 passed. Full suite once: **579 passed** (up from 572
  after the b06/b10 merge), same 5 pre-existing pptx-module failures, 6 skipped — no
  regression. Committed directly to `consolidated` (`67a5b44`) — solo backend slice,
  no branch/merge overhead needed since nothing else was in flight on these files.

## Explicitly NOT built / not verified

- `web/offer.html` (your file) still shows the "SIMULATED — INTEGRATION PENDING · no
  letter or email sent" banner and doesn't display or let HR review the rendered
  `letter` field yet — the API now returns it, the screen doesn't consume it.
- The letter is never actually delivered as a real email attachment/document — it's
  sent as the adapter's `body` text (same transport B10 uses for messages), not a
  PDF/Word offer letter. If the client expects a formatted document rather than plain
  text in the email body, that's a follow-up, not done here.
- `OutlookMailAdapter`'s real-COM path remains unverified against a live mailbox
  (unchanged from B10's own caveat) — offers now exercise the identical adapter, so
  the same caveat applies to offer sends.
- B11 (calendar invites) — not touched this session.

## Suggested `00-MASTER-BACKLOG.md` B12 delta

- [x] Create an approved offer-letter template — `app/core/offer_letter.py`,
      deterministic, no LLM.
- [x] Populate candidate, role, salary, declaration, joining terms, other approved
      fields — all present in the rendered letter.
- [x] Generate a draft for HR review — `OfferOut.letter` in the draft/revise response.
- [~] Send it to the candidate — `send_email()`'s replacement (`outlook_adapter`) is
      now called from the offer workflow; simulated by default, same unverified-against-
      a-live-mailbox caveat as B10. Screen (`web/offer.html`) doesn't show it yet.
- [~] Track accepted / declined / pending — unchanged, already real (lifecycle + UI).
- [x] Update the final hiring outcome — unchanged, already real.
- [x] Preserve the offer and response in the audit trail — unchanged, already real.

## Next

No instruction on what's next after this. Candidates: (a) B11 (calendar invites, same
real-mailbox caveat as B10), (b) `web/offer.html` wiring to show the letter and honest
`simulated`/`send_detail` state (your file), (c) push `consolidated` / open the
bootstrap PR now that b06/b10/B12 are all integrated, (d) something else — ask.
