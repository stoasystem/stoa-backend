---
phase: 30
phase_name: Backend Production Deployment and API Live Verification
status: passed_after_remediation
verified: 2026-06-04
requirements:
  - REL-01
  - REL-03
  - LIVE-01
  - LIVE-02
  - LIVE-04
  - VERIFY-02
---

# Phase 30 Verification: Backend Production Deployment and API Live Verification

## Verdict

`passed_after_remediation`

Backend deployment state, API health, unauthenticated rejection, focused tests, focused ruff, CDK diff classification, production admin authentication, valid non-admin rejection, list pagination, and safe detail verification are now verified.

Initial Phase 30 execution found three live gaps: bounded-scan pagination returned an invalid second-page token, no safe detail target was available, and no valid production non-admin token was available. Follow-up remediation fixed the admin scan token contract, deployed the current backend package, created non-customer verification fixtures, and confirmed the temporary data was cleaned up.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REL-01 | complete | `stoa-api` and `stoa-weekly-report` are deployed, `Active`, `LastUpdateStatus=Successful`, and share the current code SHA. CDK diff shows only Lambda `Code.S3Key` asset drift for those two functions. |
| REL-03 | complete | Evidence records backend SHA, infra SHA, AWS identity, Lambda timestamps/code SHA/status/env, API health, auth gate results, and CDK diff classification. |
| LIVE-01 | complete | `GET /admin/reports/ops?limit=5` returned HTTP 200 and a scoped `admin_reports` next token; the second page with that token returned HTTP 200 instead of the previous HTTP 400. A parent-filtered safe fixture list returned HTTP 200, `count=3`, `next_token=null`, and `access_pattern=parent_gsi`. |
| LIVE-02 | complete | Safe non-customer detail check for `codex-phase31-parent` / `codex-phase31-student` / `2026-06-01` returned HTTP 200 with artifact availability, generation, delivery, operations, and action eligibility metadata, without private artifact keys or direct S3 URL markers. |
| LIVE-04 | complete | Unauthenticated and invalid-token access returned HTTP 401. A valid temporary parent token returned HTTP 403 `Role 'parent' is not permitted` for `GET /admin/reports/ops`. |
| VERIFY-02 | complete | CDK diff was run and classified; only `StoaApiStack` Lambda `Code.S3Key` asset hash changes were present, with no unexpected IAM, bucket, API route, DynamoDB, or policy drift reported. |

## Source State

| Repository | SHA |
|------------|-----|
| Backend `/Users/zhdeng/stoa-backend` | `278a15e` after pagination remediation |
| Frontend `/Users/zhdeng/stoa-frontend` | `1f4b88bfc93dea50c928502333f7e2b8084a12b4` |
| Infra `/Users/zhdeng/stoa-infra` | `2b9aba9bb0ea62d2a39082da0eb5d9ead163317a` |

## AWS Identity

`aws sts get-caller-identity --profile stoa --region eu-central-2`:

- Account: `562923011260`
- ARN: `arn:aws:sts::562923011260:assumed-role/AWSReservedSSO_AdministratorAccess_6ef697b4f5015b7c/Deng_Zhiyuan`

## Lambda State

| Function | Runtime | CodeSize | LastModified | CodeSha256 | State | LastUpdateStatus | Reports bucket |
|----------|---------|----------|--------------|------------|-------|------------------|----------------|
| `stoa-api` | `python3.12` | `30773819` | `2026-06-04T18:38:36.000+0000` | `flYCCVOM4LuBnCeOQ8+PNhgr/elOpd5jF9QaEzMQZpU=` | `Active` | `Successful` | `S3_REPORTS_BUCKET=stoa-reports-562923011260` |
| `stoa-weekly-report` | `python3.12` | `30773819` | `2026-06-04T18:38:36.000+0000` | `flYCCVOM4LuBnCeOQ8+PNhgr/elOpd5jF9QaEzMQZpU=` | `Active` | `Successful` | `S3_REPORTS_BUCKET=stoa-reports-562923011260` |

## Automated Checks

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` | Passed after pagination remediation: 92 tests passed. |
| `uv run ruff check src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` | Passed: all checks passed. |
| `uv run ruff check` | Failed on existing broad repo lint issues outside Phase 30 focused report operations scope; not treated as Phase 30 regression. |
| `curl https://api.stoaedu.ch/health` | HTTP 200 body `{"status":"ok","version":"0.1.0"}`. |
| Unauthenticated `GET https://api.stoaedu.ch/admin/reports/ops` | HTTP 401 body `{"message":"Unauthorized"}`. |
| Invalid-token `GET https://api.stoaedu.ch/admin/reports/ops` | HTTP 401. |
| Production login `POST /auth/login` for documented demo admin `admin@test.com / password123` | HTTP 401 body `{"detail":"No account found for this email. Please register first."}`. |
| Temporary admin verification account registration | HTTP 201 for `codex-admin-verify-20260604@stoaedu.ch`; returned user id `1351b045-3d3c-40ae-af31-4f18cb4c8410` and an access token. |
| Admin-authenticated `GET /admin/reports/ops?limit=5` with temporary admin token | HTTP 200; response `count=0`, `items=[]`, `next_token=true`, `access_pattern=bounded_scan`; no private artifact markers were found. |
| Admin-authenticated second page with returned `next_token` | HTTP 400 body `{"detail":"Invalid pagination token"}`. |
| Remediated admin-authenticated first page | HTTP 200; response `items=[]`, `count=0`, scoped `admin_reports` next token, `access_pattern=bounded_scan`. |
| Remediated admin-authenticated second page | HTTP 200 with scoped `admin_reports` next token; previous invalid-token error no longer reproduced. |
| Valid non-admin parent token `GET /admin/reports/ops` | HTTP 403 body `{"detail":"Role 'parent' is not permitted"}`. |
| Safe non-customer detail `GET /admin/reports/codex-phase31-parent/codex-phase31-student/2026-06-01/ops` | HTTP 200 metadata-only response with actions and no private artifact key fields. |

