---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 14
subsystem: billing-entitlements
tags: [free-trial, dynamodb, profile-cas, auth, admission]

requires:
  - phase: 476-04
    provides: Historical activation-evidence classification and fail-closed migration review
  - phase: 476-13
    provides: Monotonic paid-to-free lifecycle transitions and canonical entitlement projection
provides:
  - Immutable first-student-activation timestamp and exact 14-day trial expiry behind account/profile CAS
  - Active, expired, and migration-review trial projection with stable choose-paid-plan action
  - Separate new-use admission and preserved account/history/parent read projection
affects: [auth-activation, effective-entitlements, ai-admission, teacher-support, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Trusted activation evidence is persisted once behind active account fence and profile-version CAS
    - Entitlement reads project trial state but never initialize or rewrite missing evidence

key-files:
  created:
    - src/stoa/services/free_trial_service.py
    - tests/test_free_trial_window.py
  modified:
    - src/stoa/services/entitlement_service.py
    - src/stoa/routers/auth.py

key-decisions:
  - "Derive first_student_activation_at from the already-persisted email verification activation timestamp, never from request-time entitlement reads or replay clocks."
  - "Treat missing, partial, malformed, or explicitly review-required historical evidence as migration_review_required and deny only new governed usage."
  - "Keep paid-plan admission independent of the historical free-trial window while retaining the immutable trial evidence for later paid-to-free fallback."

patterns-established:
  - "Activation replay: first confirmation and exact confirmation replay call the same conditional primitive and return the committed timestamp pair."
  - "Trial boundary: observed_at < expires_at is active; equality and every later instant are expired."

requirements-completed: [V9BILL-04]

duration: 7min
completed: 2026-07-24
---

# Phase 476 Plan 14: Immutable Free Trial Window Summary

**Student activation now seals one evidence-derived 14-day trial window, fails historical ambiguity closed, and expires only new AI/teacher-support admission while preserving account and learning-history reads.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-24T14:45:35Z
- **Completed:** 2026-07-24T14:52:34Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added `FreeTrialState`, `activate_student_free_trial()`, `get_free_trial_state()`, and `free_trial_allows_new_usage()` with strict aware-UTC validation and an exact 14-day boundary.
- Bound first and replayed student email-confirmation activation to one profile update conditioned on the active permanent account fence, student/active profile facts, profile version, and absence of every trial field.
- Projected active, expired, and `migration_review_required` state through effective entitlements with stable `choose_paid_plan`, explicit new-use admission, and unchanged account/history/parent read availability.
- Proved that concurrent activations write one timestamp pair, later profile/relationship/plan changes preserve its exact stored bytes, and entitlement reads never default missing evidence to the current time.

## Task Commits

TDD execution produced the mandatory RED and GREEN gates:

1. **Task 476-14-01 RED: Add failing immutable trial contract** - `9a7e444` (test)
2. **Task 476-14-01 GREEN: Enforce immutable free trial window** - `dafcff8` (feat)

## Files Created/Modified

- `src/stoa/services/free_trial_service.py` - Immutable activation CAS, strict evidence parser, exact trial-state projection, and new-use admission predicate.
- `tests/test_free_trial_window.py` - Race, replay/no-reset, exact expiry, historical fail-closed, preserved reads, mutation-denial, and source-link selectors.
- `src/stoa/services/entitlement_service.py` - Free-trial state, admission/action, and preserved read-access projection.
- `src/stoa/routers/auth.py` - Exact successful student confirmation and confirmation-replay calls into the immutable activation primitive.

## Decisions Made

- Used `email_verified_at` written by the successful public-identity activation as the trusted start evidence. This keeps first completion and replay byte-stable and prevents request-time trial renewal.
- Kept trial initialization out of login, locale/profile updates, relationship repair, entitlement reads, and paid lifecycle services; only the existing confirmation activation boundary calls the writer.
- Represented malformed or missing evidence without inferred timestamps. Paid plans may admit independently, but a free-trial projection with unresolved evidence returns `choose_paid_plan` and denies new usage.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- The activation update is conditioned on an active account-fence generation, exact profile version, active student role/status, and absence of all three trial fields.
- Concurrent and replayed activation selectors observe one write and the same start/expiry pair.
- Partial fields, wrong schema, malformed UTC, incorrect derived expiry, missing activation evidence, and explicit migration-review state all deny new free use without a write.
- One microsecond before expiry admits; the exact expiry instant denies and returns `choose_paid_plan`.
- Effective entitlement preserves explicit account, learning-history, and parent-view reads after expiry.
- The exact planned key link is source-bound: both successful confirmation paths in `auth.py` call `free_trial_service.activate_student_free_trial`, while entitlement projection calls only `get_free_trial_state`.
- No network endpoint, provider call, production data operation, deployment, charge, or external mutation was added or run.

## Known Stubs

None introduced. Optional `None` timestamps exist only in the closed `migration_review_required` projection and intentionally prove that no activation time was inferred.

## Issues Encountered

- Targeted mypy passes for the new free-trial service. Two inherited untyped DynamoDB `get_item` diagnostics remain in `entitlement_service.py` and were already recorded in `deferred-items.md`.
- One existing Starlette test-client deprecation warning remains for the future `httpx2` migration.

## User Setup Required

None - no dependency, credential, migration command, provider configuration, or external service was added.

## Next Phase Readiness

- Governed-use callers and the Phase 476 aggregate security gate can consume the explicit `newUsageAllowed`/`freeTrial` projection without re-deriving trial time.
- Historical rows classified by Plan 04 remain denied until an evidence-bound migration disposition is applied; this plan performs no production or provider operation.

## Self-Check: PASSED

- FOUND: `src/stoa/services/free_trial_service.py`
- FOUND: `tests/test_free_trial_window.py`
- FOUND: `src/stoa/services/entitlement_service.py`
- FOUND: `src/stoa/routers/auth.py`
- FOUND: `476-14-SUMMARY.md`
- FOUND: `9a7e444`
- FOUND: `dafcff8`
- PASS: focused free-trial suite (`10 passed`)
- PASS: governed-use/auth/entitlement regression (`173 passed`)
- PASS: planned Ruff gate, targeted free-trial mypy, and `git diff --check`
- PASS: exact auth-to-activation and entitlement-read source links

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
