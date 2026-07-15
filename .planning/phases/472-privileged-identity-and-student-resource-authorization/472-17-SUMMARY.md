---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 17
subsystem: auth
tags: [public-identity, cognito, account-recovery, authorization]
requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: immutable public identity commands and deny-first activation convergence
provides:
  - proof-bound existing-account registration resume
  - command-user-only verification resend selection
  - adversarial adoption and resend regression matrix
affects: [public-auth, account-verification, phase-478-clients]
tech-stack:
  added: []
  patterns:
    - immutable command before provider lookup or identity mutation
    - command user id as the sole local resend identity key
key-files:
  created: []
  modified:
    - src/stoa/routers/auth.py
    - src/stoa/services/public_identity_service.py
    - tests/test_public_identity_lifecycle.py
    - tests/test_auth_account_lifecycle.py
    - tests/test_auth_security.py
key-decisions:
  - "Existing-account registration returns one safe recovery action unless issuer, subject, user ID, role, and immutable command match exactly."
  - "Verification resend never selects authority through the email index and reports active only after command-aware reconciliation completes."
patterns-established:
  - "Proof before lookup: load and validate the immutable public command before reading an existing provider subject."
  - "Deny-first recovery: partial or mismatched convergence never produces an active public profile."
requirements-completed: [V9AUTH-04]
duration: 8 min
completed: 2026-07-15
---

# Phase 472 Plan 17: Proof-bound Public Identity Resume and Resend Convergence Summary

**Existing provider accounts can resume only their exact immutable public command, while resend converges exclusively through the command-owned subject and profile.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-15T15:46:27Z
- **Completed:** 2026-07-15T15:54:25Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments

- Moved the `UsernameExistsException` path behind an immutable-command precondition and exact issuer/subject/user/role proof.
- Added a resume-only service path that cannot create the first command and prevents unproved relationship, profile, binding, or group mutation.
- Removed email-GSI identity selection from resend and routed already-confirmed recovery through full command-aware reconciliation.
- Added endpoint and service adversarial controls for provider-only, privileged, altered-role, altered-subject, duplicate-email, partial, and dependency cases, with positive student and parent controls.

## Task Commits

1. **Task 1: Require immutable command proof before existing-account registration resume** - `e362967` (fix)
2. **Task 2: Converge verification resend through the command subject** - `4869d03` (fix)
3. **Task 3: Prove zero-mutation adoption defense and legitimate recovery controls** - `eaa0caf` (test)

## Files Created/Modified

- `src/stoa/routers/auth.py` - Enforces command-first registration resume and command-owned resend convergence.
- `src/stoa/services/public_identity_service.py` - Provides resume-only registration and command-user profile loading boundaries.
- `tests/test_public_identity_lifecycle.py` - Proves fingerprint mismatches fail before profile or authority mutation.
- `tests/test_auth_account_lifecycle.py` - Exercises HTTP adoption/resend matrices and legitimate recovery controls.
- `tests/test_auth_security.py` - Guards canonical active role vocabulary in the public identity runtime.

## Decisions Made

- Existing-account mismatch cases intentionally share `email_already_registered` status, code, keys, and actionable message so provider privilege and command existence remain undisclosed.
- A command repository outage remains a retryable dependency response, while a missing command receives the bounded accepted resend projection without provider access.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Legacy route tests selected profiles by email inside their service adapter; the adapter now exposes the command-profile boundary while production code uses only `command.user_id`.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 1 focused gate: 2 passed, 83 deselected.
- Task 2 focused gate: 21 passed, 27 deselected.
- Complete public identity, account lifecycle, and auth security gate: 85 passed.
- Runtime vocabulary scan found no alternate teacher-role term in the public identity implementation.
- All tests use injected local collaborators; no AWS, network, provider sandbox, or production mutation ran.

## Next Phase Readiness

- CR-01 and WR-03 are closed locally with executable zero-mutation and positive recovery evidence.
- Phase 474 Settings fixtures and Phase 475 teacher takeover atomicity remain unchanged and deferred to their owning phases.
- Ready for Plan 472-18.

## Self-Check: PASSED

- All five modified source/test files exist.
- All three task commits are present in git history.
- Every task acceptance criterion and the plan-level verification command pass.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
