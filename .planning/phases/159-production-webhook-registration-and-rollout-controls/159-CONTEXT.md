# Phase 159 Context: Production Webhook Registration And Rollout Controls

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Source:** Autonomous from Phase 156 contract, Phase 157 readiness, and Phase 158 refunds

<domain>
## Phase Boundary

Phase 159 adds production webhook readiness evidence and admin rollout controls for checkout and refunds. It must preserve existing billing visibility and must only gate new live-changing operations.
</domain>

<decisions>
## Locked Decisions

- Rollout controls must be admin-visible and persisted.
- Checkout and refund rollout states must be independent.
- Supported rollout states are `disabled`, `canary`, `enabled`, and `rolled_back`.
- Checkout/refund execution must use effective rollout state, not only static config flags.
- Webhook readiness must expose HTTPS endpoint mode, signing secret availability, required event subscriptions, quick-ack expectation, and last observed provider event.
- Rollback disables new live-changing operations while preserving existing billing records, refund history, and finance exports.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/phases/156-payment-production-activation-contract-and-provider-readiness/156-PAYMENT-ACTIVATION-CONTRACT.md` - Rollout and webhook contract.
- `.planning/phases/157-live-provider-readiness-api-checks/157-01-SUMMARY.md` - Provider readiness endpoint.
- `.planning/phases/158-direct-refund-execution-and-finance-handoff/158-01-SUMMARY.md` - Direct refund gate and execution path.
- `.planning/REQUIREMENTS.md` - PAYACT-04 acceptance criteria.
- `src/stoa/services/subscription_service.py` - Readiness, checkout, refund, webhook, and billing service logic.
- `src/stoa/routers/admin.py` - Admin billing endpoints.
- `tests/test_subscription_operations.py` - Payment operation tests.
</canonical_refs>

<deferred>
## Deferred Ideas

- Final release state and feature-gap update are Phase 160.
</deferred>

---

*Phase: 159-production-webhook-registration-and-rollout-controls*
*Context gathered: 2026-06-12 via autonomous mode*
