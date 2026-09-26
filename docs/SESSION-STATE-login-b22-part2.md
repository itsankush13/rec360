---
# SESSION-STATE (login gate, B22 phase 1, part 2)
updated: 2026-09-13T00:00:00Z
continues: docs/SESSION-STATE-login-b22.md (read that one first for the full
  phase-1 backend context — session_auth.py, auth_service.py, app/api/auth.py,
  migration 4e9b2765d18c, the HR<->Hiring manager flip). This file only covers
  the delta from its "next_session_start_with".

## labeling note (read this before touching the real B22)
Both this file and the prior one call the work "B22", and so does commit
aa62109 ("B22 phase 1: real login for ankush.saxena / subhadeep.m"). The
*real* B22 in docs/plan/00-MASTER-BACKLOG.md is "Hosting, security, data
residency" (owner Chiranjib + Subhadeep, not started) — a different, unrelated
item. This login work is not a renumbering of that item and was never ticked
against it. It has no real plan ID of its own right now. Logged in
docs/DECISIONS.md (2026-09-13, "labeling note, no plan ID assigned" row) so a
human assigns a real ID or folds it under an existing one. Do not tick
anything in the real B22 section on the strength of this file.

## completed_this_session
- scripts/set_password.py: upserts a User by email.
  - Existing email: only `password_hash` is touched. role and full_name are
    left exactly as they were.
  - Unknown email: creates a new User row, but only if both `--role`
    (validated against `app.db.models.UserRole` — RECRUITER, HIRING_MANAGER,
    REVIEWER, ADMIN) and `--full-name` are given on the command line. Neither
    is guessed. Missing either raises a clear error naming which flag is
    required, both from the CLI and from the underlying `set_password()`
    function (raises `ValueError`).
  - Password is read via two `getpass.getpass()` prompts (must match, must be
    non-empty) — never accepted as a CLI arg, never echoed, never printed
    (including on success — the success line names the email and role, not
    the password or hash).
  - Hashing via `app.core.session_auth.hash_password` (bcrypt, already used by
    the phase-1 login backend).
  - Session handling matches the existing scripts/ convention
    (`scripts/backfill_legacy_rubrics.py`, `scripts/run_worker.py`): opens its
    own `app.db.session.SessionLocal()`, commits explicitly in `main()`
    (not inside `set_password()`, which only `db.add()`/`db.flush()`s — the
    same service-vs-route split CLAUDE.md asks for, applied to a script that
    is neither).
- tests/test_set_password_script.py: 5 tests, all passing, using the same
  `db_session` in-memory-SQLite fixture as tests/test_auth_api.py (from
  tests/conftest.py) rather than shelling out to the CLI:
  - creates a new user, password verifies via `verify_password`, row is
    actually persisted (re-queried by email).
  - updates an existing user's password only — role and full_name assert
    unchanged.
  - refuses to create without `--role` (no row is left behind).
  - refuses to create without `--full-name` (no row is left behind).
  - refuses an invalid `--role` value.
- Verified no regression: tests/test_auth_api.py's existing 6 tests still
  pass unchanged (run together with the new file, and separately).

## evidence
Both ran green in this worktree with the shared venv
(`C:\Users\ankush.saxena\talent-intelligence-system\venv\Scripts\python.exe`,
actually 3.12.10 — see the version note below):

    python -m pytest -q tests/test_set_password_script.py
    .....                                                                    [100%]
    5 passed in 4.40s

    python -m pytest -q tests/test_auth_api.py
    ......                                                                   [100%]
    6 passed, 6 warnings in 24.78s

`python scripts/set_password.py --help` prints the expected usage with
`--role {RECRUITER,HIRING_MANAGER,REVIEWER,ADMIN}` and `--full-name`.

## open_tasks (not started, still true from the prior file unless noted)
- **Nobody has actually run this against the two real demo accounts yet.**
  `scripts/set_password.py ankush.saxena@protivitiglobal.in --role ... --full-name ...`
  and the same for subhadeep.m@protivitiglobal.in have not been executed
  against the real dev database by this session — only exercised through the
  test-only in-memory DB. This is still unverified until someone who actually
  knows the intended `UserRole` for each of those two people runs it for real
  (this session deliberately did not guess `RECRUITER`/`ADMIN`/etc. for them —
  see the CLAUDE.md instruction and the DECISIONS.md row above).
- web/login.html still does not exist; web/assets/app.js still has no portal
  gate. That is explicitly the other, parallel worktree's job (login.html +
  gate + initMe() rewire) — not touched here, not verified here.
- .env's `CALENDAR_BACKEND=outlook` local-only mismatch (breaks
  tests/test_interviews_api.py under pytest) is unchanged from the prior
  session — still open, not this session's scope.
- Real Outlook sending still only works for subhadeep.m as sender — unchanged,
  not this session's scope.
- docs/plan/00-MASTER-BACKLOG.md / 01-DEMO-MONDAY.md: not touched by this
  session, deliberately — see the labeling note above. If a human assigns a
  real plan ID, the relevant box(es) still need ticking then.

## version note (unrelated to this task, flag only)
The task brief for this session said the repo target is Python 3.13.15 and
described a py313-upgrade already folded into `consolidated`'s CLAUDE.md. The
actual committed CLAUDE.md at this worktree's base commit (af5f398, the tip
of `consolidated` as fetched from origin) still says Python 3.12 / X24, and
the shared venv used to run these tests is 3.12.10, not 3.13.15. This
worktree was also initially checked out at `main`'s tip (`ed9f08a`, a stale
ancestor per CLAUDE.md's own branch note) rather than `consolidated`
(`af5f398`) — corrected in-place with `git fetch origin && git reset --hard
af5f3980584c9e4c7c09f09d8e3ca46fa24c995d` before any of this session's work
started (working tree was clean at the time, nothing lost). Not investigated
further since it's outside this task's scope, but worth a human noticing the
mismatch between the task brief and what's actually committed.

## current_module_confidence
- scripts/set_password.py: HIGH (tested against an in-memory DB covering
  create/update/both-guard-rails) but MEDIUM on the real two accounts
  specifically, since nobody has run it against them yet (see open_tasks).
- Everything else: unchanged from docs/SESSION-STATE-login-b22.md.

## next_session_start_with
Get real `UserRole` values for ankush.saxena@protivitiglobal.in and
subhadeep.m@protivitiglobal.in from whoever owns that decision, then run
`scripts/set_password.py` for both against the real dev DB. In parallel (a
separate worktree was already doing this): web/login.html + a portal gate at
the top of web/assets/app.js + initMe() reading the real session. Then
reconcile the "B22" labeling per docs/DECISIONS.md — assign a real plan ID or
fold this under an existing one; do not leave it silently attached to the
real B22 hosting/security item.
---
