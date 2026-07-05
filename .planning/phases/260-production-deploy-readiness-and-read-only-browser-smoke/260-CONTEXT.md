# Phase 260 Context: Production Deploy Readiness And Read-Only Browser Smoke

## Scope

Phase 260 consolidates production deploy readiness and read-only smoke operations. It does not perform live browser login, AWS deploy, provider activation, or production mutation.

## Existing Surfaces

- Release evidence validation exists through `release_evidence_service`.
- Core product smoke exists at `GET /admin/core-smoke`.
- Provider activation smoke exists at:
  - `GET /admin/external-activation/payment-auth-smoke`
  - `GET /admin/external-activation/notification-support-smoke`
- Payment, account operations, usage, curriculum, notification, and support admin routes expose bounded read-only evidence.

## Decisions

- Add an admin-only production readiness smoke report that lists required deploy evidence, read-only API checks, read-only browser checks, request-id conventions, and no-mutation policy.
- Keep the endpoint metadata-only and deterministic.
- Treat production mutation as refused unless an approved fixture and explicit mutation mode are present.
- Use the report as the Phase 261 release-gate input rather than claiming production smoke was executed locally.

## Blocked-State Contract

- Non-production runtime returns `locally_ready`, not production-passed.
- Production runtime returns `read_only_verifiable` until operator records deploy/browser/API evidence.
- Mutation remains disabled by default in all states.
