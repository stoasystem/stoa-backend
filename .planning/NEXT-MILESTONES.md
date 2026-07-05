# Next Product Milestones

**Updated:** 2026-07-05 after completing v5.18 BI observability
**Mode:** external activation, operations, analytics, and native client implementation

## Current Reality

Completed local milestones:

- v5.12 implemented curriculum editor/content migration.
- v5.13 completed local payment/entitlement production readiness.
- v5.15 completed usage/quota/product stability.
- v5.16 completed end-to-end local product readiness: focused frontend e2e, supplemental journeys, backend product-readiness tests, frontend build/lint, and release evidence.
- v5.17 completed external provider activation smoke and release operations.
- v5.18 completed local BI observability contracts for aggregate exports, dashboards, and alert routing.

Remaining blockers are primarily external activation and client expansion:

- Live Stripe/TWINT charging and webhook activation.
- Live Cognito/email delivery smoke.
- Notification provider and push/native activation.
- External support provider and CRM/customer messaging approval.
- BI/warehouse/APM activation.
- Native/mobile app implementation and app-release prerequisites.

## Completed: v5.17 External Provider Activation Smoke And Release Operations

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.17-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.17-REQUIREMENTS.md`

Purpose:

- Convert external blockers into approved readiness, smoke, refusal, rollback, and release-operation evidence.
- Cover payment, Cognito/email, notifications, support provider handoff, and production deploy/read-only smoke.
- Close honestly as live-passed, read-only-passed, safe-fixture-passed, locally ready, or blocked with exact prerequisites.

## Completed: v5.18 Warehouse BI Observability And Product Analytics Activation

Roadmap: `.planning/milestones/v5.18-ROADMAP.md`
Requirements: `.planning/milestones/v5.18-REQUIREMENTS.md`

Purpose:

- Activate aggregate warehouse/BI exports, operator dashboards, APM/alerts, and analytics runbooks.
- Use v5.17 provider-state dimensions so dashboards separate live, blocked, read-only, safe-fixture, and local-only behavior.
- Preserve privacy boundaries and support-safe metadata.

## Active Next: v5.19 Native Mobile Push And Offline Client Implementation

Roadmap: `.planning/milestones/v5.19-ROADMAP.md`
Requirements: `.planning/milestones/v5.19-REQUIREMENTS.md`

Purpose:

- Implement a real native/mobile client after web product readiness and provider/analytics boundaries are explicit.
- Cover auth/session, parent/student journeys, native push, notification deep links, offline/read-through behavior, localization, and app-release evidence.

## Ordering Rationale

1. v5.17 completed first because local product readiness was complete but external activation state was the largest uncertainty.
2. v5.18 completed second because analytics and alerts needed stable provider/product-state dimensions.
3. v5.19 is next because native/mobile should inherit stable web contracts, provider state, observability, and notification boundaries.
