---
phase: 475-transactional-usage-assignment-and-relationship-consistency
reviewed: 2026-07-23T10:53:26Z
depth: standard
files_reviewed: 60
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
  - tests/dynamodb_expression_assertions.py
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: issues_found
---

# Phase 475: Code Review Report

**Reviewed:** 2026-07-23T10:53:26Z
**Depth:** standard
**Files Reviewed:** 60
**Status:** issues_found

## Summary

Iteration 2 confirms CR-02, CR-03, CR-04, WR-02, and WR-03 are closed: DynamoDB expression placeholders now have exact closure, terminal compensation binds `:one`, relationship lifecycle transitions carry both account/profile observations, and every selected dispatch assignment is fenced by the teacher's current lifecycle state.

CR-01 remains release-blocking because an expired `invoking` lease can repeat a provider call after the first call succeeded but the process died before storing its result. WR-01 therefore still overstates provider convergence, and its published evidence remains bound to the pre-fix candidate. WR-04's pagination fix still stops before the Python eligibility filter. The dispatch fix also introduces one new exact-file mypy failure (WR-05).

The 33 reviewed test modules pass (`655 passed`), and the focused seven-module fix regression passes (`150 passed`). Those suites do not exercise the two residual failure shapes below.

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01 [BLOCKER]: Expired invocation leases can call the provider twice

**File:** `src/stoa/db/repositories/question_submission_repo.py:845`
**Related:** `src/stoa/routers/questions.py:518`, `src/stoa/routers/questions.py:580`, `src/stoa/db/repositories/question_submission_repo.py:1364`

**Issue:** The durable state changes to `invoking` before the provider call, but that state does not prove whether invocation has started or completed. Every request generates a new random owner. Once `invocation_lease_expires_at` passes, `_claim_question_effect_invocation()` allows that new owner to replace the old owner and returns `INVOKE_PROVIDER`; `_recover_missing_question_effect()` then calls the provider again. A process death after the provider accepted/completed the first invocation but before `record_question_effect_result()` durably stored the result therefore duplicates the provider effect.

The existing harness reproduces this deterministically: terminate the first request immediately after `get_ai_answer()` is entered, expire the stored lease, and replay the same submission. The effect moves `invoking -> completed`, but `provider_calls` moves from 1 to 2. The same outcome follows when all three immediate result-persistence attempts fail: only the in-memory validated result exists, so later lease reclaim cannot recover it without reinvoking.

**Fix:** Make provider replay idempotent at the provider boundary. Pass the deterministic `effect_id` as the provider idempotency key (or persist a provider request ID and use a provider status/result lookup), so reclaim always retrieves the original invocation result:

```python
provider_result = provider.invoke_or_replay(
    idempotency_key=str(effect["effect_id"]),
    request=provider_request,
)
```

Keep `intent_ready` reclaimable before provider admission, but never blindly reinvoke an ambiguous `invoking` row when the provider cannot deduplicate or query it. Add a crash-after-provider-before-receipt test that expires the lease, converges to the original result, and asserts `provider_calls == 1`.

## Warnings

### WR-01 [WARNING]: Evidence still reports provider convergence without the ambiguous-invocation proof

**File:** `scripts/verify_phase475.py:766`
**Related:** `tests/test_phase475_question_effect_recovery.py:495`, `docs/security/phase-475-evidence-results.json:2`, `docs/security/phase-475-evidence-results.json:1191`

**Issue:** The new D-01/CR-01 selectors prove one result-write retry, same-request intent response loss, and missing-intent recovery. None kills the worker after the provider has accepted the call and then replays after a different owner's lease reclaim, which is the CR-01 failure above. The registry can therefore render D-01 and CR-01 as PASS while provider invocation is duplicated.

The checked evidence artifact was also not regenerated after the fixes: it is still bound to candidate `677edf994deaee4aa0faef91eb38e2a3a07899ea` and records the removed test `test_result_receipt_failure_closes_unknown_state_and_never_blindly_reinvokes`. It does not attest commits `e44feda`, `47fe136`, `a9a362d`, or `2e74069`.

**Fix:** Add the crash/lease-reclaim/no-duplicate node described in CR-01 to both D-01 and CR-01, require it in the registry-closure test, then capture and publish evidence from a clean candidate containing all review fixes.

### WR-04 [WARNING]: Pagination still stops before business eligibility filtering

**File:** `src/stoa/services/teacher_dispatch_service.py:573`
**Related:** `src/stoa/services/teacher_dispatch_service.py:44`, `src/stoa/services/teacher_dispatch_service.py:74`, `tests/test_teacher_dispatch.py:204`

**Issue:** `_scan_filtered_items()` stops when it has collected `limit` rows matching only `SK = PROFILE` or `SK = META`. Teacher role/lifecycle/fence/availability and dispatch-question markers are filtered afterward. If the first evaluated page contains `limit` student/inactive profiles or ordinary question META rows, the helper returns without reading `LastEvaluatedKey`; the caller then filters every collected row out and misses eligible teachers/questions on the next page.

A deterministic `limit=1` probe with one student profile followed by one active teacher returns `teachers=[]` after one scan. The equivalent ordinary-question/dispatch-question probe returns `questions=[]` after one scan. The added sparse-page test uses an empty first `Items` page, so it does not cover this boundary.

**Fix:** Paginate until the caller's final predicate has produced `limit` accepted rows, not until the coarse DynamoDB filter has produced `limit` rows. Add tests whose first non-empty page contains only rejected profile/META rows and whose second page contains an eligible row.

### WR-05 [WARNING]: Dispatch conditions regress the phase's exact mypy gate

**File:** `src/stoa/db/repositories/question_repo.py:851`
**Related:** `src/stoa/db/repositories/question_repo.py:877`

**Issue:** `additional_conditions` is typed as `tuple[Mapping[str, object], ...]`, but it is expanded into a transaction list inferred as `list[dict[str, Any]]`. The exact 22-runtime-file command now fails:

```text
src/stoa/db/repositories/question_repo.py:877: error:
List item 1 has incompatible type "tuple[Mapping[str, object], ...]";
expected "dict[str, Any]"  [list-item]
```

This was introduced by `a9a362d` and invalidates the unfiltered zero-diagnostic mypy property claimed by the Phase 475 evidence gate.

**Fix:** Use the repository's concrete transaction-operation type for the parameter and list, or validate/copy mappings before expansion:

```python
additional_conditions: tuple[QuestionItem, ...] = ()
operations: list[QuestionItem] = [
    active_fence,
    *additional_conditions,
    question_update,
]
```

Re-run the exact 22-file mypy gate after the change.

---

_Reviewed: 2026-07-23T10:53:26Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
