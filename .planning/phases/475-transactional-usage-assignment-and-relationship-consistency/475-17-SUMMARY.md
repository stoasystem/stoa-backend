---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 17
subsystem: database
tags: [dynamodb, cas, state-machine, concurrency, teacher-takeover]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 15
    provides: opaque question command coordinates and versioned question admission
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 04
    provides: atomic teacher takeover and deterministic session primitive
provides:
  - typed owner/status/version CAS boundary for every ordinary question writer
  - explicit legacy question-version initialization behind the active account fence
  - closed production writer registry and AI/takeover commit-order race proofs
affects: [475-18-provider-recovery, 475-21-teacher-fence, V9DATA-01, V9DATA-02, CR-03]

tech-stack:
  added: []
  patterns: [observed-snapshot CAS, closed source-state sets, strong-reread disposition classification]

key-files:
  created:
    - tests/test_phase475_question_state_cas.py
  modified:
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/routers/questions.py
    - src/stoa/routers/teachers.py
    - src/stoa/services/teacher_dispatch_service.py
    - tests/test_questions.py
    - tests/test_teacher_dispatch.py
    - tests/test_teacher_reply_sla.py

key-decisions:
  - "Every ordinary writer supplies its observed question snapshot plus a code-level closed allowed-source set; the repository conditions on the exact observed source status and positive version and increments once."
  - "Legacy rows cross a separate attribute-not-exists(version) initialization transaction before their first ordinary mutation, while newly admitted questions start at version 1."
  - "A failed/unknown transaction is classified by a strong reread; only an exact N+1 target state with all requested fields is APPLIED, while later versions are STALE without exposing the winning coordinates."

patterns-established:
  - "Question writer CAS: active student fence + exact owner + exact observed status + exact observed version + one next-version write."
  - "Closed writer inventory: AST discovery rejects legacy repository calls and any direct question Update outside reviewed CAS/takeover/reconciliation primitives."

requirements-completed: [V9DATA-01, V9DATA-02]

duration: 18 min
completed: 2026-07-22
---

# Phase 475 Plan 17: Question State/Version CAS Summary

**All OCR, AI, escalation, dispatch, feedback, teacher reply, and resolve writes now lose safely against newer question state through one owner/status/version CAS boundary, preserving a committed teacher takeover and session.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-22T10:02:44Z
- **Completed:** 2026-07-22T10:21:17Z
- **Tasks:** 1
- **Files modified:** 8

## Accomplishments

