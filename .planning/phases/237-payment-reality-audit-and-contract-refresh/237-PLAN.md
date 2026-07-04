# Phase 237 Plan: Payment Reality Audit And Contract Refresh

## Goal

Map current payment and entitlement reality and define the implementation contract for v5.13.

## Work Items

1. Audit backend payment routes and services.
   - Checkout/session creation.
   - Stripe webhook ingestion.
   - Provider event dedupe/reconciliation.
   - Entitlement resolution.
   - Refund/rollout/provider readiness.
   - Admin and parent billing APIs.

2. Audit frontend payment surfaces.
   - Legacy `/billing` page and billing hooks.
   - Parent subscription operations.
   - Admin subscription and account operations views.
   - Demo fallback boundaries.

3. Produce reality evidence table.
   - Implemented.
   - Stubbed/demo.
   - Locally verified.
   - Externally blocked.

4. Update v5.13 contract.
   - Identify Phase 238 first implementation target.
   - Preserve provider/manual entitlement distinction.
   - Keep live activation explicitly gated.

## Verification

- Documentation review against concrete backend/frontend files.
- Roadmap and requirement alignment.

## Exit Criteria

- v5.13 can proceed to implementation without confusing old readiness artifacts with working paid access.
