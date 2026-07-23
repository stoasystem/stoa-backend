---
phase: 475-transactional-usage-assignment-and-relationship-consistency
reviewed: 2026-07-23T10:16:51Z
depth: standard
files_reviewed: 59
files_reviewed_list:
  - docs/security/phase-475-evidence-results.json
  - docs/security/phase-475-evidence.md
  - docs/security/route-authorization-inventory.json
  - scripts/verify_phase475.py
  - src/stoa/db/repositories/account_deletion_repo.py
  - src/stoa/db/repositories/notification_repo.py
  - src/stoa/db/repositories/practice_repo.py
  - src/stoa/db/repositories/question_repo.py
  - src/stoa/db/repositories/question_submission_repo.py
  - src/stoa/db/repositories/user_repo.py
  - src/stoa/jobs/reconcile_question_submissions.py
  - src/stoa/models/practice.py
  - src/stoa/models/question.py
  - src/stoa/routers/admin.py
  - src/stoa/routers/auth.py
  - src/stoa/routers/practice.py
  - src/stoa/routers/questions.py
  - src/stoa/routers/teachers.py
  - src/stoa/security/authorization.py
  - src/stoa/services/account_deletion_service.py
  - src/stoa/services/notification_service.py
  - src/stoa/services/practice_projection_service.py
  - src/stoa/services/rate_limit.py
  - src/stoa/services/subscription_service.py
  - src/stoa/services/teacher_dispatch_service.py
  - src/stoa/services/usage_ledger_service.py
  - tests/test_admin_authorization.py
  - tests/test_auth_account_lifecycle.py
  - tests/test_conversations.py
  - tests/test_curriculum_analytics.py
  - tests/test_phase473_account_deletion.py
  - tests/test_phase473_account_deletion_claim_fencing.py
  - tests/test_phase473_delivery_intent_recovery.py
  - tests/test_phase473_notification_deletion.py
  - tests/test_phase475_completed_deletion_replay.py
  - tests/test_phase475_deletion_discovery.py
  - tests/test_phase475_deletion_notification_identity_scrub.py
  - tests/test_phase475_deletion_relationship_scrub.py
  - tests/test_phase475_deletion_teacher_identity_scrub.py
  - tests/test_phase475_delivery_begin.py
  - tests/test_phase475_evidence_verifier.py
  - tests/test_phase475_mistake_answer.py
  - tests/test_phase475_parent_binding_reconciliation.py
  - tests/test_phase475_parent_binding_transaction.py
  - tests/test_phase475_profile_version_cas.py
  - tests/test_phase475_question_admission.py
  - tests/test_phase475_question_effect_recovery.py
  - tests/test_phase475_question_reconciliation.py
  - tests/test_phase475_question_replay.py
  - tests/test_phase475_question_state_cas.py
  - tests/test_phase475_rate_limit.py
  - tests/test_phase475_teacher_takeover.py
  - tests/test_phase475_teacher_takeover_effect.py
  - tests/test_practice.py
  - tests/test_questions.py
  - tests/test_subscription_operations.py
  - tests/test_teacher_dispatch.py
  - tests/test_teacher_reply_sla.py
  - tests/test_usage_ledger.py
findings:
  critical: 4
  warning: 4
  info: 0
  total: 8
status: issues_found
---

# Phase 475: Code Review Report

**Reviewed:** 2026-07-23T10:16:51Z
**Depth:** standard
**Files Reviewed:** 59
**Status:** issues_found

## Summary

The submitted implementation still has four release-blocking correctness or security defects. Two DynamoDB transactions are invalid against the real service, successful or not-yet-invoked question provider effects can become permanently non-convergent, and relationship status transitions can reactivate authorization projections without atomically proving that both accounts remain active. The evidence gate and its in-memory transaction doubles conceal several of these failures.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]: Ambiguous provider-effect states are terminally stuck instead of converging

**File:** `src/stoa/db/repositories/question_submission_repo.py:674`
**Related:** `src/stoa/db/repositories/question_submission_repo.py:1229`, `src/stoa/routers/questions.py:388`, `tests/test_phase475_question_effect_recovery.py:475`

**Issue:** `begin_question_effect()` durably writes `status="inflight"` before provider invocation. If the transaction commits but its response is lost, the reread returns that inflight receipt, the route refuses to invoke the provider, and replay returns the same pending question forever. If the intent write fails before commit, replay observes no receipt and `_recover_question_effect_receipts()` simply skips the missing effect, so that path is also permanently pending. Separately, after a provider succeeds, any pre-commit failure in `record_question_effect_result()` discards the already validated result by changing the receipt to `provider_outcome_unknown`; no worker can ever complete it. The tests at lines 475-521 explicitly assert these non-convergent outcomes (`provider_calls == 0` for a committed intent and `ai_response is None` after a successful provider call), contrary to D-01's backend-convergence contract.

**Fix:** Give each effect a retryable invocation lease/owner and explicit invocation phases. A replay or reconciler must be able to:

1. retry creation of a missing pre-provider intent;
2. acquire or recover an expired intent whose provider invocation has not started;
3. retry persistence of the in-memory validated provider result until it is durably `result_ready`; and
4. reserve `provider_outcome_unknown` only for an actually ambiguous provider invocation, with an operator/reconciliation path to a terminal outcome.

Replace the two permanent-pending tests with bounded eventual-convergence assertions while retaining the no-duplicate-provider invariant.

### CR-02 [BLOCKER]: Every below-limit rate admission is rejected by DynamoDB validation

**File:** `src/stoa/services/rate_limit.py:412`

