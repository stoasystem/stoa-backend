# Phase 100 Context: Subscription Operations Contract And Entitlement Model

**Milestone:** v3.3 Subscription Operations MVP
**Requirement:** SUBOPS-01
**Status:** Planned

## Why This Phase Exists

`stoa_docs` says MVP payments are manual: parents contact STOA, admins update `subscription_tier`, and transfers happen outside the product. The backend already has subscription tiers that drive daily quota, but there is no complete parent request/admin processing workflow. Phase 100 defines that workflow before backend/UI implementation.

## Product Scope

- Parent plan view and request intent: upgrade, downgrade, cancellation.
- Admin queue and processing workflow.
- Entitlements for Free, Standard, Premium.
- Manual billing status tracking without Stripe/TWINT integration.

## Completion Criteria

Phase 100 completes when the subscription request contract, entitlement model, API plan, UI workflow, and lightweight verification checklist are written and internally consistent.
