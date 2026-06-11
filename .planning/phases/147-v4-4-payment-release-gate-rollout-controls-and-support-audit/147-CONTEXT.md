# Phase 147 Context: v4.4 Payment Release Gate, Rollout Controls, And Support Audit

## Why This Phase Exists

Phases 144 through 146 built the controlled live-payment rollout foundation: live credential/readiness contract, Stripe/TWINT checkout and webhook gating, and billing operations projections for invoices, refunds, dunning, and Swiss accounting handoff.

Phase 147 closes v4.4 by collecting release evidence, verifying rollback/disable controls, updating planning docs, and explicitly listing unresolved live-payment blockers before the milestone can be considered complete.

## Current Foundation

- Phase 144 defined the live rollout contract, credential path, TWINT inclusion, safe smoke modes, and rollback switches.
- Phase 145 added fail-closed readiness states, Stripe SDK wiring, TWINT-capable Checkout configuration, authoritative webhook entitlement behavior, provider lookup rows, and signed webhook defaults.
- Phase 146 added parent/admin invoice metadata, non-mutating refund handoff, dunning projections, Swiss accounting export metadata, and TWINT lifecycle propagation.

## Release-Gate Boundaries

- No real customer charge should be executed in this phase.
- Live charging remains deferred unless approved provider credentials, TWINT capability, webhook endpoint registration, finance acceptance, and explicit rollout approval are all present.
- Verification should prefer local/focused backend evidence and redacted provider-readiness evidence.

## Required Closeout Outputs

- Focused backend test/static-check evidence.
- Provider configuration and live-charge gate evidence.
- Checkout, webhook, billing operations, refund, dunning, and accounting handoff evidence.
- Rollback/disable controls audit.
- Updated requirements, roadmap, state, milestone history, and remaining feature queue.
- Remaining payment blockers and next milestone recommendation.