- Added `QuestionMutationDisposition` and `QuestionMutationResult` with `APPLIED`, `STALE`, `INVALID_TRANSITION`, and `RETRYABLE` outcomes.
- Added a single ordinary mutation transaction containing the active student fence, exact question identity/owner/status/version conditions, protected-field rejection, and one version increment.
- Added explicit state-constrained initialization for legacy unversioned questions and started every new question at version 1.
- Migrated OCR enrichment, AI completion, student escalation, no-candidate/claim/timeout dispatch, feedback, teacher reply, and resolve to caller-observed snapshots and closed transition sets.
- Proved takeover-first rejects stale AI/metadata work, while AI-first permits refreshed escalation and takeover without losing the answer.
- Sealed the production writer inventory with AST discovery across all backend Python sources.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing question state CAS proofs** - `923561a` (test)
2. **GREEN: Fence all question writers with state CAS** - `54160f5` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_repo.py` - Typed mutation result, exact owner/status/version CAS transaction, strong-reread classification, and explicit legacy initialization.
- `src/stoa/routers/questions.py` - Versioned admission plus OCR, AI, escalation, and feedback CAS callers.
- `src/stoa/routers/teachers.py` - Teacher reply and resolve CAS callers with stale-state conflict projection.
- `src/stoa/services/teacher_dispatch_service.py` - Versioned no-candidate, dispatch claim, timeout, and reassignment mutations.
- `tests/test_phase475_question_state_cas.py` - Transaction-shape, legacy initialization, invalid transition, stale metadata, writer registry, and two takeover/AI ordering proofs.
- `tests/test_questions.py` - Question escalation regression fixture migrated to typed CAS results.
- `tests/test_teacher_dispatch.py` - Dispatch regression fixtures migrated to versioned snapshots and typed CAS results.
- `tests/test_teacher_reply_sla.py` - Escalation/reply/SLA fixtures migrated to versioned snapshots and typed CAS results.

## Decisions Made

- Exact observed status is always part of the DynamoDB condition even when a caller's closed transition set admits multiple source states; a later allowed state cannot make a stale snapshot replay.
- Identity, owner, status, and version are protected from `extra_attrs`, so metadata writers cannot smuggle an ownership or lifecycle replacement through the shared boundary.
- Commit-before-timeout reconciliation recognizes success only when the strong reread contains version N+1, the requested target status, and every requested field value.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migrated inherited regression fixtures to the typed CAS seam**
- **Found during:** Task 1 GREEN verification
- **Issue:** Existing dispatch, question, and SLA tests monkeypatched the retired `update_status`/`update_status_conditionally` calls and supplied legacy snapshots without a version, so they could not exercise the migrated production paths.
- **Fix:** Updated only the directly affected fixtures to provide versioned snapshots and return typed applied/stale mutation results.
- **Files modified:** `tests/test_questions.py`, `tests/test_teacher_dispatch.py`, `tests/test_teacher_reply_sla.py`
- **Verification:** The exact plan gate passes 31 tests; the necessary wider question/replay/reconciliation/deletion gate passes 70 tests; Ruff passes all modified files.
- **Committed in:** `54160f5`

---

**Total deviations:** 1 auto-fixed (1 blocking regression-fixture migration).
**Impact on plan:** Test-only compatibility updates preserve existing assertions while routing them through the planned CAS contract; no feature or architectural scope was added.

## Issues Encountered

- The sandbox denied normal `.git/index.lock` creation. Individually scoped files were staged and committed with approved repository permission; normal hooks ran and no verification was bypassed.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_question_state_cas.py tests/test_phase475_teacher_takeover.py tests/test_teacher_dispatch.py tests/test_teacher_reply_sla.py` - 31 passed.
- `.venv/bin/python -m pytest -q tests/test_questions.py tests/test_phase475_question_replay.py tests/test_phase475_question_reconciliation.py tests/test_phase473_account_deletion.py` - 70 passed.
- `.venv/bin/ruff check src/stoa/db/repositories/question_repo.py src/stoa/routers/questions.py src/stoa/routers/teachers.py src/stoa/services/teacher_dispatch_service.py tests/test_phase475_question_state_cas.py` - passed.
- Production source scan - zero `question_repo.update_status` or `question_repo.update_status_conditionally` calls remain in question, teacher, or dispatch production paths.
- Commit isolation scan - only the eight plan/compatibility files appear in RED/GREEN commits; all five user-owned parallel paths remain untracked or unstaged.

## User Setup Required

None - no dependency, credential, migration, service, or deployment change is required.

## Known Stubs

None. Stub-pattern matches are test containers, optional type defaults, and existing safe runtime fallbacks; none flow as a new placeholder result.

## Next Phase Readiness

- CR-03 is closed: ordinary question writers cannot overwrite a newer takeover, recovery, or lifecycle transition.
- Plan 475-18 can layer durable provider-effect recovery on the shared versioned question boundary.
- Plan 475-21 can add the teacher lifecycle fence to the existing takeover transaction without reopening ordinary writer consistency.

## Self-Check: PASSED

- All four production files, the new CAS proof, and this summary exist.
- RED commit `923561a` precedes GREEN commit `54160f5`; both exist with no tracked deletions.
- Exact plan verification, the 70-test wider regression, Ruff, source registry, stub scan, commit isolation, and `git diff --check` pass.
- The only remaining non-planning worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
