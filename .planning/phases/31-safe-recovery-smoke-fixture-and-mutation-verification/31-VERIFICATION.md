---
phase: 31
phase_name: Safe Recovery Smoke Fixture and Mutation Verification
status: passed_after_remediation
verified: 2026-06-04
requirements:
  - SMOKE-01
  - SMOKE-02
  - SMOKE-03
  - SMOKE-04
  - SMOKE-05
---

# Phase 31 Verification: Safe Recovery Smoke Fixture and Mutation Verification

## Verdict

`passed_after_remediation`

Safe non-customer production mutation smoke passed for generation retry, single resend, selected bulk resend, valid non-admin rejection, admin list/detail metadata, and fixture cleanup.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SMOKE-01 | complete | Safe non-customer target documented as `codex-phase31-parent` / `codex-phase31-student` with weeks `2026-06-01`, `2026-05-25`, and `2026-05-18`. |
| SMOKE-02 | complete | Retry generation returned HTTP 200, `status=email_sent`, `email_status=sent`, `operation_result=success`, artifact booleans true, and post-detail recorded `last_operation=retry_generation`. |
| SMOKE-03 | complete | Single resend returned HTTP 200, `status=email_sent`, `email_status=sent`, `operation_result=success`, and post-detail recorded resend audit fields. |
| SMOKE-04 | complete | Bulk resend returned HTTP 200 with per-item `success` for the safe failed target and `not_found` for a missing target. |
| SMOKE-05 | complete | Cleanup confirmed temporary Cognito users absent, temporary DynamoDB report absent, and temporary S3 artifact absent. |

## Final Lambda State

| Function | LastModified | CodeSha256 | State | LastUpdateStatus |
|----------|--------------|------------|-------|------------------|
| `stoa-api` | `2026-06-04T18:38:36.000+0000` | `flYCCVOM4LuBnCeOQ8+PNhgr/elOpd5jF9QaEzMQZpU=` | `Active` | `Successful` |
| `stoa-weekly-report` | `2026-06-04T18:38:36.000+0000` | `flYCCVOM4LuBnCeOQ8+PNhgr/elOpd5jF9QaEzMQZpU=` | `Active` | `Successful` |

## Smoke Output Summary

| Check | Result |
|-------|--------|
| Valid parent token `GET /admin/reports/ops` | HTTP 403 `Role 'parent' is not permitted`. |
| Admin list `GET /admin/reports/ops?parent_id=codex-phase31-parent&limit=10` | HTTP 200, `count=3`, `next_token=null`, `access_pattern=parent_gsi`. |
| Detail before retry | HTTP 200, `status=generation_failed`, `retry_generation.enabled=true`, metadata-only response. |
| Retry generation | HTTP 200, `status=email_sent`, `email_status=sent`, `operation_result=success`, artifacts true. |
| Detail after retry | HTTP 200, generated and sent timestamps present, `last_operation=retry_generation`, `last_operation_result=success`. |
| Single resend | HTTP 200, `status=email_sent`, `email_status=sent`, `operation_result=success`. |
| Bulk resend | HTTP 200, results `[success, not_found]`. |
| Detail after single resend | HTTP 200, `last_operation=resend_email`, `last_operation_result=success`, resend timestamps present. |
| Detail after bulk resend | HTTP 200, `last_operation=resend_email`, `last_operation_result=success`, resend timestamps present. |

## Remediation Evidence

Initial smoke found `AccessDenied` for `ses:SendEmail` from the `stoa-api` role. Infra remediation grants `stoa-api` `ses:SendEmail` and `ses:SendRawEmail` scoped to `arn:aws:ses:eu-central-2:562923011260:identity/stoaedu.ch`.

The same CDK deploy temporarily reintroduced an older Lambda package from stale local `dist`, making report ops list/retry/bulk endpoints return HTTP 404 and detail expose the old `artifact_keys` shape. The backend Lambda package was rebuilt from current source and redeployed to both functions before final smoke. A follow-up CDK deploy aligned CloudFormation to the rebuilt package, and final `cdk diff StoaApiStack` reported 0 differences. Final smoke responses used the current metadata-only `artifacts` and `actions` shape.

## Cleanup Evidence

- `admin-get-user` for `codex-admin-pagination-20260604@stoaedu.ch` returned `UserNotFoundException`.
- `admin-get-user` for `codex-parent-verify-20260604@stoaedu.ch` returned `UserNotFoundException`.
- DynamoDB `get-item` for `REPORT#weekly-report-codex-phase31-parent-codex-phase31-student-2026-06-01` returned no item.
- S3 `head-object` for `weekly-reports/codex-phase31-parent/codex-phase31-student/2026-05-25/report.html` returned 404 Not Found.

## Residual Risk

CDK deployments use `../stoa-backend/dist`; operators must rebuild `dist` from current backend source before CDK deploys that touch Lambda assets, or deploy IAM-only changes with a method that cannot package stale backend code.
