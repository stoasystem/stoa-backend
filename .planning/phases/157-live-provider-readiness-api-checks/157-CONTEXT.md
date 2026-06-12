# Phase 157 Context: Live Provider Readiness API Checks

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Source:** Autonomous from Phase 156 accepted activation contract

<domain>
## Phase Boundary

Phase 157 adds admin-only, read-only provider readiness checks for Stripe/TWINT production activation. The implementation must not create real charges, Checkout Sessions, PaymentIntents, subscriptions, refunds, or customer records.
</domain>

<decisions>
## Locked Decisions

- Provider readiness must use the existing subscription billing service and admin router patterns.
- The readiness endpoint must be admin-only.
- The response must redact secrets and raw provider payloads.
- Missing credentials, test-mode production credentials, live-ready-but-blocked, provider API failure, TWINT pending/inactive, and readiness success must be distinguishable.
- TWINT must be included in readiness with CHF, Switzerland, 5,000 CHF maximum, recurring support, no manual capture, 180-day refund window, merchant onboarding, and `twint_payments` capability status.
- Provider API checks may call Stripe account and price retrieval seams only; no mutating provider API calls are allowed.
</decisions>

<canonical_refs>
## Canonical References

### Planning
- `.planning/phases/156-payment-production-activation-contract-and-provider-readiness/156-PAYMENT-ACTIVATION-CONTRACT.md` - Defines required readiness contract and safety boundary.
- `.planning/research/SUMMARY.md` - Captures official Stripe/TWINT, refund, and webhook research.
- `.planning/REQUIREMENTS.md` - PAYACT-02 acceptance criteria.
- `.planning/ROADMAP.md` - Phase 157 success criteria.

### Implementation
- `src/stoa/config.py` - Payment provider settings.
- `src/stoa/services/subscription_service.py` - Billing readiness, checkout, webhook, refund projection, and accounting handoff logic.
- `src/stoa/routers/admin.py` - Admin subscription billing endpoints.
- `tests/test_subscription_operations.py` - Existing payment readiness, checkout, webhook, refund projection, and accounting tests.
</canonical_refs>

<specifics>
## Specific Implementation Notes

- Extend local config with a public webhook endpoint URL for readiness only.
- Add provider adapter seams for Stripe account capability lookup and price lookup so tests can monkeypatch without the live Stripe SDK.
- Keep checkout creation behavior unchanged.
- Prefer a response shape that exposes `state`, `checkoutAllowed`, `refundsAllowed`, `providerMode`, `credentials`, `prices`, `twint`, `webhook`, `finance`, `rollout`, `blockers`, and `warnings`.
- Use existing provider event storage to compute last-observed webhook evidence when available.
</specifics>

<deferred>
## Deferred Ideas

- Direct refund mutation is Phase 158.
- Runtime-editable rollout controls are Phase 159.
- Final activation status and feature-gap update are Phase 160.
</deferred>

---

*Phase: 157-live-provider-readiness-api-checks*
*Context gathered: 2026-06-12 via autonomous mode*
