---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 19
subsystem: database
tags: [dynamodb, idempotency, replay, ownership, integrity]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 18
    provides: durable versioned question commands and provider-effect recovery
provides:
  - one strong-read question replay classifier bound to command, active fence, and question
  - redacted denial of corrupt, stale, legacy, or cross-student replay coordinates
  - authoritative payload-mismatch handling without private question projection
affects: [475-question-reconciliation, 478-question-processing, V9DATA-01, CR-02]

tech-stack:
  added: []
  patterns: [strong-read replay classification, owner-bound private projection, closed status compatibility]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/routers/questions.py
    - tests/test_phase475_question_replay.py
    - tests/test_questions.py

key-decisions:
  - "Payload mismatch is returned only after the command key, schema, digest, owner, version, generation, status, and current active fence establish command authority."
  - "Exact replay requires a question.v1 row whose key, identity, owner, generation, positive version, and status are compatible with the durable command."
  - "Route preflight, attachment races, admission contention, effect refresh, and final persisted projection all consume the same strict replay classifier."

patterns-established:
  - "Strict replay: strong command read -> exact active generation fence -> strong question read -> owner-bound projection."
  - "Replay denial: corrupt, foreign, stale, or missing dependencies collapse to one coordinate-free retry response."

requirements-completed: [V9DATA-01]

duration: 13 min
completed: 2026-07-22
---

# Phase 475 Plan 19: Strict Owner-Bound Question Replay Summary

**Question replay now projects private content only after one repository classifier proves the durable command, current account fence, and strongly loaded question belong to the same student and generation.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-22T14:58:08Z
- **Completed:** 2026-07-22T15:10:53Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added `classify_question_submission_replay(...)` with exact command PK/SK, entity/schema, opaque digest, fingerprint, owner, allowed state, positive version, question identity, and account-generation validation.
- Strongly loaded the current account fence and question before RESUME, then required exact question key, schema, identity, owner, generation, positive version, and command-compatible status.
- Routed preflight, attachment-reservation races, admission contention rereads, effect recovery refreshes, and persisted result projection through the strict classifier.
- Added a foreign/corrupt/legacy/generation/status matrix plus processing, completed, later-resolved, and authoritative mismatch positive controls.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing strict question replay matrix** - `66d672a` (test)
2. **GREEN: Enforce strict owner-bound question replay** - `67703b6` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Strong replay classifier, question schema/status compatibility, strict contention reread, and canonical question metadata persistence.
- `src/stoa/routers/questions.py` - Unified replay entry use and removal of command-coordinate direct question projection.
- `tests/test_phase475_question_replay.py` - Strong-read integrity/ownership denial matrix and exact replay controls.
- `tests/test_questions.py` - Production-shaped command/fence fixtures for the stricter replay contract.

## Decisions Made

- Changed payload remains the existing safe 409 only when the command itself is fully authoritative and current; the question is not loaded or exposed for that outcome.
- Processing commands accept only pending questions; completed commands accept AI-answered or later teacher/resolution states; terminal failure accepts only submission-failed questions.
- New admission transactions stamp canonical `question` / `question.v1` metadata and a positive version so future strict replay does not depend on inferred schema.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated inherited route fixtures for the strict durable command contract**
- **Found during:** Task 1 GREEN regression verification
- **Issue:** Two inherited route tests supplied command rows without PK/SK, generation, version, or an active-fence observation, so their intended authoritative mismatch scenarios became correctly unavailable.
- **Fix:** Updated the shared test command helper and fence stub to use the production-shaped strict contract.
- **Files modified:** `tests/test_questions.py`
- **Verification:** The necessary admission, effect, state-CAS, reconciliation, and route regression gate passes 61 tests.
- **Committed in:** `67703b6`

---

**Total deviations:** 1 auto-fixed (1 blocking fixture migration).
**Impact on plan:** Test-only compatibility preserves existing behavior coverage on the new strict boundary; no feature or architectural scope was added.

## Issues Encountered

- Normal Git staging required repository approval because the sandbox denied `.git/index.lock`; normal hooks were retained.
- The local formatter proposed unrelated whole-file reflow, so those uncommitted changes were precisely discarded and the logical GREEN patch was replayed without formatter churn.

## Verification

- Exact plan gate: 27 selected replay/foreign/owner/schema/generation/mismatch tests passed; Ruff passed all planned files.
- Necessary regression gate: 61 tests passed across admission, effect recovery, question state CAS, reconciliation, and route behavior.
- Acceptance criteria: strict command/fence/question validation, exact processing/completed replay, foreign-content denial, and authoritative changed-payload 409 all PASS.
- `git diff --check`: passed.

## User Setup Required

None - no dependency, credential, schema deployment, external service, or provider execution is required.

## Known Stubs

None. Empty collections and optional values in the touched paths are bounded runtime defaults or test effect collectors, not placeholder replay results.

## Next Phase Readiness

- CR-02 is locally closed: stored question coordinates cannot bypass current owner/generation/schema validation before private projection.
- Plan 475-20 can build terminal failure and compensation behavior on one authoritative replay boundary.
- No provider, production, or external-system claim was made.

## Self-Check: PASSED

- All four implementation/test files and this summary exist.
- RED commit `66d672a` precedes GREEN commit `67703b6`; both exist and contain only plan-owned files.
- Exact plan verification, necessary regression, Ruff, stub scan, deletion scan, diff check, and commit isolation all pass.
- The only remaining non-planning worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
