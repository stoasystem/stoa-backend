# Phase 260 Production Readiness Runbook

## New Release Endpoint

- Route: `GET /admin/external-activation/production-readiness-smoke`
- Role: admin only
- Mutation: none
- Purpose: metadata-only checklist for deploy evidence, read-only API smoke, read-only browser smoke, request IDs, and no-mutation policy.

## Deploy Evidence Required

Backend:

- Commit SHA.
- Deploy run ID.
- Lambda update status.
- Lambda configuration waiter status.
- Health endpoint status.

Frontend:

- Commit SHA.
- Deploy run ID.
- Asset build status.
- Hosting/CDN deploy status.
- Production URL.

Infra:

- IaC/CDK diff summary.
- Expected resource changes.
- IAM permission preflight.
- Rollback plan.

## Read-Only API Smoke

Run with an admin session and a unique `X-Request-Id` for each check:

- `GET /admin/core-smoke`
- `GET /admin/external-activation/payment-auth-smoke`
- `GET /admin/external-activation/notification-support-smoke`
- `GET /admin/subscriptions/billing/provider-readiness`
- `GET /admin/account-operations/parents/{parent_id}` with approved fixture identity only.
- `GET /admin/curriculum/analytics/dashboard`
- `GET /admin/notifications/delivery-status`
- `GET /admin/reports/support-handoff-sla`

## Read-Only Browser Smoke

Capture only redacted/operator-local screenshots:

- `/login`
- `/admin`
- `/admin/account-operations`
- `/admin/billing`
- `/admin/curriculum`
- `/admin/notifications`

## No-Mutation Policy

Production mutation is refused unless:

- An approved fixture name is present.
- An explicit mutation mode is present.
- Fixture status is ready or the mutation mode is cleanup/restore.
- Privacy denylist passes.

Use `release_evidence_service.mutation_refusal_reasons` as the backend refusal helper.
