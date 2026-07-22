---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 27
subsystem: database
tags: [dynamodb, account-deletion, teacher-identity, cas, quiescence]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 21
    provides: versioned question takeover and deterministic teacher-session identity
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 25
    provides: strong cross-account teacher reference discovery and two-clean-epoch progression
provides:
  - exact CAS scrub of deleting-teacher references from retained student questions
  - strict teacher-session tombstones guarded by deletion generation and session identity
  - retry and late-write proof requiring two subsequent strong clean epochs
affects: [account-deletion-seal, teacher-takeover, V9DATA-02, CR-10]

tech-stack:
  added: []
  patterns: [cross-account reference CAS, closed non-authorizing state, strict session tombstone]

key-files:
  created:
    - tests/test_phase475_deletion_teacher_identity_scrub.py
  modified:
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/services/account_deletion_service.py

key-decisions:
  - "Teacher deletion resolves only questions whose current teacher or dispatch authority names that teacher; history-only cleanup preserves the existing question status and every unrelated teacher reference."
  - "Teacher-session cleanup binds the existing schema's positive question_version together with exact session, question, student, teacher, and takeover-claim coordinates before strict tombstone replacement."

patterns-established:
  - "Teacher question cleanup: exact key/entity/schema/owner/status/version CAS removes only reviewed teacher linkage and increments version once without replacing student content."
  - "Teacher deletion quiescence: any CAS loss or late matching row resets progress before two later strong clean epochs."

requirements-completed: [V9DATA-02]

duration: 13 min
completed: 2026-07-22
---

# Phase 475 Plan 27: Teacher Question And Session Identity Scrub Summary

**Teacher deletion now CAS-removes direct, dispatch, history, takeover, and session linkage from student-owned questions while retaining student content, and replaces teacher sessions with strict identity-fenced tombstones.**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-22T15:12:12Z
- **Completed:** 2026-07-22T15:25:06Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Extended the reviewed cross-account registry to discover exact current dispatch and prior-dispatch teacher references without recursive payload matching.
- Added a question CAS that binds exact PK/SK, entity/schema, student owner, status, positive version, and current/history teacher reference; it removes only teacher authority/session linkage and increments the version once.
- Closed teacher-dependent questions as `resolved` with dispatch `revoked`, while history-only scrubs preserve the existing status and retain other teachers in history.
- Added strict teacher-session tombstone replacement conditioned on exact session, question, student, teacher, takeover claim, and positive linked question version.
- Proved a real CAS loss, retained concurrent student data, refreshed cleanup, a late matching question, and two later strong clean epochs through the production branch.

## TDD Cycle

- **RED:** The production branch attempted owner-deletion tombstones for foreign-owned student questions and lacked teacher identity/version conditions.
- **GREEN:** Added entity-specific question/session cleanup and service routing; the target node and 95 related deletion/takeover regressions pass.
- **REFACTOR:** No separate refactor commit was needed; validation and transaction construction remained inside the existing deletion repository boundary.

## Task Commits

1. **RED: Add failing teacher identity scrub proof** - `520927b` (test)
2. **GREEN: Scrub teacher identity from retained questions** - `66ca07a` (feat)

## Files Created/Modified

- `tests/test_phase475_deletion_teacher_identity_scrub.py` - Real scan/transaction fake proving CAS loss, content preservation, session minimization, late discovery, and two clean epochs.
- `src/stoa/db/repositories/account_deletion_repo.py` - Reviewed history discovery plus exact teacher-question and teacher-session cleanup primitives.
- `src/stoa/services/account_deletion_service.py` - Owner deletion versus cross-account teacher-reference routing in the question/session branch.

## Decisions Made

- A current teacher or dispatch reference makes the question teacher-dependent and therefore closes it as `resolved`; removing a historical teacher alone does not alter the learning state.
- Current teacher/session/takeover fields are removed only when the deleting teacher owns that current linkage, so cleanup cannot erase a retained teacher's authority or session.
- The existing teacher-session schema has no independent row version; its positive `question_version` is bound with every persisted identity coordinate for the exact replacement CAS.
- Conditional loss is converted to row-conflict debt, forcing fresh strong discovery rather than allowing stale cleanup to overwrite concurrent state.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The restricted filesystem sandbox denied `.git/index.lock` for the RED commit; the same individually scoped test file was committed with approved repository permission. Normal hooks ran and were not bypassed.

## Verification

- Exact plan node: 1 passed.
- Teacher deletion, discovery, relationship/notification scrub, inherited owner deletion, deletion claim fencing, question CAS, takeover effect, dispatch, and reply/SLA regressions: 96 passed.
- Ruff over all three planned files: passed.
- `git diff --check` over all three planned files: passed.
- Acceptance criteria: no raw deleting teacher ID survives; student content/attachments/AI result and ownership remain byte-equivalent; no owner/session is created; CAS loss and a late row both reset progress before clean epochs 1 and 2.
- Commit isolation: both task commits exclude `README.md`, both seed/provision scripts, and both AWS operator identity paths.

## User Setup Required

None - no dependency, credential, schema migration, provider call, deployment, or external configuration is required.

## Known Stubs

None. Empty collections in the test and repository are bounded accumulators or deliberate clean-scan state, not runtime placeholders.

## Threat Flags

None. The only new cross-account mutation is the teacher-to-student trust boundary explicitly registered as T-475-27-01/T-475-27-02 and is protected by the planned exact CAS and content-preserving update.

## Next Phase Readiness

- CR-10 teacher question/session identity retention is locally closed without deleting student learning data or reopening takeover authority.
- Remaining Phase 475 gap plans can rely on retryable row debt and two strong clean epochs for deletion-seal completeness.

## Self-Check: PASSED

- All three planned source/test files and this summary exist.
- RED commit `520927b` precedes GREEN commit `66ca07a`; both exist with no tracked deletions.
- Exact plan verification, 96-test regression gate, Ruff, diff check, stub scan, threat-surface scan, and commit-isolation checks pass.
- The only remaining non-planning worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
