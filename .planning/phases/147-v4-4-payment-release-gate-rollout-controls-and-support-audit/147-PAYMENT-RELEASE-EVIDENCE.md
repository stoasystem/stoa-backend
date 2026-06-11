---
phase: 147
requirement: VERIFY-27
status: passed
captured_at: 2026-06-11
---

# v4.4 Payment Release Evidence

## Verification Commands

```bash
.venv/bin/python -m pytest tests/test_subscription_operations.py
.venv/bin/ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/routers/billing.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py
rg -n "status: (issues_found|failed)|Status:\\*\\* (issues_found|Failed|Planned)|Pending Phase" .planning/phases/144-live-payment-rollout-contract-and-credential-readiness .planning/phases/145-production-checkout-webhook-and-twint-capable-stripe-gating .planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff
```

## Results

- `tests/test_subscription_operations.py`: 17 passed.
- Focused ruff check: all checks passed.
- Phase 144-146 unresolved failure scan: no unresolved `issues_found`, failed, or pending phase artifacts found.

## Provider Configuration Evidence

- Phase 144 documents the required live credential path, webhook endpoint, product/price mapping, safe smoke modes, and rollback switches.
- Phase 145 implements redacted readiness states: `test`, `not_configured`, `live_ready_but_blocked`, and `live_enabled`.
- Production checkout fails closed unless live Stripe credentials, webhook secret, Standard/Premium price IDs, Stripe SDK availability, and `STRIPE_LIVE_CHARGES_ENABLED=true` are all present.
- Real customer charging remains deferred. No live provider mutation or real customer charge was executed in this milestone.

## Checkout And Webhook Evidence

- Checkout creation distinguishes local/test behavior from production live readiness and blocked live rollout.
- TWINT is included through Stripe Checkout when enabled, capability-confirmed, and live rollout gates allow it.
- Webhook verification uses Stripe SDK verification when available and requires webhook signing secrets by default.
- Entitlement activation is tied to authoritative invoice/subscription events rather than checkout completion.
- Webhook idempotency, provider lookup rows, livemode, processing result, and selected payment method context are persisted.

## Billing Operations Evidence

- Parent/admin billing responses include provider-hosted invoice/receipt metadata where Stripe supplies it.
- Refund readiness is non-mutating and exposes provider handoff state, required operator reason, eligible amount, currency, and provider references.
- Dunning projections expose active, retrying, payment-failed, recovered, cancelled, checkout-pending, none, and manual-review states.
- Swiss accounting handoff includes provider references, amounts, tax provider-managed status, period fields, invoice/receipt URLs, refund references, selected payment method, and reconciliation IDs.
- TWINT-originated lifecycle data flows through invoice, refund, dunning, and accounting projections in the same Stripe model.

## Release Decision

v4.4 is locally verified and ready to close as a controlled payment rollout foundation. Live customer charging is not approved by this evidence; it remains gated on external Stripe/TWINT/provider setup and explicit rollout approval.
