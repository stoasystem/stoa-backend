# Roadmap: v6.7 Revenue Retention And Controlled Growth Execution

**Status:** Completed
**Created:** 2026-07-09
**Prior milestone:** v6.6 First Cohort Live Operations And Fix Sprint

## Goal

Convert pilot usage into a reliable paid/retention loop and a controlled growth decision. v6.7 focuses on checkout/paywall, entitlement, quota, lifecycle messaging, retention, support load, referral/waitlist intake, and revenue reconciliation under real cohort conditions.

## Function Purpose

- Prove that STOA can charge, explain access, support billing issues, and retain parents without manual confusion.
- Prepare controlled growth only if support and revenue operations can handle it.
- Keep paid marketing out of scope until real conversion and retention evidence support it.

## Implementation Strategy

- Use v6.5-v6.6 cohort evidence and support tickets.
- Reconcile provider, entitlement, usage, quota, invoice/refund, lifecycle, and support states.
- Run growth intake behind capacity and support gates.
- Close with controlled growth, hold, remediation, or rollback.

## Phases

- [x] **Phase 407: Paid Conversion And Billing Reality Review** - Review checkout, paywall, payment method, entitlement, invoice, refund, failed payment, and subscription evidence.
- [x] **Phase 408: Usage Quota And Parent Account Reliability Fixes** - Fix usage/quota/account explanations, reconciliation drift, support visibility, and parent self-serve reliability.
- [x] **Phase 409: Lifecycle Retention And Support Capacity Execution** - Execute onboarding, activation, renewal, reminder, failed payment, cancellation, win-back, and support capacity checks.
- [x] **Phase 410: Referral Waitlist And Controlled Intake Execution** - Execute referral/waitlist/invite flows behind capacity gates and support visibility.
- [x] **Phase 411: v6.7 Revenue Growth Decision Gate** - Decide controlled growth, hold, rollback, or revenue remediation.

## Phase Details

### Phase 407: Paid Conversion And Billing Reality Review

**Goal**: Review checkout, paywall, payment method, entitlement, invoice, refund, failed payment, and subscription evidence.
**Depends on**: v6.6 live cohort outcome gate.
**Requirements**: V6REVEXEC-01
**Success Criteria**:

1. Checkout, paywall, payment methods, entitlement activation, renewal, cancellation, failed payment, invoice, refund, and manual correction evidence are reviewed.
2. Billing provider state, entitlement state, usage state, and admin support state reconcile for pilot accounts.
3. Parent copy explains access, limits, failures, and next action.
4. Revenue-impacting corrections are owner-approved, auditable, and reversible.

### Phase 408: Usage Quota And Parent Account Reliability Fixes

**Goal**: Fix usage/quota/account explanations, reconciliation drift, support visibility, and parent self-serve reliability.
**Depends on**: Phase 407.
**Requirements**: V6REVEXEC-02
**Success Criteria**:

1. Usage ledger coverage, idempotency, quota display, quota blocking, support explanations, and reconciliation reports are reliable for pilot scope.
2. Parent self-serve account states cover verification, subscription, child access, quota, support, and recovery.
3. Admin/support can explain account and usage state without private learning content.
4. Drift, stale records, duplicate events, and manual overrides are visible.

### Phase 409: Lifecycle Retention And Support Capacity Execution

**Goal**: Execute onboarding, activation, renewal, reminder, failed payment, cancellation, win-back, and support capacity checks.
**Depends on**: Phase 408.
**Requirements**: V6REVEXEC-03
**Success Criteria**:

1. Onboarding, activation, reminder, renewal, failed payment, cancellation, and win-back messages are executed or explicitly disabled.
2. Preferences, locale, delivery failure, quiet hours where applicable, and support visibility are handled.
3. Support capacity is measured against real volume and response quality.
4. Retention signals distinguish real users from test/dry-run traffic.

### Phase 410: Referral Waitlist And Controlled Intake Execution

**Goal**: Execute referral/waitlist/invite flows behind capacity gates and support visibility.
**Depends on**: Phase 409.
**Requirements**: V6REVEXEC-04
**Success Criteria**:

1. Referral, waitlist, invite, or controlled intake flows run behind feature, capacity, and support gates.
2. Growth surfaces clearly explain availability, eligibility, and next step.
3. Abuse/fraud handling is adequate for the internal development stage.
4. Intake feeds cohort planning and support staffing rather than public launch.

### Phase 411: v6.7 Revenue Growth Decision Gate

**Goal**: Decide controlled growth, hold, rollback, or revenue remediation.
**Depends on**: Phase 410.
**Requirements**: VERIFY-81
**Success Criteria**:

1. Decision is controlled growth, hold, rollback, or revenue remediation.
2. Decision uses conversion, revenue drift, usage accuracy, retention, support load, parent comprehension, and incident evidence.
3. Roadmap, requirements, state, milestone snapshots, and project summary are updated.
4. v6.8 receives learning-quality risks separate from revenue/account risks.

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| V6REVEXEC-01 | Phase 407 | Completed |
| V6REVEXEC-02 | Phase 408 | Completed |
| V6REVEXEC-03 | Phase 409 | Completed |
| V6REVEXEC-04 | Phase 410 | Completed |
| VERIFY-81 | Phase 411 | Completed |
