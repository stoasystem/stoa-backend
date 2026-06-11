# Project Research Summary

**Project:** STOA Backend
**Domain:** Stripe-first live payment rollout for subscription billing in Switzerland
**Researched:** 2026-06-11
**Confidence:** MEDIUM

## Executive Summary

v4.4 is not a new payments platform build. It is a controlled rollout of STOA's existing v3.9 Stripe-first billing MVP into production-ready checkout, webhook, and billing-ops behavior using the current FastAPI app, DynamoDB single-table projection, and Stripe-hosted billing primitives. The correct implementation shape is Stripe Checkout + Billing + Webhooks + Invoices + Refunds, with TWINT included through Stripe as an in-scope payment method for this milestone rather than a separate PSP or a documentation-only consideration.

The recommended approach is to keep one billing domain and split the current flat subscription logic into focused services: readiness/gating, Stripe provider adapter, webhook processing, and billing operations. Phase 145 should establish real Stripe session creation, livemode-aware verification, webhook idempotency, provider ID lookup rows, and explicit rollout gating. Phase 146 should then add invoice/receipt visibility, refund lifecycle handling, tax/accounting export fields, dunning projection, and TWINT-capable subscription flow validation on top of those primitives. Phase 147 should package evidence, canary controls, and rollback discipline instead of inventing new billing state.

The highest risks are fail-open live/test crossover, granting entitlements on Checkout completion instead of paid invoice truth, brittle webhook processing, and calling TWINT "ready" without proven Stripe capability plus CHF/subscription validation. Mitigation is consistent across the research: fail closed, treat Stripe invoice/subscription state as source of truth, normalize provider metadata into STOA-owned projections, and keep TWINT inside Stripe dynamic payment methods behind explicit readiness and rollout flags.

## Key Findings

### Recommended Stack

The stack addition is narrow and clear: add the official Stripe Python SDK and use Stripe-hosted subscription primitives rather than inventing custom billing flows. Keep FastAPI, Lambda/API Gateway, and the existing DynamoDB billing projection. Keep secrets in AWS Secrets Manager-backed runtime config, and keep price mapping in Stripe with explicit test/live IDs. TWINT should be enabled through Stripe Checkout and Billing, not through a second integration.

**Core technologies:**
- `stripe-python~=15.2`: official Stripe API client and webhook verification path for real checkout, refunds, invoices, and subscriptions.
- Existing FastAPI + Lambda/API Gateway: retain `/parents/me/subscription/checkout`, `/billing/webhooks/stripe`, and admin billing routes as the rollout surface.
- Existing DynamoDB single-table model: store normalized billing summary, append-only events, provider lookup rows, readiness state, and operator evidence.
- AWS Secrets Manager-backed config: separate live credential presence from live charge enablement and keep rollback gating explicit.
- Stripe Checkout/Billing/Webhooks/Invoicing/Refunds/TWINT: provider primitives for subscriptions, invoices, receipts, dunning, refunds, and Swiss-local payment method support.

### Expected Features

The table-stakes expectation for a Stripe + TWINT live rollout is not just “can create a checkout link.” STOA needs safe live/test separation, production-verifiable checkout and webhook behavior, parent/admin invoice visibility, refund readiness, dunning visibility, accounting export fields, and explicit TWINT inclusion in the Stripe subscription flow. Research consensus is that TWINT is in scope for v4.4 rollout planning as a real payment-method capability to validate and gate, not merely a future note.

**Must have (table stakes):**
- Live-mode rollout gate and credential readiness with explicit `live_ready_but_blocked` vs `live_enabled` semantics.
- Real Stripe Checkout creation plus operator evidence for price, mode, session, and redirect outcome.
- Webhook authenticity, idempotency, event timeline, and provider-ID-based parent resolution.
- Parent/admin invoice and receipt visibility via Stripe-hosted artifacts and normalized metadata.
- Refund lifecycle readiness, not just a dashboard-only manual process.
- Dunning visibility with hosted recovery path and projected retry metadata.
- Tax/accounting handoff export with invoice, refund, tax, and reconciliation identifiers.
- TWINT-enabled subscription rollout readiness and validation through Stripe for CHF/Swiss flows.

