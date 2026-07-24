---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 19
subsystem: billing-teacher-support
tags: [teacher-support, dynamodb, idempotency, europe-zurich, family-scope]

requires:
  - phase: 476-13
    provides: Monotonic paid grants and renewal/expiry convergence
  - phase: 476-15
    provides: Canonical plan budgets, Zurich weeks, and conditional allowance-counter pattern
  - phase: 476-17
    provides: Durable question effect and replay boundaries
  - phase: 476-18
    provides: Durable conversation effect and replay boundaries
provides:
  - Exact-once teacher-support admission receipts keyed by durable question or conversation case
  - Two-case beneficiary scopes and ten-case shared family plan-version scopes
  - Atomic case, grant-condition, receipt, and weekly counter-CAS persistence
affects: [teacher-dispatch, questions, conversations, paid-access, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Existing case repositories accept allowance operations so the durable case and debit share one transaction
    - Case receipts replay independently of later entitlement changes while fresh admissions require an exact active grant
    - Shared family counters bind parent subscription and plan version rather than one beneficiary

key-files:
  created:
    - src/stoa/services/teacher_support_allowance_service.py
    - tests/test_teacher_support_allowances.py
  modified:
    - src/stoa/routers/questions.py
    - src/stoa/routers/conversations.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/db/repositories/attachment_repo.py
    - tests/test_questions.py
    - tests/test_conversations.py
    - tests/test_notifications.py
    - tests/test_teacher_reply_sla.py

key-decisions:
  - "Use one global durable-case receipt so a successfully admitted case remains replayable after its paid grant later expires or changes."
  - "Scope teacher_supported by beneficiary plus exact grant/plan version, and family by parent subscription plus plan version shared across selected beneficiaries."
  - "Let the existing question and conversation repositories contribute the beneficiary fence and durable case mutation while the allowance service contributes parent/grant/relationship conditions, receipt, and counter CAS."

patterns-established:
  - "Admission-before-effects: queue, notification, dispatch, and usage evidence run only after the case/debit transaction commits."
  - "DynamoDB target uniqueness: the allowance operation bundle does not repeat the beneficiary fence already owned by the case repository."

requirements-completed: [V9BILL-04]

duration: 14min
completed: 2026-07-24
---

# Phase 476 Plan 19: Exact-Once Teacher-Support Case Allowance Summary

**Durable question and conversation escalations now consume exactly one Zurich-week teacher-support case under an exact beneficiary or shared-family paid-grant scope, with retries and later case activity consuming nothing further.**

## Performance

- **Duration:** 14 min
- **Started:** 2026-07-24T14:56:02Z
- **Completed:** 2026-07-24T15:09:41Z
- **Tasks:** 1
- **Files modified:** 10

## Accomplishments

- Added `TeacherSupportAdmissionDisposition`, `admit_teacher_support_case()`, and `get_teacher_support_projection()` with strict persisted-state parsing and closed replay outcomes.
- Persisted `teacher_support_admission.v1` receipts containing the durable case, opaque effect/grant/scope identities, Zurich week, post-admission count, and exact limit.
- Enforced two cases per `teacher_supported` beneficiary and ten cases per family subscription/plan version shared across three beneficiaries.
- Joined the receipt and counter CAS to the existing question mutation or conversation header/system-message transaction.
- Denied missing, free, student, expired, or grace-ended paid grants before case, queue, notification, dispatch, or usage effects.
- Preserved existing messages, teacher replies, assignment/takeover, resolution, and elapsed-time paths without teacher-support allowance mutation.
- Proved DST-aware 167-hour spring weeks, adjacent-week no-rollover, exact replay, cross-family conflict, and one-winner final-slot concurrency.

## Task Commits

TDD execution produced the mandatory RED and GREEN gates:

1. **Task 476-19-01 RED: Add failing teacher-support allowance contract** - `39c9ab6` (test)
2. **Task 476-19-01 GREEN: Admit teacher-support cases exactly once** - `936f417` (feat)

## Files Created/Modified

- `src/stoa/services/teacher_support_allowance_service.py` - Active-grant scope resolution, exact case receipt, weekly counter CAS, replay classification, and projection.
- `tests/test_teacher_support_allowances.py` - Question/conversation, replay, exact limits, family sharing, race, DST, denial, cross-family, projection, and source-link selectors.
- `src/stoa/routers/questions.py` - Question escalation admits the case/debit transaction before deterministic queue, notification, dispatch, and usage effects.
- `src/stoa/routers/conversations.py` - Conversation escalation reuses the durable request/case identity and admits before its usage effect.
- `src/stoa/db/repositories/question_repo.py` - Question state/version CAS accepts same-transaction allowance operations.
- `src/stoa/db/repositories/attachment_repo.py` - Conversation help transaction accepts same-transaction allowance operations.
- `tests/test_questions.py`, `tests/test_conversations.py`, `tests/test_notifications.py`, `tests/test_teacher_reply_sla.py` - Existing route tests now explicitly admit through the new paid-support boundary.

## Decisions Made

- Made the receipt key independent of the current allowance scope. This lets a lost-response retry prove that the original durable case was already admitted even if the grant later expires, while a different beneficiary using the same case identity conflicts.
- Derived the teacher-supported scope from parent, beneficiary, subscription digest, grant version, and plan version. Derived the family scope from parent, subscription digest, and plan version so all selected beneficiaries share one counter.
- Reused `allowance_service.plan_allowance_budget()` and `allowance_service.zurich_week()` rather than defining a second plan table or time-window algorithm.
- Kept downstream queue/notification/dispatch work outside the admission transaction but after its successful outcome; denial and quota exhaustion cannot trigger those effects.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Extended existing case transaction owners for allowance operations**
- **Found during:** Task 476-19-01 GREEN integration
- **Issue:** Question and conversation repositories owned the guarded durable case writes but had no way to include the planned receipt/counter CAS, so a route-local implementation could not make case admission and debit atomic.
- **Fix:** Added bounded `additional_operations` inputs to the existing mutation/help transaction methods and kept all prior beneficiary-fence and writer-inventory behavior.
- **Files modified:** `src/stoa/db/repositories/question_repo.py`, `src/stoa/db/repositories/attachment_repo.py`
- **Verification:** Question state-CAS and conversation private-writer gates pass; focused tests observe one transaction-owned admission callback.
- **Committed in:** `936f417`

**2. [Rule 1 - Bug] Prevented duplicate DynamoDB transaction targets**
- **Found during:** Task 476-19-01 GREEN security review
- **Issue:** Adding a second student account-fence ConditionCheck from the allowance bundle would duplicate the beneficiary-fence target already contributed by each case repository, which DynamoDB transactions reject.
- **Fix:** Kept the beneficiary fence with the case repository and limited the allowance bundle to the parent fence, exact grant/profile/relationship conditions, receipt, and counter.
- **Files modified:** `src/stoa/services/teacher_support_allowance_service.py`, `tests/test_teacher_support_allowances.py`
- **Verification:** Focused admission transactions use distinct targets and all concurrency/replay selectors pass.
- **Committed in:** `936f417`

---

**Total deviations:** 2 auto-fixed (1 missing critical integration, 1 transaction-target bug).
**Impact on plan:** Both changes are required to make the planned atomic admission valid on DynamoDB; they add no provider, deployment, or production-operation scope.

## Security Verification

- A fresh admission requires an exact active paid beneficiary grant and conditions its parent, beneficiary, plan, allowance, grant, subscription, profile, relationship, and account-fence coordinates in the case transaction.
- Create-only case receipts make question/conversation retries byte-stable and prevent the same durable identity from crossing beneficiaries or families.
- The counter replacement is conditioned on its exact prior `state_version`; a barrier test proves one final-slot winner and no count above the plan limit.
- Family scope excludes the beneficiary identity and includes the parent subscription and plan version, producing one shared counter across three selected beneficiaries.
- Plan denial and quota exhaustion return before durable case, queue, notification, dispatch, assignment, or usage effects; fail-if-called route sentinels pass.
- The service has exact source links to Plan 15's `allowance_service.zurich_week` and `allowance_service.plan_allowance_budget`, plus create-only receipt and state-version CAS expressions.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet. This plan provides 15 passing source-bound High-threat selectors without claiming the later phase-wide publication gate.
- No network request, provider call, charge, deployment, production read, or production mutation was performed.

## Known Stubs

None. Optional `None` admission values are closed non-success results; empty collections found by the stub scan are bounded test fixtures or existing initialization state.

## Issues Encountered

- The repository sandbox required the managed approval path for both normal commits; hooks remained enabled and no verification bypass was used.
- One inherited Starlette `httpx` test-client deprecation warning remains for the later `httpx2` migration.
- The phase-wide security gate script named in plan metadata is still absent and remains later Phase 476 gate ownership.

## User Setup Required

None - no dependency, credential, provider configuration, migration command, or external service was added.

## Next Phase Readiness

- Parent/admin allowance surfaces can consume `get_teacher_support_projection()` without reading private case content or raw provider coordinates.
- Later Phase 476 gate work must include these 15 source-bound selectors and the two existing repository writer-inventory gates.
- Existing admitted cases remain replayable after lifecycle changes, while every fresh case admission revalidates the current exact paid grant.

## Self-Check: PASSED

- FOUND: `src/stoa/services/teacher_support_allowance_service.py`
- FOUND: `tests/test_teacher_support_allowances.py`
- FOUND: `src/stoa/routers/questions.py`
- FOUND: `src/stoa/routers/conversations.py`
- FOUND: `476-19-SUMMARY.md`
- FOUND: `39c9ab6`
- FOUND: `936f417`
- PASS: focused plan suite (`15 passed`)
- PASS: teacher support plus Plan 15 and inherited route/writer regression (`149 passed`)
- PASS: planned Ruff gate, targeted service mypy, and `git diff --check`
- PASS: exact service-to-allowance Zurich week/budget link and admission-before-effects route ordering

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
