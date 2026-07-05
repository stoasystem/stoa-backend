# Next Product Milestones

**Updated:** 2026-07-05 after completing v5.15 usage/quota/product stability
**Mode:** internal development, product functionality and stability first

## Current Reality

Completed local milestones:

- v5.12 implemented backend and frontend curriculum editor/content migration tooling for backend-authorized curriculum operators.
- v5.13 completed local payment and entitlement production-readiness work, including canonical parent billing state, checkout integration, webhook reconciliation hardening, and admin billing support evidence.
- v5.15 completed local usage/quota/product stability, including usage-flow mapping, ledger/idempotency closure, quota reconciliation explanations, and admin core smoke evidence.

Partial gate:

- v5.14 verification/login reliability passed backend and frontend build gates, but focused frontend e2e remains blocked by platform usage-limit approval.

External blockers still explicit:

- Live Stripe/TWINT charging, production webhook registration, finance acceptance, live Cognito/email smoke, notification provider activation, external support provider activation, BI/warehouse, APM, native app provider work, and production deploy/live smoke.

## Active: v5.16 End-To-End Product Readiness And Release Evidence

Roadmap: `.planning/ROADMAP.md`
Requirements: `.planning/REQUIREMENTS.md`
Milestone roadmap: `.planning/milestones/v5.16-ROADMAP.md`
Milestone requirements: `.planning/milestones/v5.16-REQUIREMENTS.md`

Purpose:

- Verify the real product across auth, verification, billing, entitlement, usage/quota, curriculum, teacher help, and parent/admin support surfaces.
- Close or precisely classify the residual v5.14 focused frontend e2e blocker.
- Consolidate backend smoke, frontend e2e, and milestone evidence into one release-readiness matrix.
- Separate local implementation gaps from external provider blockers.

Planned build scope:

- Phase 252: Product Readiness Reality Audit And Evidence Contract. (active)
- Phase 253: Focused Frontend E2E Gate Closure.
- Phase 254: Backend Product Smoke Evidence Expansion.
- Phase 255: Cross-Surface Product Journey Verification.
- Phase 256: v5.16 Release Evidence Gate And Next Milestone Decision.

## Planned After v5.16

Candidate directions should be selected after the v5.16 evidence matrix:

- **External Provider Activation Smoke**: live Stripe/TWINT, Cognito/email, notification, and support provider smoke when credentials and approvals exist.
- **Warehouse/BI Activation**: deploy aggregate analytics only after product semantics and release evidence are stable.
- **Native/Mobile Implementation**: revisit after web product readiness and external-provider blockers are explicit.
- **Frontend Experience Polish**: only if v5.16 journey verification finds product-facing UX gaps that block internal use.
