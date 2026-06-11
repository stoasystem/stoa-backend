---
phase: 147
status: complete
captured_at: 2026-06-11
---

# Remaining Payment Work Audit

## Closed In v4.4

- Live payment rollout contract and credential readiness.
- Stripe-backed TWINT inclusion in rollout requirements and Checkout eligibility.
- Production checkout gating with fail-closed live readiness states.
- Stripe SDK dependency and webhook verification path.
- Provider lookup rows for key Stripe object IDs.
- Invoice/receipt metadata projection.
- Non-mutating refund readiness and refund lifecycle projection.
- Dunning/payment failure/recovery projection.
- Swiss accounting handoff metadata and read-only export.
- Focused backend release-gate evidence.

## Still Blocked Externally

- Approved Stripe live API key, webhook secret, and live price IDs.
- Production Stripe webhook endpoint registration and dashboard configuration.
- Stripe account confirmation that TWINT is enabled for the target Swiss/CHF subscription flow.
- Explicit business approval to set `STRIPE_LIVE_CHARGES_ENABLED=true`.
- Finance acceptance that Stripe-hosted invoice artifacts plus exported metadata satisfy Swiss accounting handoff needs.

## Future Payment Work

- Direct provider refund execution with explicit operator approval, reason capture, failure handling, and audit trail.
- Broader accounting destination integration after finance destination/credential approval.
- Provider-dashboard/readiness API reads for live price/product/TWINT capability validation.
- Expanded dunning automation, parent messaging, and support ticket handoff.
- Multi-provider billing automation beyond Stripe/TWINT basics.

## Next Milestone Recommendation

Proceed to v4.5 Support Evidence Integrations And Operations Handoff. Payment support work now has operator-visible billing/accounting metadata, and the next highest remaining product gap is approved support destination integration.
