---
plan_id: 30-01
phase: 30
phase_name: Backend Production Deployment and API Live Verification
status: passed_after_remediation
completed: 2026-06-04
requirements:
  - REL-01
  - REL-03
  - LIVE-01
  - LIVE-02
  - LIVE-04
  - VERIFY-02
---

# Plan 30-01 Summary: Backend Production Deployment and API Live Verification

## Completed

Verified the parts of backend production deployment that can be safely automated without a production admin token:

- AWS SSO profile `stoa` identity works for account `562923011260`.
- `stoa-api` is `Active`, `LastUpdateStatus=Successful`, and has `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- `stoa-weekly-report` is `Active`, `LastUpdateStatus=Successful`, and has `S3_REPORTS_BUCKET=stoa-reports-562923011260`.
- Both Lambdas share code SHA `yiG2bIzRSnuk+tHzcxYmW8fyghWiiaaqBlsC3ssH+Ps=`.
- Focused backend tests passed: 89 tests.
- Focused ruff passed.
- Production API `/health` returned HTTP 200.
- Unauthenticated and invalid-token report operations requests returned HTTP 401.
- CDK diff showed only expected Lambda `Code.S3Key` asset hash drift in `StoaApiStack`; no unexpected IAM, bucket, API route, DynamoDB, or policy drift was reported.

## Remediated

Production admin authentication was established with a temporary verification account, then cleaned up.

The documented demo admin account `admin@test.com / password123` is not present in production; `/auth/login` returned HTTP 401 with `No account found for this email. Please register first.`

After creating temporary admin account `codex-admin-verify-20260604@stoaedu.ch`, `GET /admin/reports/ops?limit=5` returned HTTP 200. The response was metadata-only, but it returned `count=0`, `items=[]`, and `next_token=true`; using that token returned HTTP 400 `Invalid pagination token`.

The pagination gap was fixed in backend commit `278a15e fix: allow admin report scan pagination tokens`. Production retest returned HTTP 200 for both the first bounded-scan page and the second page with the returned scoped `admin_reports` token.

A safe non-customer `codex-phase31-*` fixture completed admin detail verification, and a temporary valid parent token completed non-admin rejection verification with HTTP 403.

The temporary admin/parent Cognito users, DynamoDB fixture records, and S3 artifacts were deleted after verification. Post-cleanup checks confirmed Cognito `UserNotFoundException`, no DynamoDB item, and S3 404.

## Next

Proceed to Phase 31 mutation smoke using safe non-customer fixtures only.
