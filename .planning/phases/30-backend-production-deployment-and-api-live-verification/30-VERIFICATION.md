---
phase: 30
phase_name: Backend Production Deployment and API Live Verification
status: gaps_found
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

`gaps_found`

Backend deployment state, API health, unauthenticated rejection, focused tests, focused ruff, CDK diff classification, and production admin authentication were verified. Admin-authenticated report operations list returned HTTP 200, but Phase 30 still has gaps: the first page returned no rows with a `next_token`, the follow-up page returned `Invalid pagination token`, no safe detail target was available, and a valid non-admin token was not available.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REL-01 | complete | `stoa-api` and `stoa-weekly-report` are deployed, `Active`, `LastUpdateStatus=Successful`, and share the current code SHA. CDK diff shows only Lambda `Code.S3Key` asset drift for those two functions. |
| REL-03 | complete | Evidence records backend SHA, infra SHA, AWS identity, Lambda timestamps/code SHA/status/env, API health, auth gate results, and CDK diff classification. |
| LIVE-01 | partial | A temporary production admin verification account successfully called `GET /admin/reports/ops?limit=5` and received HTTP 200. The response was metadata-only but returned `count=0`, `items=[]`, and `next_token=true`; following the token returned HTTP 400 `Invalid pagination token`. |
| LIVE-02 | blocked | Admin-authenticated detail endpoint was not run because the list endpoint returned no safe report row and the next page token was invalid. |
| LIVE-04 | partial | Unauthenticated and invalid-token access to `GET /admin/reports/ops` return HTTP 401. A true non-admin valid token was not available without creating a production user, so valid non-admin rejection remains blocked. |
| VERIFY-02 | complete | CDK diff was run and classified; only `StoaApiStack` Lambda `Code.S3Key` asset hash changes were present, with no unexpected IAM, bucket, API route, DynamoDB, or policy drift reported. |

## Source State

| Repository | SHA |
|------------|-----|
| Backend `/Users/zhdeng/stoa-backend` | `3a3b8da` before Phase 30 docs commit |
| Frontend `/Users/zhdeng/stoa-frontend` | `1f4b88bfc93dea50c928502333f7e2b8084a12b4` |
| Infra `/Users/zhdeng/stoa-infra` | `2b9aba9bb0ea62d2a39082da0eb5d9ead163317a` |

## AWS Identity

`aws sts get-caller-identity --profile stoa --region eu-central-2`:

- Account: `562923011260`
- ARN: `arn:aws:sts::562923011260:assumed-role/AWSReservedSSO_AdministratorAccess_6ef697b4f5015b7c/Deng_Zhiyuan`

## Lambda State

| Function | Runtime | CodeSize | LastModified | CodeSha256 | State | LastUpdateStatus | Reports bucket |
|----------|---------|----------|--------------|------------|-------|------------------|----------------|
| `stoa-api` | `python3.12` | `30300686` | `2026-06-04T16:11:52.000+0000` | `yiG2bIzRSnuk+tHzcxYmW8fyghWiiaaqBlsC3ssH+Ps=` | `Active` | `Successful` | `S3_REPORTS_BUCKET=stoa-reports-562923011260` |
| `stoa-weekly-report` | `python3.12` | `30300686` | `2026-06-04T16:11:59.000+0000` | `yiG2bIzRSnuk+tHzcxYmW8fyghWiiaaqBlsC3ssH+Ps=` | `Active` | `Successful` | `S3_REPORTS_BUCKET=stoa-reports-562923011260` |

## Automated Checks

| Check | Result |
|-------|--------|
| `uv run pytest tests/test_admin_report_ops.py tests/test_parent_children.py` | Passed: 89 tests passed. |
| `uv run ruff check src/stoa/routers/admin.py tests/test_admin_report_ops.py tests/test_parent_children.py` | Passed: all checks passed. |
| `uv run ruff check` | Failed on existing broad repo lint issues outside Phase 30 focused report operations scope; not treated as Phase 30 regression. |
| `curl https://api.stoaedu.ch/health` | HTTP 200 body `{"status":"ok","version":"0.1.0"}`. |
| Unauthenticated `GET https://api.stoaedu.ch/admin/reports/ops` | HTTP 401 body `{"message":"Unauthorized"}`. |
| Invalid-token `GET https://api.stoaedu.ch/admin/reports/ops` | HTTP 401. |
| Production login `POST /auth/login` for documented demo admin `admin@test.com / password123` | HTTP 401 body `{"detail":"No account found for this email. Please register first."}`. |
| Temporary admin verification account registration | HTTP 201 for `codex-admin-verify-20260604@stoaedu.ch`; returned user id `1351b045-3d3c-40ae-af31-4f18cb4c8410` and an access token. |
| Admin-authenticated `GET /admin/reports/ops?limit=5` with temporary admin token | HTTP 200; response `count=0`, `items=[]`, `next_token=true`, `access_pattern=bounded_scan`; no private artifact markers were found. |
| Admin-authenticated second page with returned `next_token` | HTTP 400 body `{"detail":"Invalid pagination token"}`. |

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

## Blocking Gaps

Phase 30 cannot fully pass until these are resolved:

- Fix or work around admin report ops bounded-scan pagination so an empty scan page does not return a `next_token` that `decode_page_token` rejects.
- Provide a safe report target row for admin-authenticated detail verification, or create a non-customer report fixture with cleanup.
- Provide a valid production non-admin token or approve a temporary non-admin verification account lifecycle for a valid non-admin rejection check.

Blocked or partial checks:

- Admin-authenticated `GET /admin/reports/ops?limit=5`: partial; auth and 200 response passed, pagination/empty-page behavior has a bug.
- Admin-authenticated detail `GET /admin/reports/{parent_id}/{student_id}/{week_start}/ops`: blocked; no safe target row available.
- Valid non-admin token rejection check: blocked; no production non-admin token available.

## Temporary Account Cleanup

Temporary admin verification account:

- Email: `codex-admin-verify-20260604@stoaedu.ch`
- User id: `1351b045-3d3c-40ae-af31-4f18cb4c8410`

Cleanup completed:

- `aws cognito-idp admin-delete-user --user-pool-id eu-central-2_Ss93YQzjJ --username codex-admin-verify-20260604@stoaedu.ch --profile stoa --region eu-central-2` - passed.
- `aws dynamodb delete-item --table-name stoa-main --key '{"PK":{"S":"USER#1351b045-3d3c-40ae-af31-4f18cb4c8410"},"SK":{"S":"PROFILE"}}' --profile stoa --region eu-central-2` - passed.
- Post-cleanup `admin-get-user` returned `UserNotFoundException`.
- Post-cleanup DynamoDB `get-item` returned no item.

## Stop Condition

Phase 31 mutation smoke must not run until Phase 30 admin-auth read-only list/detail checks pass, the pagination gap is resolved or accepted with a safe workaround, and a safe smoke target is documented.
