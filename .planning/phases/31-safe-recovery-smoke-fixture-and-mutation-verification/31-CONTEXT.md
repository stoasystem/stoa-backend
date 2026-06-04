---
phase: 31
phase_name: Safe Recovery Smoke Fixture and Mutation Verification
status: complete
gathered: 2026-06-04
---

# Phase 31: Safe Recovery Smoke Fixture and Mutation Verification - Context

## Phase Boundary

Run production recovery mutation smoke only against temporary non-customer records and clean them up after verification.

Allowed operations:

- Create temporary Cognito admin/parent verification users.
- Create temporary DynamoDB parent/student/report fixture records under `codex-phase31-*`.
- Create temporary private S3 report HTML artifacts under `weekly-reports/codex-phase31-parent/codex-phase31-student/*`.
- Call admin list/detail, retry generation, single resend, and selected bulk resend APIs.
- Delete all temporary Cognito, DynamoDB, and S3 fixture data.

## Safe Fixture

- Parent id: `codex-phase31-parent`
- Student id: `codex-phase31-student`
- Parent email: `codex-phase31-parent@stoaedu.ch`
- Generation retry week: `2026-06-01`
- Single resend week: `2026-05-25`
- Bulk resend week: `2026-05-18`

The fixture contains no customer PII and is isolated by deterministic `codex-phase31-*` identifiers.

## Preconditions

- Phase 30 admin list/detail and valid non-admin checks pass.
- `stoa-api` has SES send permission scoped to `arn:aws:ses:eu-central-2:562923011260:identity/stoaedu.ch`.
- Current backend package is deployed to both `stoa-api` and `stoa-weekly-report`.

---
*Phase: 31-safe-recovery-smoke-fixture-and-mutation-verification*
*Context gathered: 2026-06-04*
