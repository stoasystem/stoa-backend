---
phase: 475-transactional-usage-assignment-and-relationship-consistency
reviewed: 2026-07-23T11:42:00Z
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
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase 475: Code Review Report

**Reviewed:** 2026-07-23T11:42:00Z
**Depth:** standard
**Files Reviewed:** 60
**Status:** clean

## Summary

Iteration 3 reviewed the original 60-file scope and the iteration 2 fixes in
`a5746b8`, `c81fd93`, `ea70f59`, `6491370`, `d63af86`, and `c30dfc9`, plus the
report-only commit `e6790d8`. CR-01, WR-01, WR-04, and WR-05 are closed. No new
correctness, security, or maintainability defect was found.

All reviewed files meet quality standards. No issues found.

## Narrative Findings (AI reviewer)

No Critical, Warning, or Info findings.

## Prior Finding Closure

### CR-01 — Closed

`question_submission_repo.py` now distinguishes an unstarted `intent_ready`
effect from an already admitted `invoking` effect. A different owner cannot
reclaim an `invoking` row to call the provider. After expiry, one conditional
update binds the exact prior owner, exact lease, exact version, and
`lease <= observed_at` before recording `provider_outcome_ambiguous`.

That terminal proof is promoted transactionally to `terminal_failed`, then the
existing reconciliation transaction reverses the counter and ledger exactly
once and moves the question to `submission_failed`. Stable same-key replay
performs no provider or transaction work, while a fresh key can commit a new
submission. `intent_ready` remains safely claimable and recoverable.

### WR-01 — Closed

The crash-after-provider-before-receipt selector is registered under both D-01
and CR-01. The published evidence is bound to candidate
`d63af86a9543fd678017d4c8a6ce1f641208ed35`, which contains every iteration 2
fix commit, and publication
`c30dfc9d9ffead55199525f37ac59f50a9449481` is its direct child changing
exactly the two evidence files. Both evidence blobs at current HEAD are
identical to the publication blobs.

### WR-04 — Closed

Teacher and dispatch-question scans now apply the final business-eligibility
callback while paginating. They continue until `limit` eligible rows have been
accepted or DynamoDB pagination is exhausted. The regression includes a
non-empty rejected first page followed by an eligible second page for both
profiles and questions.

### WR-05 — Closed

`additional_conditions` and the assembled transaction list now use the
repository's concrete `QuestionItem` type. The exact ordered 22-runtime-file
mypy command completed with zero diagnostics.

## Verification

- Original review-scope tests: **657 passed** across 34 test files.
- Focused fix regression: **92 passed**.
- Exact runtime type gate: **22 files, 0 diagnostics**.
- Ruff over the runtime inventory, verifier, and affected tests: **passed**.
- Published default-sandbox formal manifest: **2,619/2,619 passed**, with zero
  failed, error, skipped, xfail, or xpass outcomes.
- The same formal manifest records PASS for direct/subprocess network denial
  and both normal-return orphan and timeout process-group termination nodes.
- Live AWS/DynamoDB, live provider effects, deployment, and production smoke
  remain explicitly **NOT RUN** under Phases 479/480.

---

_Reviewed: 2026-07-23T11:42:00Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