**Issue:** The counter update supplies `":limit"` in `ExpressionAttributeValues` at line 443, but neither its update nor condition expression references that token. DynamoDB rejects unused expression attribute values with `ValidationException`, so a real below-limit admission transaction cannot commit. The in-memory test double accepts the malformed request and even asserts that the unused token exists, masking the production failure.

**Fix:**

```python
"ExpressionAttributeValues": {
    ":expected": counter_value,
    ":next": next_counter_value,
    ":expires": expires_at_value,
    ":counter_type": "rate_counter",
    ":owner": owner,
    ":period": period,
    ":generation": generation,
}
```

Alternatively, reference `:limit` in a genuine atomic cap condition. Add a test that rejects any unused or missing DynamoDB expression placeholder.

### CR-03 [BLOCKER]: Terminal submission compensation cannot execute on DynamoDB

**File:** `src/stoa/db/repositories/question_submission_repo.py:2240`

**Issue:** The usage-ledger condition contains `quantity=:one` at line 2249, but that update's `ExpressionAttributeValues` omits `":one"`. The `:one` supplied to the preceding counter operation is scoped to that operation and is not available here. Real DynamoDB therefore rejects the entire transaction, preventing the promised exact-once allowance and ledger reversal after proven terminal provider failure.

**Fix:**

```python
"ExpressionAttributeValues": {
    ":ledger": ledger_identity,
    ":student": student_id,
    ":command_id": current.command_id,
    ":question": current.question_id,
    ":one": 1,
    ":active": "active",
    ":reversed": "reversed",
    ":reversal": reversal_id,
    ":reversed_at": reversed_at,
}
```

Exercise this transaction with DynamoDB-compatible expression validation before treating D-03 as satisfied.

### CR-04 [BLOCKER]: Relationship status transitions can reactivate permissions during account deletion

**File:** `src/stoa/db/repositories/user_repo.py:718`
**Related:** `src/stoa/routers/admin.py:2305`

**Issue:** Initial parent binding creation atomically includes parent/student active-account fences and active profile observations, but the status-transition transaction contains only the two relationship updates and the student's profile update. The admin endpoint accepts transitions back to `active`. A parent or student can therefore become inactive or enter deletion after the pre-read at line 837 while the transaction still commits an active forward edge, reverse edge, and student projection. Exact relationship status/version CAS does not protect the independently changing account lifecycle, so authorization data and cross-account identity can be revived during deletion.

**Fix:** Pass both observed fence generations and both observed active profile versions into `build_parent_binding_status_transition_transaction()`. In the same transaction, add both `active_fence_condition()` checks and active parent/student profile observation checks, including `account_status="active"`, before any relationship update. Map lifecycle loss to a conflict/retryable result and add races for both participants and every allowed status transition.

## Warnings

### WR-01 [WARNING]: The evidence registry marks the broken provider convergence contract as PASS

**File:** `scripts/verify_phase475.py:765`

**Issue:** D-01 and legacy CR-01 are mapped only to successful receipt recovery and a generic pending-response test. The registry omits the scoped tests at `tests/test_phase475_question_effect_recovery.py:475-521` that deliberately prove permanent `provider_outcome_unknown` and `inflight` states. Consequently the published evidence can report PASS while the decision contract it claims to verify is false.

**Fix:** Register failure-window tests that require eventual completion or proven terminal compensation after intent response loss, missing-intent dependency recovery, and result-receipt failure. A test that merely returns a queryable pending row must not satisfy the convergence node.

### WR-02 [WARNING]: Transaction test doubles do not validate DynamoDB expressions

**File:** `tests/test_phase475_rate_limit.py:71`
**Related:** `tests/test_phase475_question_reconciliation.py:181`

**Issue:** The rate-limit fake manually interprets only selected condition shapes, while the reconciliation fake reads selected values without checking that every placeholder referenced by an expression is defined and every supplied placeholder is used. This makes both CR-02 and CR-03 pass locally and gives the evidence verifier a false production-equivalence signal.

**Fix:** Add a shared assertion for every fake transaction operation that tokenizes all expressions and requires exact closure over `ExpressionAttributeNames` and `ExpressionAttributeValues`. Keep at least one DynamoDB Local or live-AWS contract test for service-level expression semantics.

### WR-03 [WARNING]: Dispatch treats inactive teacher accounts as available candidates

**File:** `src/stoa/services/teacher_dispatch_service.py:44`
**Related:** `src/stoa/services/teacher_dispatch_service.py:414`

**Issue:** Candidate loading filters only `role`, normalization drops account lifecycle state, and missing dispatch availability defaults to `"available"`. An inactive/deleting teacher profile with a teacher/admin role can therefore be selected and persisted as the assigned teacher. Later takeover fencing does not undo the dead initial assignment, which can delay the student until timeout.

**Fix:** Require an active account fence and active profile lifecycle state when assigning a teacher, not just when the teacher later takes over. Preserve `account_status` in normalization, default missing availability to unavailable, and add inactive/deleting-profile dispatch tests.

### WR-04 [WARNING]: Single-page filtered scans silently omit dispatch candidates and questions

**File:** `src/stoa/services/teacher_dispatch_service.py:44`
**Related:** `src/stoa/services/teacher_dispatch_service.py:62`

**Issue:** Both helpers issue one DynamoDB `Scan` with `Limit=limit` and ignore `LastEvaluatedKey`. DynamoDB applies `Limit` to evaluated items before the filter, so a table whose first page contains unrelated rows can return fewer than `limit` matches—or none—despite eligible teachers or dispatch questions existing later. This changes dispatch and SLA behavior, not merely performance.

**Fix:** Paginate with `ExclusiveStartKey` until the requested number of matching rows is collected or the scan is exhausted. Add sparse-table tests where the first evaluated page has zero matching profiles/questions.

---

_Reviewed: 2026-07-23T10:16:51Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
