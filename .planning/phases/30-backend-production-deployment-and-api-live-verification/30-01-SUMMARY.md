---
plan_id: 30-01
phase: 30
phase_name: Backend Production Deployment and API Live Verification
status: gaps_found
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

## Blocked

Production admin-authenticated read-only API checks did not run because no production admin token was available.

The documented demo admin account `admin@test.com / password123` is not present in production; `/auth/login` returned HTTP 401 with `No account found for this email. Please register first.`

## Next

Do not run Phase 31 mutation smoke yet. First provide or create an approved safe production admin verification path, then rerun Phase 30 admin-auth read-only checks.
