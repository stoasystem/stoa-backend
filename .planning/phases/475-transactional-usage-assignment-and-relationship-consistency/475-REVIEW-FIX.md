---
phase: 475
fixed_at: "2026-07-23T10:41:47Z"
review_path: ".planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-REVIEW.md"
iteration: 1
findings_in_scope: 8
fixed: 8
skipped: 0
status: all_fixed
---

# Phase 475: Code Review Fix Report

**Fixed at:** 2026-07-23T10:41:47Z
**Source review:** `.planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-REVIEW.md`
**Iteration:** 1

**Summary:**

- Findings in scope: 8
- Fixed: 8
- Skipped: 0
- Unresolved: none

## Fixed Issues

### CR-01: Ambiguous provider-effect states are terminally stuck instead of converging

**Files modified:** `src/stoa/db/repositories/question_submission_repo.py`, `src/stoa/routers/questions.py`, `tests/test_phase475_question_effect_recovery.py`
**Commit:** `2e74069`
**Status:** fixed: requires human verification
**Applied fix:** Added explicit `intent_ready` and leased `invoking` phases, unique invocation ownership, same-owner lost-response recovery, expired-lease reclaim support, missing-intent replay recovery, and bounded retry of the already validated provider result. `provider_outcome_unknown` is no longer used for result-receipt persistence failures.
**Verification:** The three failure-window convergence tests passed; the complete effect recovery file passed 10 tests; the question submission broad regression passed 131 tests.

### CR-02: Every below-limit rate admission is rejected by DynamoDB validation

**Files modified:** `src/stoa/services/rate_limit.py`, `tests/test_phase475_rate_limit.py`, `tests/dynamodb_expression_assertions.py`
**Commit:** `e44feda`
**Status:** fixed
**Applied fix:** Removed the unused `:limit` value and conditionally supplies `:expected` only when the update condition references it.
**Verification:** Rate-limit and reconciliation expression tests passed as part of 24 focused tests.

### CR-03: Terminal submission compensation cannot execute on DynamoDB

**Files modified:** `src/stoa/db/repositories/question_submission_repo.py`, `tests/test_phase475_question_reconciliation.py`, `tests/dynamodb_expression_assertions.py`
**Commit:** `e44feda`
**Status:** fixed
**Applied fix:** Added the missing `:one` binding to the usage-ledger reversal operation and validated exact expression closure.
**Verification:** Rate-limit and reconciliation expression tests passed as part of 24 focused tests.

### CR-04: Relationship status transitions can reactivate permissions during account deletion

**Files modified:** `src/stoa/db/repositories/user_repo.py`, `tests/test_phase475_parent_binding_transaction.py`
**Commit:** `47fe136`
**Status:** fixed: requires human verification
**Applied fix:** Bound both observed account-fence generations, the active parent profile, and the active/versioned student profile into the status-transition transaction. Lifecycle loss maps to a non-transitioning conflict or retryable outcome.
**Verification:** All 48 parent-binding transaction tests passed, including both participants across all 12 distinct allowed status transitions.

### WR-01: The evidence registry marks the broken provider convergence contract as PASS

**Files modified:** `scripts/verify_phase475.py`, `tests/test_phase475_evidence_verifier.py`, `tests/test_phase475_question_effect_recovery.py`
**Commit:** `2e74069`
**Status:** fixed
**Applied fix:** Registered result-receipt failure, committed-intent response loss, and missing-intent recovery nodes under both D-01 and legacy CR-01.
**Verification:** Evidence verifier and effect recovery suites passed 57 tests together.

### WR-02: Transaction test doubles do not validate DynamoDB expressions

**Files modified:** `tests/dynamodb_expression_assertions.py`, `tests/test_phase475_rate_limit.py`, `tests/test_phase475_question_reconciliation.py`
**Commit:** `e44feda`
**Status:** fixed
**Applied fix:** Added and integrated a shared exact-closure assertion for DynamoDB expression-name and expression-value placeholders.
**Verification:** The new assertion first exposed both malformed operations, then all 24 focused tests passed after the source fixes.

### WR-03: Dispatch treats inactive teacher accounts as available candidates

**Files modified:** `src/stoa/services/teacher_dispatch_service.py`, `src/stoa/db/repositories/question_repo.py`, `tests/test_teacher_dispatch.py`
**Commit:** `a9a362d`
**Status:** fixed: requires human verification
**Applied fix:** Preserved and required active account lifecycle state, defaulted missing availability to unavailable, required positive profile/fence observations, and atomically included the selected teacher fence and profile conditions in question assignment.
**Verification:** Teacher dispatch and question CAS suites passed 21 tests.

### WR-04: Single-page filtered scans silently omit dispatch candidates and questions

**Files modified:** `src/stoa/services/teacher_dispatch_service.py`, `tests/test_teacher_dispatch.py`
**Commit:** `a9a362d`
**Status:** fixed
**Applied fix:** Added bounded `LastEvaluatedKey` pagination until the requested number of filtered matches is collected or the scan is exhausted.
**Verification:** Sparse-page teacher and question scan tests passed; teacher dispatch and question CAS suites passed 21 tests.

## Final Verification

- Focused DynamoDB expression tests: 24 passed.
- Parent-binding transaction tests: 48 passed.
- Teacher dispatch and question CAS tests: 21 passed.
- Provider-effect recovery tests: 10 passed.
- Evidence verifier plus provider-effect tests: 57 passed.
- Question submission broad regression: 131 passed.
- Final combined regression covering all findings: 211 passed.
- Ruff and `git diff --check`: passed for every modified group.
- Existing warning only: Starlette `httpx` deprecation warning.
- Real provider calls: NOT RUN.
- AWS/DynamoDB live or DynamoDB Local contract tests: NOT RUN.
- Deployment checks: NOT RUN.

## Skipped Issues

None.

---

_Fixed: 2026-07-23T10:41:47Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 1_
