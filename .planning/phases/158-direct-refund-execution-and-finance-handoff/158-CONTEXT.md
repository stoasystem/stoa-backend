# Phase 158 Context: Direct Refund Execution And Finance Handoff

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Source:** Autonomous from Phase 156 contract and Phase 157 implementation

<domain>
## Phase Boundary

Phase 158 adds controlled admin direct refund execution and finance handoff updates for existing Stripe-backed billing records. It must not loosen live checkout gates and must not execute refunds unless an explicit refund gate is enabled.
</domain>

<decisions>
## Locked Decisions

- Direct refunds require admin authorization through existing admin route dependencies.
- Refund execution requires an eligible billing state, provider payment reference, positive amount, operator reason, idempotency key, and explicit refund gate.
- TWINT refunds must respect a 180-day refund window when the payment method is TWINT and payment timing evidence exists.
- Provider refund mutation must go through a dedicated seam so tests can verify behavior without live Stripe calls.
- Provider failures must not update billing as successful.
- Finance handoff must include refund result, provider reference, amount, currency, reason, idempotency key, operator, and timestamps.
</decisions>

<canonical_refs>
## Canonical References

### Planning
- `.planning/phases/156-payment-production-activation-contract-and-provider-readiness/156-PAYMENT-ACTIVATION-CONTRACT.md` - Direct refund contract.
- `.planning/phases/157-live-provider-readiness-api-checks/157-01-SUMMARY.md` - Readiness endpoint leaves refund mutation disabled.
- `.planning/REQUIREMENTS.md` - PAYACT-03 acceptance criteria.

### Implementation
- `src/stoa/config.py` - Add refund execution gate.
- `src/stoa/services/subscription_service.py` - Existing refund projection, accounting handoff, provider lookup, and billing event logic.
- `src/stoa/routers/admin.py` - Admin billing endpoints.
- `tests/test_subscription_operations.py` - Payment operation tests and fake table.
</canonical_refs>

<specifics>
## Specific Implementation Notes

- Add `stripe_refunds_enabled`, default false.
- Add `POST /admin/subscriptions/billing/{parent_id}/refunds`.
- Persist idempotency state before the provider call when possible.
- Use Charge ID when present, otherwise PaymentIntent ID.
- Return the updated admin billing response plus idempotency status.
- Extend accounting handoff refund shape rather than creating a separate export endpoint.
</specifics>

<deferred>
## Deferred Ideas

- Runtime-editable rollout controls are Phase 159.
- Live activation state closeout is Phase 160.
</deferred>

---

*Phase: 158-direct-refund-execution-and-finance-handoff*
*Context gathered: 2026-06-12 via autonomous mode*
