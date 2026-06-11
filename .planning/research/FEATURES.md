# Feature Research

**Domain:** Live payment rollout and post-checkout billing operations for Stripe-first STOA subscriptions in Switzerland
**Researched:** 2026-06-11
**Confidence:** MEDIUM

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Live-mode rollout gate and credential readiness | Operators expect a clean separation between test and live behavior and a default that cannot accidentally charge real families. | MEDIUM | Depends on the existing v3.9 checkout flow, `stripe_live_charges_enabled`, price IDs, and webhook secret config. Add a visible readiness state, redacted config evidence, and a kill switch before any live rollout. |
| Production checkout verification with operator evidence | A subscription product must prove that hosted checkout can create the right subscription for the right plan before opening real charging. | HIGH | Depends on replacing the current local/simulated session behavior with real Stripe session creation while keeping the parent/admin route contracts. Evidence should show mode, price, session, redirect outcome, and request correlation without exposing secrets. |
| Production webhook authenticity, idempotency, and event timeline | Live billing breaks if operators can’t prove that Stripe events were verified, deduplicated, and applied once. | MEDIUM | Depends on the existing signature verification and dedupe rows in `subscription_service.py`. Expand operator-visible fields to include delivery result, provider mode, invoice/subscription IDs, and refusal reasons for failed processing. |
| Parent invoice and receipt access through provider-hosted artifacts | Families expect a way to retrieve payment records without opening a support ticket. | MEDIUM | Depends on the existing parent billing surface. STOA should expose invoice status, hosted invoice URL or invoice PDF link when available, and receipt/invoice metadata instead of generating custom documents. |
| Refund and credit-note operations | Internal operators need a controlled way to reverse billing mistakes or service issues. | MEDIUM | First pass should capture eligibility, refund type, amount, reason, operator note, and provider outcome. Prefer Stripe refunds and invoice credit notes or provider-dashboard handoff before building custom refund math. |
| Dunning visibility and recovery path | Failed renewals and expired cards are normal subscription cases; hiding them creates churn and support load. | MEDIUM | Depends on broader invoice event handling and parent/admin status surfaces. Use Stripe Smart Retries, failed-payment emails, and a hosted payment-method update path instead of a custom retry engine. |
| Tax/accounting handoff export | Even at small scale, finance needs reconcilable billing data before month-end and VAT review. | MEDIUM | Export invoice, payment, refund, credit-note, fee, and settlement metadata in CHF-friendly form. Stripe reports and balance transactions should remain the source of truth for fees and payouts; STOA should add parent/subscription mapping and operator context. |
| TWINT readiness and Swiss payment-method gating | Swiss families will expect TWINT to be considered, even if rollout starts card-first. | MEDIUM | For v4.4, the table-stakes outcome is a readiness decision: capability status, merchant onboarding checks, CHF compatibility, recurring-flow validation, and a rollout flag. Full TWINT activation can stay gated after proof. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Safe live-smoke flow with explicit no-real-charge default | Lets STOA prove production readiness without normalizing risky “just try a real payment” behavior. | MEDIUM | Build around named safe fixtures, approved smoke modes, and redacted evidence. This fits STOA’s existing release-gate style and is better than ad hoc operator testing. |
| Unified operator billing timeline | Gives support/admins one place to inspect checkout, webhook, invoice, refund, and dunning state without opening raw Stripe payloads. | MEDIUM | Extends the current admin billing visibility instead of creating a second operations console. Most value comes from normalized event summaries and next-action hints. |
| Parent recovery UX that deep-links to hosted payment management | Reduces involuntary churn by sending parents straight to the action that fixes a failed renewal. | LOW | Use Stripe-hosted payment update and customer portal flows where possible. STOA should frame the issue and current plan state, not rebuild payment-method management itself. |
| Controlled Swiss rollout for TWINT | Lets STOA test Swiss-local conversion upside without forcing a full payment-method redesign. | MEDIUM | Prefer Dashboard-driven dynamic payment methods and explicit enablement rules over custom frontend branching. Stage as “ready/off”, then “enabled for approved rollout cohort”. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Custom invoice PDF and receipt generation inside STOA | Seems brand-consistent and gives full UI control. | Rebuilds compliance-sensitive document behavior Stripe already handles, creates drift from provider truth, and expands tax/legal surface area. | Surface Stripe-hosted invoice and receipt links plus immutable metadata in STOA. |
| Custom dunning scheduler, retry engine, and email campaign logic | Feels like “more control” over failed payments. | Duplicates Stripe Smart Retries and billing emails, creates split-brain retry state, and is too large for this milestone. | Let Stripe execute retries and customer emails; STOA should mirror status, next step, and support context. |
| Full accounting or ERP sync in v4.4 | Finance teams eventually want automatic journal entries. | It turns a readiness milestone into an integration project with connector, mapping, reconciliation, and failure-recovery scope. | Export a clean handoff dataset keyed to Stripe report and balance transaction identifiers. |
| Full TWINT rollout before capability and recurring-flow proof | TWINT is attractive for Swiss families, so pressure to “just turn it on” is predictable. | Risks checkout inconsistency, unsupported recurring edge cases, and operator confusion if live eligibility is incomplete. | Make TWINT readiness explicit, then enable it behind a rollout decision once account capability and recurring checkout behavior are verified. |
| Real live-charge smoke as the default verification path | Feels like the fastest way to “know it works”. | Unsafe during internal development, hard to repeat cleanly, and unnecessary if configuration inspection plus approved fixtures exist. | Default to read-only/live-ready checks and explicit approved smoke fixtures only. |

