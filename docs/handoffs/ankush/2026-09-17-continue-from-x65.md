# Continue from here — 2026-09-17

Read `AGENT-START-HERE.md` first, then `docs/SESSION-STATE.md`'s top `session_wrap` block
(X65) for full detail. Short version below.

## State
- Branch: `consolidated`, pushed to `origin/develop` at commit `bd50559`
  (`git push origin consolidated:develop`). `origin/develop` and `consolidated` were
  identical before this push (both at `b834fa6`), so this was a clean fast-forward.
- Working tree is clean — nothing uncommitted.

## What just landed (X65, `web/rubric.html`)
Fixed three user-reported display bugs on the Scoring rules page (Set up → Shortlist →
back to Set up):
1. `.approvalstrip` was `flex` with unfilled children, leaving a blank gap right of
   "Weights total" — now `display:grid;grid-template-columns:repeat(4,1fr)`.
2. "Must have" only ever showed 1 row (the campaign's one `HARD_FAIL` disqualification
   rule) instead of all mandatory scored criteria — `renderMustHave` now lists every
   active `MANDATORY` weight with its weight, tagging the real eligibility gate(s)
   separately as "Not eligible if missing".
3. "Counts in their favour" filtered out any `weight === 0` preferred criterion (most of
   them, since `requirement_service` seeds preferred skills at weight 0 by default) —
   filter removed, full list now renders.

Also folded in and committed X63 (pending-resumes IndexedDB stash for AI-start →
"review manually") and X64 (new-campaign.html rubric weight delete-sync + zero-out fix)
which were done earlier this session but left uncommitted.

Verified live against real campaign `5212142d-6150-4ecc-b2c7-9e97d8e31312` via the actual
API before and after — not just read from code.

Full detail, root causes, and what's still open (`X65`'s "Left / next" note: only tested
against one campaign with real mandatory/preferred data; still want a check against a
campaign with zero preferred criteria and zero hard-fail rules — the empty-state text in
both render functions) is in `docs/SESSION-STATE.md` and `docs/plan/04-KNOWN-DEFECTS.md`
(`X65`).

## Branch/authorization reminders (from CLAUDE.md — still in force)
- Canonical branch is `consolidated`; the two-person exclusive-file/short-branch regime
  in `docs/plan/08-TWO-PERSON-DELIVERY.md` only starts once its bootstrap PR into
  `azure-provider` lands, which it hasn't yet.
- `git fetch origin` before starting anything new — check
  `git log --oneline HEAD..origin/azure-provider` and `..origin/develop`.
- Publishing/pushing needs explicit user authorization each time; this push was
  explicitly requested.
