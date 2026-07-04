# Phase 239 Plan: Webhook Reconciliation And Entitlement Activation

**Milestone:** v5.13 Payment And Entitlement Production Completion
**Requirement:** PAYPROD-03
**Status:** Complete
**Date:** 2026-07-05

## Plan

1. Audit existing provider webhook and billing transition behavior.
2. Identify reconciliation gaps not covered by Phase 237/238 evidence.
3. Record duplicate provider deliveries in billing event history with `processingResult=deduplicated`.
4. Add stale-event detection using provider `created` timestamps versus current `last_provider_event_at`.
5. Record stale events as `processingResult=stale_ignored` while preserving current billing and entitlement state.
6. Extend focused backend tests for duplicate evidence and stale event ordering.
7. Run focused subscription tests and Ruff.

## Acceptance Criteria Mapping

| Acceptance Criteria | Result |
|---------------------|--------|
| Provider event identity, storage, reconciliation status, and entitlement activation are idempotent | Complete. Dedupe keys still prevent repeat mutation; duplicate deliveries now also emit support-visible dedup events. |
| Successful payment activates the correct linked-student entitlement exactly once | Complete. Existing invoice-paid path remains covered; duplicate invoice delivery does not reapply activation. |
| Duplicate, stale, failed, refunded, canceled, missing-context, and conflicting events are support-visible | Complete for duplicate, stale, failed, refunded, canceled/expired, and manual override interactions. Missing-context still fails explicitly with 400 and no raw provider payload exposure. |
| Entitlement state and usage-limit checks agree after reconciliation | Complete for backend contract coverage: active invoice-paid state updates parent profile tier and effective entitlements remain provider-backed. |
| Focused backend tests cover event ordering, duplicate delivery, stale state, missing context, and manual override interaction | Complete for local focused scope. Existing tests cover duplicate delivery, failed payment, refunds, checkout expiration, signature failures, and manual override; Phase 239 added stale event ordering evidence. |
