# Requirements: v5.7 Usage Ledger And Quota Reconciliation

**Milestone:** v5.7
**Status:** Complete
**Created:** 2026-07-03
**Prior milestone:** v5.6 Effective Entitlements And Paid Access Enforcement

## Purpose

Turn plan-governed usage from counter-only behavior into durable, queryable ledger events and reconcile those events with quota counters.

v5.6 made effective entitlement authoritative for question quota. v5.7 makes usage evidence durable enough for support, reconciliation, and future parent/admin operations visibility.

## Requirements

### LEDGER-01 Usage Ledger Contract And Idempotency

Acceptance criteria:

- Usage ledger event schema is defined for quota-governed actions, starting with student question submissions.
- Event fields include actor/student, parent context when available, action, quantity, entitlement snapshot, effective plan/source, quota period, counter key, idempotency key, request/question correlation, timestamps, and privacy-safe metadata.
- Idempotency rules prevent duplicate ledger rows for retried question submissions or repeated writes.
- Ledger write ordering relative to the atomic quota counter is explicit.
- Privacy boundaries forbid raw question content, provider secrets, private S3 keys, invoice internals, and unredacted billing payloads.

### LEDGER-02 Question Usage Ledger Recording

Acceptance criteria:

- Successful student question quota increments write durable ledger events.
- Ledger events store the effective entitlement snapshot used for the quota decision.
- Failed or refused quota attempts do not create consumed-usage events unless explicitly classified as refused audit metadata.
- Existing daily counter behavior remains stable.
- Tests cover free, paid parent entitlement, manual override, pending/blocked entitlement, retry/idempotency, and quota exhaustion paths.

### RECON-01 Quota Counter Reconciliation

Acceptance criteria:

- Reconciliation can compare daily counter rows with ledger event totals for a student/action/day.
- Reconciliation reports matched, ledger-missing, counter-missing, and count-mismatch states.
- Reconciliation is read-only by default and safe to run repeatedly.
- Any repair behavior is deterministic, bounded, and explicitly separated from preview/report mode.
- Tests cover matching counts, missing ledger rows, missing counter rows, mismatched counts, and repeated reconciliation runs.

### USAGE-01 Usage Visibility And Support Summaries

Acceptance criteria:

- Parent/customer usage summary can show consumed, limit, remaining, effective plan, and reconciliation status for linked students.
- Admin/support usage summary can inspect student usage ledger and reconciliation status without exposing private question content or billing internals.
- Existing parent/admin subscription and entitlement responses remain backward compatible.
- Visibility surfaces identify when ledger data is partial, stale, or unreconciled.
- Broader operations console work remains handed off to v5.9.

### VERIFY-40 v5.7 Usage Ledger Release Gate

Acceptance criteria:

- Ledger contract, question usage recording, reconciliation, visibility, and tests are complete.
- Requirements, roadmap, state, and remaining-feature queue reflect v5.7 completion.
- Release evidence identifies commit SHAs, focused tests, lint checks, and residual full-suite status.
- Final audit records rollout state: `usage-ledger-ready`, `blocked`, or `deferred`.
- v5.8 email verification/login-code policy handoff is updated.

## Future Milestones

- v5.8 Email Verification And Login Code Policy.
- v5.9 Parent Admin Operations Visibility.
- Native iOS/Android app buildout after core account/payment/usage correctness.

## Out of Scope

- Email verification and login-code implementation.
- Full parent/admin operations console.
- Native app implementation.
- Final live Stripe/TWINT activation.
- Replacing DynamoDB with an analytics warehouse.
- Storing raw question content, answer content, private S3 keys, or provider billing payloads in usage ledger rows.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LEDGER-01 | Phase 207 | Complete |
| LEDGER-02 | Phase 208 | Complete |
| RECON-01 | Phase 209 | Complete |
| USAGE-01 | Phase 210 | Complete |
| VERIFY-40 | Phase 211 | Complete |