**Should have (competitive):**
- Unified operator billing timeline across checkout, webhook, invoice, refund, and dunning events.
- Safe live-smoke flow with no-real-charge default and redacted evidence.
- Parent recovery UX that deep-links to hosted payment-method update/recovery actions.
- Controlled TWINT cohort rollout after capability and end-to-end proof.

**Defer (v2+):**
- Full ERP/accounting connector.
- Custom invoice PDFs, receipt rendering, or custom dunning engine.
- Separate TWINT SDK or multi-provider orchestration beyond Stripe-hosted TWINT.

### Architecture Approach

The architecture should remain a single billing domain inside the monolith, but with clearer boundaries. `subscription_service.py` stays as orchestration, while new focused services own readiness/gating, Stripe API I/O, webhook verification/projection, and billing operations. Stripe remains source of truth for payment execution; STOA keeps a local projection for entitlement, parent/admin visibility, support evidence, and export.

**Major components:**
1. `billing_readiness_service`: compute environment rollout state, verify config completeness, gate live checkout, and track TWINT capability state.
2. `payment_provider/stripe_gateway.py`: own all Stripe SDK calls for Checkout, refunds, invoices, customer/subscription reads, and webhook parsing.
3. `billing_webhook_service`: verify signatures, dedupe by event ID, resolve parent via lookup rows, and project invoice/subscription/refund state.
4. `billing_ops_service`: serve invoice/receipt links, refund readiness/action state, tax/export data, and dunning projections to parent/admin APIs.
5. Provider lookup and readiness rows in DynamoDB: replace scan-based mapping and store environment-scoped rollout evidence.

### Critical Pitfalls

1. **Fail-open test/live crossover** — refuse live checkout unless live keys, live webhook secret, live price IDs, production URLs, and rollback switch are all present and operator-approved.
2. **Granting access on `checkout.session.completed`** — drive entitlements from `invoice.paid` plus subscription truth, and handle `payment_action_required`, `past_due`, `unpaid`, and cancellation states explicitly.
3. **Operationally brittle webhooks** — verify raw-body signatures with the SDK, persist `livemode` and event IDs, dedupe safely, resolve parents without scans, and keep processing replay-safe.
4. **Missing provider linkage across async events** — persist customer, subscription, session, invoice, payment intent, charge, and refund IDs with lookup rows as soon as they exist.
5. **TWINT false readiness** — treat Dashboard enablement as insufficient; verify Stripe capability state, Swiss/CHF compatibility, merchant onboarding, and actual subscription Checkout presentation before calling rollout-ready.

## Implications for Roadmap

Based on research, Phases 145-147 should stay as the v4.4 build spine, but the milestone scope needs to be tightened around real Stripe primitives and explicit TWINT inclusion.

### Phase 145: Production Checkout, Webhook, and TWINT-Capable Provider Primitives
**Rationale:** Every downstream billing-ops feature depends on stable provider IDs, real Stripe session creation, livemode-aware gating, and reliable webhook projection.
**Delivers:** `stripe-python` integration, `billing_readiness_service`, `stripe_gateway`, raw-body SDK verification, provider lookup rows, enriched webhook/event evidence, admin readiness visibility, and Stripe Checkout subscription sessions configured so TWINT can be surfaced through Stripe when eligible.
**Addresses:** PAYLIVE-02 foundations, live/test gating, checkout verification, webhook idempotency, and the TWINT in-scope correction from “readiness note” to real rollout primitive.
**Avoids:** test/live crossover, wrong entitlement trigger, webhook scan resolution, and unsupported TWINT claims.

### Phase 146: Billing Operations, Invoices, Refunds, Dunning, and Swiss Handoff
**Rationale:** Once provider primitives are stable, STOA can safely project the post-checkout lifecycle for parents, admins, and finance.
**Delivers:** `billing_ops_service`, invoice/receipt links and metadata, refund state machine and operator evidence, tax/accounting export fields, dunning status/retry projection, and TWINT-specific validation/results folded into the same Stripe billing model.
**Uses:** Stripe invoices, refunds, hosted artifacts, Smart Retries, and existing DynamoDB summary/event patterns.
**Implements:** PAYLIVE-03 with no custom invoice engine, no custom retry scheduler, and no separate TWINT backend branch unless production validation proves Stripe Checkout insufficient.