## Feature Dependencies

```text
Existing v3.9 checkout + billing state foundation
    └──requires──> Live-mode rollout gate and real Stripe session wiring
                         └──requires──> Production checkout verification
                                              └──requires──> Parent/admin evidence surfaces

Existing webhook signature + dedupe foundation
    └──requires──> Enriched webhook event timeline
                         ├──enables──> Dunning visibility and recovery UX
                         ├──enables──> Refund/credit-note audit trail
                         └──enables──> Release-gate payment evidence

Invoice and receipt metadata surfaces
    └──enhances──> Parent billing self-service

Stripe reports + balance transactions
    └──requires──> Tax/accounting handoff export

TWINT capability validation
    └──requires──> Controlled Swiss rollout decision

Custom dunning engine ──conflicts──> Stripe Smart Retries and hosted recovery emails
Custom invoice generation ──conflicts──> Stripe-hosted invoices/receipts as source of truth
```

### Dependency Notes

- **Live-mode rollout gate requires the existing v3.9 billing foundation:** STOA already has parent checkout endpoints, billing rows, and admin billing views. v4.4 should upgrade those paths to real live-ready behavior rather than create a second billing model.
- **Production checkout verification requires real Stripe session wiring:** The current code stores placeholder session IDs and checkout URLs. Readiness features only matter once STOA can distinguish simulated/test behavior from real provider-backed checkout creation.
- **Enriched webhook events enable almost every post-checkout feature:** Refund visibility, invoice status, payment-failed handling, release evidence, and operator support all depend on provider events being recorded with enough normalized metadata.
- **Parent self-service is enhanced by provider-hosted artifacts:** STOA should explain status and expose trusted links; Stripe should remain the system that renders invoices, receipts, and payment-method update flows.
- **Tax/accounting handoff requires Stripe financial identifiers:** For reconciliation, Stripe report IDs, balance transaction IDs, invoice IDs, and refund IDs matter more than a custom STOA summary alone.
- **Custom retry and document systems conflict with milestone scope:** They duplicate Stripe Billing primitives and turn a rollout-readiness milestone into a billing-platform rebuild.

## MVP Definition

### Launch With (v4.4)

Minimum viable rollout readiness for this milestone.

- [ ] Live-mode rollout gate and credential readiness contract — essential to prevent accidental real charging and to define the production switch.
- [ ] Production checkout and webhook verification — essential because the MVP is only local/test-like today.
- [ ] Parent/admin invoice and receipt visibility — essential for real-money support operations.
- [ ] Refund and credit-note readiness workflow — essential for operator error correction and parent support.
- [ ] Dunning visibility with hosted recovery path — essential to manage failed renewals without custom retry logic.
- [ ] Tax/accounting handoff export — essential so finance can reconcile live billing without waiting for a future integration.
- [ ] TWINT readiness decision — essential for Swiss-market rollout planning even if activation is deferred.

### Add After Validation (v4.4.x)

Features to add once the core rollout path works in production.

- [ ] Direct refund execution from STOA admin — add after manual/provider-dashboard handoff is reliable and audit fields are stable.
- [ ] Controlled TWINT enablement for an approved cohort — add after account capability and recurring subscription behavior are verified in production-safe conditions.
- [ ] Operator resend/share tools for invoice and receipt links — add if support volume shows parents struggle with the hosted artifacts.

### Future Consideration (v5+)

