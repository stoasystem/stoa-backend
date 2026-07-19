---
phase: 474-deterministic-verification-and-gated-delivery
plan: 40
subsystem: database
tags: [python, mypy, dynamodb, privileged-identity, security-audit, typing]

requires:
  - phase: 474-09
    provides: object-valued shared DynamoDB table boundary and per-operation Protocol pattern
  - phase: 474-39
    provides: typed privileged reconciliation and authorization-audit collaborators
provides:
  - mypy-zero privileged teacher activation, administrator lifecycle, and security-audit repositories
  - explicit object-valued provider response validation at every DynamoDB operation boundary
  - preserved idempotent command, invitation claim, audit replay, and bounded probe semantics
affects: [474-mypy-closure, privileged-identity, teacher-activation, authorization-audit]

tech-stack:
  added: []
  patterns: [object-valued repository records, per-operation runtime protocols, stable fail-closed provider validation]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/teacher_application_repo.py
    - src/stoa/db/repositories/privileged_identity_repo.py
    - src/stoa/db/repositories/security_audit_repo.py

key-decisions:
  - "Privileged lifecycle repositories validate only the DynamoDB operation each path invokes and keep provider responses object-valued until string-keyed mapping checks pass."
  - "Malformed privileged and audit provider responses fail through stable repository exceptions without exposing coordinates or restoring broad typing."
  - "The unavailable authorization-audit sink retains its no-argument fail-closed diagnostic probe while accepting typed object-valued keyword inputs for production calls."

patterns-established:
  - "Privileged provider boundary: runtime-check the smallest get, put, query, or update Protocol before calling a table returned as object."
  - "Audit response boundary: validate mapping keys, bounded string collections, and nonnegative integer counters before replay or probe decisions."

requirements-completed: [V9QUAL-04]

duration: 7 min
completed: 2026-07-19
---

# Phase 474 Plan 40: Privileged Activation and Security-Audit Repository Typing Summary

**Teacher activation, administrator lifecycle, and authorization-audit repositories now use object-valued DynamoDB boundaries with operation-specific Protocols and explicit fail-closed provider narrowing.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-19T17:45:42Z
- **Completed:** 2026-07-19T17:52:18Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- Reduced the three-file focused mypy result from 14 diagnostics to zero without `Any`, casts, ignores, excludes, or missing-import suppression.
- Narrowed provider-returned mappings, items, collections, probe counters, and table capabilities before they influence privileged lifecycle or durable authorization evidence.
- Preserved invitation and command idempotency, conditional version conflicts, old-key audit replay, bounded probe aggregation, redaction, and fail-closed unavailable-sink behavior across 390 broader regressions.

## Task Commits

The task was committed atomically after its RED/GREEN verification cycle:

1. **Task 1 GREEN: type privileged activation and security-audit repositories** - `fc323ef` (fix)

The RED gate was the plan's existing focused mypy command, which reproduced 14 diagnostics before implementation. No new test file was added because the behavior under repair was the measured static boundary and the plan already named the reconciliation runtime regression suite.

## Files Created/Modified

- `src/stoa/db/repositories/teacher_application_repo.py` - Typed teacher application, review, invitation, claim, and activation-command records with minimal get/put/query/update table Protocols.
- `src/stoa/db/repositories/privileged_identity_repo.py` - Typed administrator lifecycle commands with validated command identity, provider mappings, and conditional update results.
- `src/stoa/db/repositories/security_audit_repo.py` - Typed audit sink contracts, provider responses, replay records, bounded probe state, safe scalar projection, and append-only writes.

## Decisions Made

- Kept the central `get_table()` result object-valued and narrowed it inside each repository so Plan 09's downstream diagnostics remain visible instead of being re-masked.
- Used separate runtime-checkable Protocols for each DynamoDB operation, preserving minimal test fakes and least-capability validation.
- Rejected malformed provider mappings, non-string keys and event-ID collections, and invalid counter/version shapes through stable redacted repository errors before using them in authority or evidence decisions.
- Kept the deliberately unavailable audit sink callable with no arguments so its existing fail-closed diagnostic contract remains stable.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored the unavailable audit sink's no-argument fail-closed probe**

- **Found during:** Task 1 broader authorization-audit regression verification
- **Issue:** The first explicit method signature raised Python's missing-argument `TypeError` before the sink could emit the stable `authorization_audit_key_unavailable` error.
- **Fix:** Accepted typed `**kwargs: object` on the unavailable sink while retaining the Protocol-compatible return types and unconditional stable exception.
- **Files modified:** `src/stoa/db/repositories/security_audit_repo.py`
- **Verification:** The previously failing audit test and the complete 390-test privileged lifecycle/audit matrix pass.
- **Committed in:** `fc323ef`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** The fix preserves an existing fail-closed compatibility contract and adds no scope or authority.

## Issues Encountered

- The managed filesystem denied `.git/index.lock` creation for the first staging attempt. The exact three-file stage and commit were rerun with approved repository permission; no hook, reset, stash, clean, or unrelated path was used.
- The canonical full-repository mypy command remains red with 595 diagnostics in 85 non-target files. None are in the three Plan 40 repositories, and no residual was suppressed or treated as passing.
- Broader tests report existing Starlette and Mangum deprecation warnings; all 390 selected tests pass and the warnings are outside this plan's repository scope.

## Known Stubs

None. Empty mappings are bounded provider-response accumulators, and optional `None` values are explicit absent-item, optional-key, or conditional-expression states rather than placeholder behavior.

## User Setup Required

None - no external service configuration required.

## Verification

- RED: focused mypy reproduced 14 diagnostics across all three target repositories.
- Plan command: focused mypy passed with no issues; the named reconciliation suite passed 47 tests; focused Ruff passed.
- Focused lifecycle/audit regression: 115 tests passed after the compatibility correction.
- Broader privileged lifecycle/audit regression: 390 tests passed across administrator authorization, reconciliation, student policy, authorization audit, Phase 473 practice authorization, route inventory, identity authorization, teacher onboarding, and public identity lifecycle.
- Canonical repository-wide measurement: 595 diagnostics remain in 85 non-target files; Plan 40 target diagnostics are zero.
- Suppression scan found no `Any`, `cast(`, `type: ignore`, `follow_imports=skip`, `ignore_missing_imports`, skip, or xfail in the three targets.
- `git diff --check` passed; the task commit contains no tracked-file deletions and the backend was clean afterward.
- Stub and threat-surface scans passed. No endpoint, authentication path, provider call, file-access boundary, schema, dependency, or production authority was introduced.
- Production infrastructure, deployment, smoke, and rollback remained exact `NOT RUN`.

## Next Phase Readiness

- Later mypy split plans can consume the object-valued table boundary without reintroducing masking types.
- The repository-wide mypy gate remains release-blocking until the remaining declared coherent domains reach zero.
- Plan 474-26 remains intentionally incomplete: no summary was created, and its infrastructure quarantine was not read or modified.

## Self-Check: PASSED

- All three declared target files and this summary exist.
- Task commit `fc323ef` exists and contains no tracked-file deletions.
- Focused mypy, named and broader runtime regressions, Ruff, suppression, diff, stub, and threat-surface scans passed.
- Phase summary count is 13 of 80; Plan 474-26 remains incomplete and has no summary.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
