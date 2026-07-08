# Roadmap: v6.2 Paid Conversion Usage And Account Reliability Completion

**Status:** Completed
**Created:** 2026-07-07
**Prior milestone:** v6.1 First Cohort Product Remediation Sprint

## Goal

Complete the business-critical parent account and paid access loop: checkout/paywall, entitlement activation, usage ledger, quota reconciliation, verification, lifecycle messaging, billing support, and self-serve account reliability.

## Function Purpose

- Make paid STOA access understandable and reliable for real parents.
- Remove ambiguity around who has access, what was used, what is blocked, and what support can fix.
- Prepare controlled growth without billing/account confusion.

## Implementation Strategy

- Use v6.0/v6.1 evidence and support tickets as priority input.
- Reconcile billing provider state, entitlement state, usage ledger state, quota display, and admin/support state.
- Keep customer-visible copy simple and support-visible.
- Treat revenue-impacting changes as auditable and reversible.

## Phases

- [x] **Phase 382: Paid Conversion Flow Completion** - Finish package, checkout, paywall, entitlement activation, failure, cancellation, renewal, invoice, and refund states for pilot scope.
- [x] **Phase 383: Usage Ledger And Quota Reliability Completion** - Close usage recording, idempotency, quota display, reconciliation, and parent/admin explanations across learning actions.
- [x] **Phase 384: Verification Lifecycle And Account Recovery Completion** - Complete email verification, login-code policy, resend/confirm, recovery, and support-visible account status.
- [x] **Phase 385: Billing Support And Lifecycle Messaging Completion** - Complete support macros, billing operations, lifecycle messages, preferences, failed delivery, and retention reporting.
- [x] **Phase 386: v6.2 Revenue Reliability Gate** - Decide controlled growth, hold, or further account/revenue remediation.

## Phase Details

### Phase 382: Paid Conversion Flow Completion

**Goal**: Complete package, checkout, paywall, entitlement activation, renewal, cancellation, failed payment, invoice, and refund states for pilot scope.
**Depends on**: v6.1 remediation release gate.
**Requirements**: V6REV-01
**Success Criteria**:

1. Package, checkout, payment method, paywall, entitlement activation, renewal, cancellation, failed payment, invoice, and refund states work for approved pilot scope.
2. Parent-facing copy explains access, limits, failures, and next action.
3. Provider events are reconciled without storing secrets or raw provider payloads.
4. Admin/support can explain paid state without private student content.

### Phase 383: Usage Ledger And Quota Reliability Completion

**Goal**: Close usage recording, idempotency, quota display, reconciliation, and parent/admin explanations across learning actions.
**Depends on**: Phase 382.
**Requirements**: V6REV-02
**Success Criteria**:

1. Usage ledger covers pilot-critical learning actions with idempotent writes.
2. Quota display and blocking behavior match entitlement state.
3. Parent/admin explanations show usage and remaining access clearly.
4. Reconciliation catches missing, duplicate, stale, and manually adjusted records.

### Phase 384: Verification Lifecycle And Account Recovery Completion

**Goal**: Complete email verification, login-code/passwordless policy, resend/confirm, recovery, support override, and account-state transitions.
**Depends on**: Phase 383.
**Requirements**: V6REV-03
**Success Criteria**:

1. Email verification, login-code/passwordless policy, resend/confirm, expiry, recovery, and support override behavior are explicit and tested.
2. Edge states have clear user copy and admin/support status.
3. Verification codes, tokens, and secrets are never exposed in logs or evidence.
4. Role and account state transitions are auditable.

### Phase 385: Billing Support And Lifecycle Messaging Completion

**Goal**: Complete billing support workflows and approved lifecycle messaging needed before controlled growth.
**Depends on**: Phase 384.
**Requirements**: V6REV-04
**Success Criteria**:

1. Billing support workflows cover failed payment, refund, invoice, subscription change, entitlement mismatch, usage dispute, and account recovery.
2. Lifecycle messages cover onboarding, activation, renewal, failed payment, reminder, cancellation, and win-back states where approved.
3. Preferences, locale, delivery failure, and support visibility are handled.
4. Support capacity gates remain explicit before growth expansion.

### Phase 386: v6.2 Revenue Reliability Gate

**Goal**: Decide controlled growth, hold, or further account/revenue remediation from current reliability evidence.
**Depends on**: Phase 385.
**Requirements**: VERIFY-76
**Success Criteria**:

1. Decision is controlled growth, hold, or further account/revenue remediation.
2. Decision uses billing drift, entitlement mismatch, usage accuracy, verification success, support load, and parent comprehension evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.3 receives learning/product-quality risks separately from billing/account risks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6REV-01 | Phase 382 | Completed |
| V6REV-02 | Phase 383 | Completed |
| V6REV-03 | Phase 384 | Completed |
| V6REV-04 | Phase 385 | Completed |
| VERIFY-76 | Phase 386 | Completed |
