# Ankush handoff — 2026-09-12 B06 AI-generated JD

## Acting developer
Ankush (backend `app/**`, per [08-TWO-PERSON-DELIVERY.md](../../plan/08-TWO-PERSON-DELIVERY.md)).

## What this session did
Branched `ankush/b06-jd-generation` off `consolidated` (which at this point already contains all
eight previously-separate local fixes, merged locally this same session — see
`2026-09-12-local-integration-merge.md`). **Not pushed, no PR** — same local-only mode.

Scope: `00-MASTER-BACKLOG.md`'s B06, "Nothing built. No JD-generation code in the tree." Built
the backend generation/reuse service and contract; the UI half (`web/new-campaign.html`
accept/edit/upload/override, uncertainty display) is Subhadeep's and untouched.

### What was built
- **`app/core/jd_templates.py`** — a small, hand-picked registry of industry-standard templates
  for common roles (Software Engineer, Data Analyst, Recruiter, HR Business Partner, Project
  Manager, Sales Executive). This is the deterministic floor, in the same relationship to a
  generated JD that `rubric_presets.py`'s `MARKET_STANDARD` weighting has to a rubric: a starting
  point, never a delivered answer. Deliberately no remuneration figures in a template — a
  fabricated salary band is actively misleading, unlike a generic skills list.
- **`app/agents/jd_agent.py`** gains `generate_jd(...)` alongside the existing `parse_jd`. Same
  client factory (`get_cached_chat_model`), same JSON-only prompt convention. Returns the same
  structured fields `parse_jd` extracts (`role_title`, `required_skills`, `preferred_skills`,
  `min_experience_years`, `education_requirement`, `key_responsibilities`, `seniority_level`)
  plus `jd_text` — the two stay in sync by construction rather than needing a second round-trip
  through the extractor. Accepts a matched template and prior similar-campaign JD text as prompt
  context.
- **`app/services/jd_generation_service.py`** — the orchestration, mirroring
  `evaluation_service._apply_llm_refinement`'s double-catch safe-fallback shape exactly:
  - Matches the campaign's `job_title` against the template registry (loose substring match).
  - **"Learn from prior campaigns"**: queries other campaigns with the exact same `job_title`
    (case-insensitive) that already have a saved `job_description`, most recent 3, and passes
    their text to the model as "prior JDs this company used for a similar role." This is a real
    few-shot signal, not a claimed one — no existing reuse-query helper existed in
    `campaign_service.py` to build on, so this is new code.
  - **Uncertainty flag**: `uncertain=True` whenever there's no template match *and* no prior
    campaign with this title — this is the "niche role" signal, independent of whether the LLM
    call itself succeeds. A recruiter should see the flag even on a fluent-looking generated JD
    if nothing backs it up.
  - **Safe fallback**: if the agent import fails, or the LLM call raises, and a template
    matched, returns the template alone (`source: "template_only"`) with an explicit
    uncertainty reason. If no template matched either, raises `JDGenerationUnavailableError` →
    422 — an honest failure ("write the JD directly") rather than a guess.
- **`POST /api/campaigns/{campaign_id}/jd/generate`** (`app/api/jd.py`, new router, mirrors
  `requirements.py`'s shape and is registered in `app/main.py`). **Returns a preview only —
  nothing is persisted.** The recruiter accepts it through the existing
  `PATCH /api/campaigns/{id}` (`job_description`), same as any other edit. This keeps the
  product's existing rule (AI recommendation separate from human decision) intact rather than
  inventing a new accept/reject mechanism for this one feature.
- Request accepts optional overrides (`grade`, `min_experience_years`, `required_skills`,
  `key_responsibilities`, `remuneration`) — "let the user accept, edit, ... or override" as an
  input to generation, not just a post-hoc edit.

### What was not built (explicitly out of scope this slice)
- `web/new-campaign.html` doesn't call this endpoint yet — no UI trigger, no accept/edit/upload
  affordance, no uncertainty display. That's Subhadeep's file.
- "Learn from prior campaigns" only matches on exact `job_title` string equality (case-folded).
  Nothing fuzzy (e.g. "Software Engineer" vs "Senior Software Engineer") — a real fuzzy-reuse
  story would need its own design; this session kept the query honest about what it actually
  does rather than guessing at similarity.
- No new persisted "generation event" or audit row — this is a stateless preview endpoint, like
  `/requirements/extract`'s dry-run-adjacent shape before it commits. If the product later wants
  to audit "a JD was AI-generated" the same way other AI actions are audited, that's separate
  scope, not assumed here.
- Paste/upload of an existing JD file, as an alternative "override" input, is a
  `web/new-campaign.html` concern (there's already a general upload/extract path via
  `/requirements/extract` with `jd_text` this could reuse) — not touched.

## Verification
`tests/test_jd_generation.py` — 5 new tests, all passing: LLM output returned and not persisted;
a niche role flagged uncertain even when the LLM succeeds; falls back to the template when the
LLM fails (for a role with a template); fails honestly with 422 when there's no template and the
LLM fails; a prior same-title campaign is passed as context and clears the uncertainty flag.

Run together with `test_requirements.py` + `test_campaigns.py`: 23 passed. Full suite once:
**564 passed** (up from 559 before this branch), 5 failed (pre-existing `test_pptx_intake.py`
`pptx` module gap, unrelated), 6 skipped — no regression.

## Suggested `00-MASTER-BACKLOG.md` delta (Subhadeep to apply after review)
Under B06, change the summary from "**Nothing built.** No JD-generation code in the tree." to
"**Backend built, unmerged; screen not wired.**" and check:
```
- [~] Generate a JD after role entry — API contract built
      (`POST /api/campaigns/{id}/jd/generate`), preview-only, not persisted. Screen doesn't
      call it yet.
- [~] Learn from prior campaigns — implemented for exact job_title match only (no fuzzy
      reuse); passed to the model as few-shot context.
- [x] Use an industry-standard template for new common roles — `app/core/jd_templates.py`,
      6 roles, used as the deterministic floor and as LLM context.
- [x] Flag uncertainty and request input for niche roles — `uncertain`/`uncertainty_reason`
      on the response, independent of LLM success.
- [ ] Let the user accept, edit, delete, paste, upload, or override — override inputs exist
      on the generate request; accept/edit/paste/upload UI not built (Subhadeep, new-campaign.html).
- [x] Pitch it as a company-learning feature, not random internet generation — prior-campaign
      reuse and the template baseline are both real inputs to the prompt, not decoration.
```

## Next
Either continue toward the `web/new-campaign.html` wiring (Subhadeep's file — this session
supplies the contract), or move to the next agreed backend item (`B05`, then `B07`) per
`00-MASTER-BACKLOG.md`'s execution order. No instruction given this session on which.
