# Next Product Milestones

**Updated:** 2026-07-03 after completing v5.10 frontend account operations readiness
**Mode:** final polish, product functionality first

## Current Reality

v5.6-v5.9 are complete local backend milestones:

- v5.6 made paid entitlement effective for linked-student question quota.
- v5.7 added privacy-safe question usage ledger events, idempotency, and reconciliation.
- v5.8 added Cognito-backed email verification lifecycle and explicitly deferred unsupported passwordless login-code behavior.
- v5.9 added parent/admin account operations aggregation APIs.

v5.10 has now closed the frontend and production-readiness gap for email verification, parent account operations, and admin account operations.

## Completed: v5.10 Account Operations Frontend And Production Readiness

**Status:** Completed local frontend/readiness release gate 2026-07-03
**Roadmap:** `.planning/ROADMAP.md`
**Requirements:** `.planning/REQUIREMENTS.md`
**Milestone roadmap:** `.planning/milestones/v5.10-ROADMAP.md`
**Milestone requirements:** `.planning/milestones/v5.10-REQUIREMENTS.md`

Purpose:

- Make email verification usable in the web frontend.
- Make parent account operations visible through a parent UI surface.
- Make admin parent account operations inspectable through a support console.
- Prepare production read-only smoke for account operations and verification paths.

Completed build scope:

- Phase 222: Reality Refresh And Frontend Account Operations Contract. (complete)
- Phase 223: Email Verification UX Integration. (complete)
- Phase 224: Parent Account Operations UI. (complete)
- Phase 225: Admin Account Operations Console. (complete)
- Phase 226: v5.10 Frontend And Production Readiness Gate. (complete)

## Active: v5.11 Additional Usage Ledger Coverage

**Status:** Recommended next milestone

Purpose:

- Extend usage ledger beyond question submissions only.
- Cover chat, hints, teacher-help requests, and any practice/generation action that affects paid limits or support explanations.
- Keep existing question quota enforcement stable.

Likely build scope:

- Contract for governed action taxonomy and idempotency.
- Ledger instrumentation for chat/hints/teacher-help/practice generation.
- Reconciliation or summary behavior per action.
- Parent/admin usage UI handoff updates.

## Planned: v5.12 Next Product Expansion Selection

**Status:** Planned decision after v5.10/v5.11 reality

Candidate directions:

- Native/mobile account operations client.
- Rich curriculum editor frontend implementation.
- Production content import and migration UI/API.
- Live warehouse/BI deployment.
- Final external payment/support/notification activation when prerequisites unblock.

## Deferred External Activation

- Final live Stripe/TWINT charging still needs approved live credentials, registered production webhook endpoint, TWINT approval, finance acceptance, and explicit rollout enablement.
- Real external support provider and CRM/customer messaging still need approved provider selection, credentials, destination policy, templates, and rollout approval.
- Live notification provider/native push activation remains outside the v5.10 web account operations scope.