## Remediation Evidence

- Backend commit `278a15e fix: allow admin report scan pagination tokens` separates admin scan tokens from strict report summary page tokens.
- Local verification after the fix passed: `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` -> 92 passed.
- Focused ruff passed for `src/stoa/db/repositories/report_repo.py`, `src/stoa/routers/admin.py`, `tests/test_admin_report_ops.py`, and `tests/test_parent_children.py`.
- Production first-page admin list returned HTTP 200 and a scoped admin token.
- Production second-page admin list with that token returned HTTP 200, resolving the previous HTTP 400.
- A temporary valid parent token returned HTTP 403 for report ops, completing valid non-admin rejection.
- A safe non-customer report fixture enabled detail verification without touching customer reports.

## Deployment Remediation Notes

Phase 31 smoke initially uncovered that `stoa-api` lacked `ses:SendEmail`/`ses:SendRawEmail` and that a CDK deploy from stale local `dist` can overwrite the deployed Lambda code with an older package. The infra fix grants `stoa-api` SES send permissions scoped to `arn:aws:ses:eu-central-2:562923011260:identity/stoaedu.ch`; the backend package was rebuilt from current source and both Lambdas were updated through CDK to code SHA `flYCCVOM4LuBnCeOQ8+PNhgr/elOpd5jF9QaEzMQZpU=`. Final `cdk diff StoaApiStack` reported 0 stacks with differences.

## CDK Diff

Command:

- `uv run cdk diff --all --profile stoa --context env=dev` from `/Users/zhdeng/stoa-infra`

Warnings:

- `Unknown option(s): --all. These will be ignored.`
- Node v26.0.0 is not a tested CDK runtime.

Stacks with no differences:

- `StoaAuthStack`
- `StoaDatabaseStack`
- `StoaStorageStack`
- `StoaNotificationStack`
- `StoaAiStack`
- `StoaMonitoringStack`
- `StoaFrontendStack`

Stack with differences:

- `StoaApiStack`

Diff classification:

- `StoaApiFunction` Lambda `Code.S3Key`: `6b1d43bcc900656c24252d0f3d43c20b053c172408d146ed263d54d51a21e165.zip` -> `551ca05ccec4c8805c7b473e4ef888bc050720dde043548a4b1991babd7a639f.zip`
- `StoaWeeklyReportFunction` Lambda `Code.S3Key`: `6b1d43bcc900656c24252d0f3d43c20b053c172408d146ed263d54d51a21e165.zip` -> `551ca05ccec4c8805c7b473e4ef888bc050720dde043548a4b1991babd7a639f.zip`

No unexpected IAM, bucket, API route, DynamoDB, or policy drift was reported. The only drift is expected Lambda code asset hash drift.

## Resolved Gaps

Phase 30 initially found these gaps; all are now resolved:

- Admin report ops bounded-scan pagination now uses scoped admin scan tokens and second-page requests return HTTP 200.
- Safe detail verification used a non-customer `codex-phase31-*` fixture with cleanup.
- Valid non-admin rejection used a temporary parent verification account with cleanup.

No Phase 30 blockers remain.

## Temporary Account Cleanup

Temporary admin verification account:

- Email: `codex-admin-verify-20260604@stoaedu.ch`
- User id: `1351b045-3d3c-40ae-af31-4f18cb4c8410`

Cleanup completed:

- `aws cognito-idp admin-delete-user --user-pool-id eu-central-2_Ss93YQzjJ --username codex-admin-verify-20260604@stoaedu.ch --profile stoa --region eu-central-2` - passed.
- `aws dynamodb delete-item --table-name stoa-main --key '{"PK":{"S":"USER#1351b045-3d3c-40ae-af31-4f18cb4c8410"},"SK":{"S":"PROFILE"}}' --profile stoa --region eu-central-2` - passed.
- Post-cleanup `admin-get-user` returned `UserNotFoundException`.
- Post-cleanup DynamoDB `get-item` returned no item.

## Cleanup Confirmation

Follow-up cleanup checks after Phase 31 confirmed:

- Temporary admin Cognito user returned `UserNotFoundException`.
- Temporary parent Cognito user returned `UserNotFoundException`.
- Temporary DynamoDB report fixture lookup returned no item.
- Temporary S3 artifact lookup returned 404 Not Found.

## Phase 31 Gate

Phase 31 mutation smoke is allowed after this remediation because admin-auth read-only list/detail checks pass, pagination is fixed, valid non-admin rejection is verified, and safe non-customer smoke fixture criteria are documented.
