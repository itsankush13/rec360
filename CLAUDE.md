# Talent Intelligence System

Agent entry point: read [AGENT-START-HERE.md](AGENT-START-HERE.md) for the complete
planning read order, evidence-based done/left reconciliation and execution/update loop.

## Canonical tree and branch

Only this folder is live code. These siblings are dead prototypes: `app/`, `app-v2/`,
`talent-intelligence-system-final/`, `Recruitment-360-Delivery/`. Their `SESSION-STATE.md`
files name the wrong tree as canonical. Do not read or edit them.

**Work on `consolidated`. Nothing else.** It is the only branch that has everything: it is
`origin/azure-provider` plus the Python 3.13 upgrade, the cp1252 crash fix, the plan folder,
the ported offer/hired states, and (as of 2026-09-13) `Subodhip` — Subhadeep's frontend lane
(navigation scaffold, the X18 durable-campaign fix, campaign UX) — merged in locally. There is
no branch named `Subhadeep`; `Subodhip` is now fully contained in `consolidated`'s history and
is not a separate place to work. Do not commit to `azure-provider`, `py313-upgrade`, or
`py313-upgrade-archive` — the last two are a discarded lifecycle implementation kept only
for reference.

`docs/SESSION-STATE.md` on `consolidated` is the current session state. Three other files in
this workspace look like a session state and are all dead; do not restore from them.

Two-person transition: [08-TWO-PERSON-DELIVERY.md](docs/plan/08-TWO-PERSON-DELIVERY.md)
defines exclusive files and the common-baseline gate. Until the authorized bootstrap PR
lands, the branch rule above remains active. After its shared SHA is recorded, use short
owner/task branches from `origin/azure-provider`, with PRs explicitly targeting
`azure-provider`; stop developing directly on `consolidated`. Publication still requires
the existing explicit authorization. Central plan/session files are Subhadeep-owned;
Ankush supplies updates through PR evidence or his own handoff files.

**`consolidated` was published to `origin/consolidated` on 2026-09-12 with explicit user
authorization.** It tracks that remote branch. Bootstrap PR/merge into `azure-provider`
remains pending; branch publication alone does not complete the shared-baseline gate.

**One branch is the product on the remote: `azure-provider`.** Verified 2026-09-12: `main`, `phase-b`,
`phase-c` and `phase-d` are all ancestors of it with zero unique commits. They are historical
checkpoints, not parallel work. Do not treat them as branches to track or merge.

**Fetch before you build.** On 2026-09-12 two people built the same lifecycle state machine
in the same two hours, in the same six files, producing two Alembic heads. The second one was
thrown away. `git fetch origin && git log --oneline HEAD..origin/azure-provider` costs five
seconds and would have prevented it.

## The plan is the source of truth — read it, then update it

`docs/plan/` holds the product vision, the backlog, and the checklist. Start at
`docs/plan/README.md`.

**Before any task:** find its plan ID (`B01`-`B24` backlog, `D1`-`D8` demo builds, `X1`-`X9`
defects). Work against that ID. A task with no plan ID is out of plan — say so and ask before
building.

**After any task, before reporting it done, in the same turn:**

1. Tick the boxes in `docs/plan/00-MASTER-BACKLOG.md` and `docs/plan/01-DEMO-MONDAY.md`
   for what actually landed. `[ ]` not started · `[~]` in progress · `[x]` done and verified
   · `[-]` dropped, with the reason on the line.
2. Update `docs/plan/04-KNOWN-DEFECTS.md` if a defect was fixed, found, or changed severity.
3. Append to `docs/DECISIONS.md` if a decision was taken, naming its plan ID.
4. Update `docs/SESSION-STATE.md` at the end of a session.

Never renumber a plan ID. Only tick `[x]` on evidence you saw yourself — a test summary line
or a diff you read. A build report claiming success is not evidence; one such report on
2026-09-12 said GREEN over three real defects.

Name the plan ID in commit messages and status reports.

## How to run

Terminal 1: `$env:QUEUE_BACKEND = "inline"; .\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000`
Terminal 2: `cd web ; python -m http.server 8124`

`QUEUE_BACKEND` MUST be a shell variable, not an `.env` line. Without it, uploads sit
`QUEUED` forever and every screen looks empty.

Tests: `.\venv\Scripts\python.exe -m pytest -q`. The full suite takes 4-12 minutes, so run a
single file while iterating and the full suite once at the end. The repository target is
**Python 3.13.15**; recreate the existing `venv` with that interpreter before running the
suite locally. CI (`.github/workflows/ci.yml`), `runtime.txt`, and `.python-version` are
pinned to match.

OCR now installs from `requirements.txt` in one pass. `requirements-ocr.txt` and its two-step
dance are superseded: they existed because spacy 3.7.4 needed numpy<2 while the OCR chain
declares numpy>=2, and the 3.13 upgrade moved to spacy 3.8.7 on numpy 2.x.

## Conventions

- Enums: `class X(str, enum.Enum)`, stored as `Enum(X, native_enum=False, length=N)`.
- Services `db.add()` and `db.flush()`. **Routes commit.** No service commits itself.
- An audit event is written in the same unit of work as the change it records, through
  `record_audit` in `app/services/disposition_service.py`.
- An enum value never reaches a reader. Every user-facing string comes from a plain-words
  map, and there are tests enforcing it — including one that requires every `AuditAction`
  to appear as a label in `web/audit.html`.
- `DateTime` columns come back naive from SQLite. Normalise before comparing against an
  aware `datetime.now(timezone.utc)`.
- Current state is **stored, not derived on read**. `CandidateLifecycle` holds the operative
  row and is superseded rather than edited. Deriving "latest" from a timestamp invites a tie,
  and the tie-break is then arbitrary.

## Not yet configured

This repo has no `## Agent skills` block. Run `/setup-matt-pocock-skills` to add one when
there is time; until then the engineering skills fall back to local-markdown tickets.