### Phase 147: Release Gate, Canary Controls, and Scope Closure
**Rationale:** Payment rollout needs explicit approval, evidence, and rollback controls after the billing system is already built.
**Delivers:** redacted release evidence, webhook health proof, live-charge deferral or approval status, canary/allowlist controls, rollback switch verification, and updated roadmap/remaining-work docs.
**Addresses:** VERIFY-27 and the milestone closeout requirement to update roadmap and requirements based on what v4.4 actually ships.
**Avoids:** “works in test mode” false confidence, untracked live enablement, and unsupported claims that TWINT or refunds are production-ready without proof.

### Phase Ordering Rationale

- Phase 145 must come first because lookup rows, livemode truth, and real Checkout/Webhook wiring are hard dependencies for invoices, refunds, dunning, and TWINT validation.
- Phase 146 groups features that consume the same projected billing state: invoice visibility, refund handling, tax export, dunning, and Swiss-local payment method validation.
- Phase 147 stays a release gate, not a feature phase, because rollout evidence and rollback discipline only make sense after the billing surfaces exist.
- TWINT should be planned inside Phases 145-146, not deferred out of the milestone, because provider capability validation and live subscription presentation affect both checkout architecture and rollout evidence.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 145:** confirm exact Stripe Checkout/Dynamic Payment Method configuration for TWINT subscription presentation in STOA's target account and environment.
- **Phase 146:** validate the minimum Swiss accounting export contract and whether Stripe-hosted invoices plus exported metadata are sufficient for finance.

Phases with standard patterns (skip research-phase):
- **Phase 147:** release evidence, rollback switch, and canary gating follow established STOA operational patterns.

### Explicit v4.4 Scope Updates

- Update `PAYLIVE-01` to remove the old ambiguity about whether TWINT is implementation scope. v4.4 should explicitly state that TWINT is in-scope as a Stripe-backed payment method for rollout planning and validation.
- Update `PAYLIVE-02` so production checkout verification includes proving that Stripe Checkout is configured to surface TWINT for eligible Swiss/CHF subscription flows when the provider/account state allows it.
- Update `PAYLIVE-03` so parent/admin billing projections and finance exports remain provider-agnostic within Stripe, including TWINT-originated subscriptions/refunds through the same invoice/refund surfaces.
- Update roadmap wording for Phases 145-146 so TWINT is grouped with payment-provider primitives and billing operations, not parked as a later “production-readiness doc” item.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Built mostly on official Stripe docs plus direct fit with existing STOA backend seams. |
| Features | MEDIUM | Strong product consensus, but some TWINT rollout details depend on actual Stripe account capability and finance workflow choices. |
| Architecture | MEDIUM | The monolith-with-service-split pattern is well justified by the codebase, though exact component boundaries still need implementation judgment. |
| Pitfalls | MEDIUM | Risks are credible and specific, but a few mitigations depend on production validation rather than code inspection alone. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **TWINT account reality:** verify STOA's Stripe account capability state, Swiss merchant onboarding status, and live/test eligibility before treating TWINT as launchable.
- **Finance handoff contract:** confirm with Swiss accounting stakeholders whether Stripe-hosted invoice artifacts plus exported metadata are enough for month-end reconciliation.
- **Entitlement policy details:** lock the exact access policy for `incomplete`, `past_due`, `unpaid`, refunded, and manually overridden subscriptions before Phase 146 UI/API work.
- **Webhook event set:** confirm the final subscribed event list, especially `invoice.updated` and refund-related events, against the chosen Stripe Billing/Recovery configuration.

## Sources

### Primary (HIGH confidence)
- `.planning/research/STACK.md` — provider primitives, SDK choice, TWINT-through-Stripe recommendation, and rollout config patterns.
- `.planning/research/ARCHITECTURE.md` — service boundaries, build order for Phases 145-147, and DynamoDB lookup/readiness patterns.
- Official Stripe docs cited in the research set — Checkout, Webhooks, Billing, TWINT, Refunds, Invoices, Smart Retries, and Dynamic Payment Methods.

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` — table-stakes billing expectations, rollout sequencing, and operator/parent workflow implications.
- `.planning/research/PITFALLS.md` — rollout failure modes, warnings, and prevention strategies.
- `.planning/PROJECT.md` and `.planning/REQUIREMENTS.md` — milestone framing, current scope, and existing Phase 145-147 mapping.

---
*Research completed: 2026-06-11*
*Ready for roadmap: yes*
