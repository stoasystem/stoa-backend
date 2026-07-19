---
phase: 474-deterministic-verification-and-gated-delivery
plan: 08
subsystem: database
tags: [python, mypy, dynamodb, identity, capability, typing]

requires:
  - phase: 474-07
    provides: object-valued identity and authorization boundary narrowing pattern
provides:
  - mypy-zero identity, capability, public-identity, and user repository domain
  - closed capability transaction operation records and narrow DynamoDB protocols
  - explicit validation of provider-originated public identity and capability state
affects: [474-mypy-closure, authentication, authorization, account-lifecycle]

tech-stack:
  added: []
  patterns: [object-valued repository records, closed TypedDict operations, runtime-checkable provider protocols]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/capability_repo.py
    - src/stoa/db/repositories/public_identity_repo.py
    - src/stoa/db/repositories/identity_repo.py
    - src/stoa/db/repositories/user_repo.py

key-decisions:
  - "DynamoDB records remain object-valued until exact text, boolean, integer, mapping, and fingerprint checks establish safe use."
  - "Capability transaction variants use a closed TypedDict union while fake and boto-backed tables cross narrow runtime-checkable Protocol boundaries."
  - "Malformed durable identity and capability state fails closed with stable coordinate-free repository errors instead of coercion."

patterns-established:
  - "Repository boundary pattern: copy only string-keyed mappings and narrow authority-bearing members before use."
  - "Provider adapter pattern: runtime-check the smallest query, get, transaction, and metadata protocols without casts or broad Any."

requirements-completed: [V9QUAL-04]

duration: 16 min
completed: 2026-07-19
---

# Phase 474 Plan 08: Identity, Capability, and User Repository Typing Summary

**Identity, capability, public-identity, and user repositories now pass focused mypy without `Any`, casts, ignores, or changes to authorization, fence, idempotency, pagination, privacy, and stable-error behavior.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-19T16:47:57Z
- **Completed:** 2026-07-19T17:04:18Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Reduced the plan's focused mypy result from five diagnostics in two files to zero diagnostics across all four declared repository files.
- Replaced broad and bare collection types with object-valued repository records, closed capability transaction operations, and narrow runtime-checkable DynamoDB boundaries.
- Added explicit fail-closed narrowing for string-keyed provider mappings, identity fingerprints, booleans, DynamoDB integer/Decimal versions, account-fence generations, timestamps, and capability lineage fields.
- Preserved immutable public identity commands, exact capability replay/revocation, current-grant filtering, parent/student bindings, account deletion fences, pagination, and stable coordinate-free errors across 186 lifecycle regressions.

## Task Commits

The task was committed atomically after its RED/GREEN verification cycle:

1. **Task 1 GREEN: type identity, capability, and user repositories** - `7ce6cc3` (fix)

The RED gate was the plan's existing focused mypy command, which reproduced five diagnostics before implementation. As in Plan 474-07, no new test file was added because the plan fixes a measured static-typing boundary and declares an exact four-source-file scope.

## Files Created/Modified

- `src/stoa/db/repositories/capability_repo.py` - Object-valued capability records, closed transaction variants, narrow fake/DynamoDB protocols, and validated lineage/version/timestamp parsing.
- `src/stoa/db/repositories/public_identity_repo.py` - Explicit command reconstruction with boolean/integer narrowing and durable email/fingerprint integrity checks.
- `src/stoa/db/repositories/identity_repo.py` - String-keyed identity records and explicitly narrowed binding/inventory/account adapters.
- `src/stoa/db/repositories/user_repo.py` - Typed profile/binding operations, provider response normalization, and positive account-fence generation validation.

## Decisions Made

- Kept provider-returned records as `dict[str, object]` rather than claiming trusted field types before runtime validation.
- Used a discriminated `TypedDict` union for capability condition/put operations so transaction branches are closed without changing the fake-table contract.
- Preserved DynamoDB `Decimal` compatibility while rejecting booleans, fractional values, missing authority versions, non-string keys, and coerced identity fields.
- Revalidated public identity email digests and command fingerprints when reading durable state so corrupted records cannot become an authority source.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The managed filesystem denied `.git/index.lock` creation during the first staging attempt. The same narrow four-file Git operation was rerun with the approved repository permission; no hook was bypassed and no reset, stash, clean, or unrelated path was used.
- The exact repository-wide mypy command remains release-red outside this plan at 372 errors in 72 files. The four Plan 474-08 targets have zero diagnostics; stricter object-valued results expose downstream consumer errors previously hidden by broad repository types, which remain assigned to later coherent typing plans rather than being suppressed or fixed out of scope.
- The broader runtime gate reports one existing Starlette test-client deprecation warning. All 186 tests pass and the warning is outside this plan's four-file scope.

## Known Stubs

None. Empty dictionaries/lists are bounded parsing, transaction-building, or pagination accumulators; optional `None` parameters are explicit transition/query outcomes; empty timestamp defaults preserve the durable command data model and do not feed UI placeholders.

## User Setup Required

None - no external service configuration required.

## Verification

- RED: focused mypy reproduced 5 errors in 2 files before implementation.
- Plan command: focused mypy passed with no issues in all 4 source files; 38 named identity authorization/public identity lifecycle tests passed; focused Ruff passed.
- Broader identity/capability/account-fence regression: 186 tests passed across identity authorization, public identity lifecycle, privileged identity reconciliation, Phase 473 account deletion, auth account lifecycle, and auth security.
- Exact full scope: 229 source files checked; no diagnostics remain in the four Plan 474-08 targets. The remaining 372 diagnostics in 72 downstream files stay release-blocking for subsequent typing plans.
- Suppression scan found no `Any`, `cast(`, `type: ignore`, mypy weakening, skip, or xfail in the four target files.
- `git diff --check` passed; task commit contains no deletions; backend was clean after the task commit.
- Production infrastructure, deployment, smoke, and rollback remained exact `NOT RUN`.

## Next Phase Readiness

- Plan 474-09 and later typing domains can consume the explicit object-valued repository contracts and repair newly visible caller narrowing without reintroducing broad types.
- Plan 474-26 remains intentionally incomplete: no summary was created, its Linux ARM64 boot-smoke issue was skipped by owner direction, and its infra quarantine was not modified.

## Self-Check: PASSED

- All four declared target files and this summary exist.
- Task commit `7ce6cc3` exists and contains no tracked-file deletions.
- Task acceptance, plan verification, broader lifecycle regression, suppression scan, stub scan, diff check, and threat-surface scan passed.
- No endpoint, authentication mechanism, provider call, file-access boundary, schema, dependency, or production operation was introduced.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
