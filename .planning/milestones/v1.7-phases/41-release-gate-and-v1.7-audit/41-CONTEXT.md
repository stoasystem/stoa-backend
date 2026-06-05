# Phase 41 Context

**Phase:** 41 - Release Gate And v1.7 Audit
**Milestone:** v1.7 Recovery Evidence Export & Admin Credential Operations
**Created:** 2026-06-05
**Status:** Complete

## Inputs

- Phase 38 defined production admin credential operations and the metadata-only export contract.
- Phase 39 implemented admin-only `GET /admin/reports/recovery-evidence`.
- Phase 40 added read-only export controls to `/admin/report-operations` and completed local browser smoke.
- Backend deploy workflow updates Lambda code directly from GitHub Actions.
- Frontend deploy workflow builds production config, syncs S3, uploads no-cache `index.html`, and invalidates CloudFront.

## Release Gate Scope

Phase 41 closes v1.7 by proving:

- Lambda build provenance and deployed Lambda runtime state.
- Backend and frontend deploy evidence for the Phase 39/40 changes.
- Admin-only API authorization, bounds, request IDs, and privacy boundary.
- Cognito `admins` group membership for the long-lived production admin account.
- Production browser smoke of the evidence export UI using the secret-backed credential path.
- No production recovery mutation during smoke.
- Final milestone audit and archive readiness.

## Production Safety Boundary

Allowed:

- `GET /health`
- `GET /admin/reports/recovery-evidence`
- `GET /admin/reports/recovery-jobs`
- `GET /admin/reports/ops`
- Cognito/Secrets Manager metadata and login checks needed to authenticate the long-lived admin user.

Blocked:

- Retry generation.
- Resend email.
- Bulk resend.
- Create/cancel recovery job.
- S3 artifact reads/writes.
- Report state mutation.

