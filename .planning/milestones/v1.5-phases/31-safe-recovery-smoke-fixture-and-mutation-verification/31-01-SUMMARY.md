---
plan_id: 31-01
phase: 31
phase_name: Safe Recovery Smoke Fixture and Mutation Verification
status: complete
completed: 2026-06-04
requirements:
  - SMOKE-01
  - SMOKE-02
  - SMOKE-03
  - SMOKE-04
  - SMOKE-05
---

# Plan 31-01 Summary: Safe Recovery Smoke Fixture and Mutation Verification

Phase 31 created a temporary non-customer smoke fixture, ran production recovery mutations, and cleaned up the fixture data.

## Completed

- Valid parent token rejected report ops with HTTP 403.
- Admin parent-filtered list returned HTTP 200 with three safe fixture rows and metadata-only response fields.
- Admin detail returned HTTP 200 for the generation retry target with retry action enabled.
- Generation retry returned HTTP 200 with `status=email_sent`, `email_status=sent`, and `operation_result=success`.
- Single resend returned HTTP 200 with `status=email_sent`, `email_status=sent`, and `operation_result=success`.
- Bulk resend returned HTTP 200 with one `success` result and one `not_found` result.
- Post-mutation detail checks recorded `last_operation`, `last_operation_by`, `last_operation_result`, `resend_attempted_at`, and `resend_completed_at` fields.
- Cleanup removed temporary Cognito users, DynamoDB fixtures, and S3 artifacts.

## Production Fixes Required During Smoke

- `stoa-api` needed SES send permission for admin recovery send paths. Infra now grants `ses:SendEmail` and `ses:SendRawEmail` scoped to `arn:aws:ses:eu-central-2:562923011260:identity/stoaedu.ch`.
- A CDK deploy from stale local `dist` temporarily rolled Lambda code back to an older package. The backend package was rebuilt from current source and redeployed to both Lambdas.

## Result

Phase 31 passed after IAM and package remediation.