Features to defer until product-market fit and payment volume justify them.

- [ ] Automated accounting connector or ERP sync — defer until manual export pain is proven.
- [ ] Custom cancellation deflection and churn automation — defer until retention work is a larger business lever than rollout safety.
- [ ] Multi-provider orchestration beyond Stripe/TWINT basics — defer until there is a concrete provider expansion need.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Live-mode rollout gate and credential readiness | HIGH | MEDIUM | P1 |
| Production checkout verification | HIGH | HIGH | P1 |
| Webhook authenticity, idempotency, and operator timeline | HIGH | MEDIUM | P1 |
| Parent invoice and receipt access | HIGH | MEDIUM | P1 |
| Refund and credit-note readiness | HIGH | MEDIUM | P1 |
| Dunning visibility and hosted recovery path | HIGH | MEDIUM | P1 |
| Tax/accounting handoff export | MEDIUM | MEDIUM | P1 |
| TWINT readiness decision | MEDIUM | LOW | P1 |
| Direct refund execution from STOA admin | MEDIUM | MEDIUM | P2 |
| Controlled TWINT enablement | MEDIUM | MEDIUM | P2 |
| ERP/accounting sync | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for v4.4 rollout readiness
- P2: Should have after the core rollout path is proven
- P3: Nice to have, future consideration

## Market Feature Analysis

| Feature | Typical Stripe-First Product | Swiss Family Expectation | STOA Approach |
|---------|------------------------------|--------------------------|---------------|
| Payment method rollout | Use hosted checkout plus Dashboard-managed dynamic payment methods. | CHF pricing and TWINT consideration matter more than a huge custom payment UI. | Keep hosted checkout, gate live/test clearly, and make TWINT a controlled enablement decision. |
| Receipts and invoices | Rely on provider-hosted invoice/receipt artifacts and billing emails. | Parents expect a simple record they can reopen later. | Surface hosted links and metadata in STOA; do not generate custom billing documents. |
| Refunds | Refund through Stripe Dashboard or API, often with internal notes. | Families expect fast correction when billing is wrong. | Start with auditable operator workflow and provider primitives; automate only the thin layer STOA must own. |
| Dunning | Use Smart Retries, provider emails, and a hosted payment update path. | Families expect clear action when payment fails, not silent access loss. | Mirror state in STOA and deep-link to hosted recovery actions. |
| Accounting handoff | Export Stripe reports plus internal customer mapping. | Swiss bookkeeping needs clean month-end evidence, not necessarily live ERP sync. | Export normalized Stripe IDs, CHF amounts, tax fields, and STOA parent/subscription mapping. |
| TWINT | Enable only if account capability, currency, and recurring support line up. | TWINT is a strong local signal but not worth destabilizing rollout. | Treat readiness as mandatory, activation as gated. |

## Sources

- Project context: `.planning/PROJECT.md`
- Milestone requirements: `.planning/REQUIREMENTS.md`
- Phase context: `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-CONTEXT.md`
- Current implementation: `src/stoa/config.py`, `src/stoa/services/subscription_service.py`, `src/stoa/routers/admin.py`, `src/stoa/routers/parents.py`, `tests/test_subscription_operations.py`
- Stripe subscriptions overview: https://docs.stripe.com/billing/subscriptions/overview
- Stripe subscription webhooks: https://docs.stripe.com/billing/subscriptions/webhooks
- Stripe webhook signature verification: https://docs.stripe.com/webhooks/signature
- Stripe Smart Retries: https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Stripe customer emails and recovery flows: https://docs.stripe.com/billing/revenue-recovery/customer-emails
- Stripe customer portal: https://docs.stripe.com/customer-management
- Stripe invoicing status/finalization: https://docs.stripe.com/invoicing/integration/workflow-transitions
- Stripe invoicing emails: https://docs.stripe.com/invoicing/send-email
- Stripe receipts: https://docs.stripe.com/receipts
- Stripe refunds: https://docs.stripe.com/refunds
- Stripe credit notes: https://docs.stripe.com/invoicing/dashboard/credit-notes
- Stripe Tax for invoices: https://docs.stripe.com/tax/invoicing
- Stripe reports API: https://docs.stripe.com/reports/api
- Stripe balance transaction types: https://docs.stripe.com/reports/balance-transaction-types
- Stripe TWINT overview: https://docs.stripe.com/payments/twint
- Stripe dynamic payment methods: https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods

---
*Feature research for: live payment rollout and billing operations readiness*
*Researched: 2026-06-11*
