# Pitfalls Research

**Domain:** Live subscription payment rollout for an existing Stripe-first backend MVP
**Researched:** 2026-06-11
**Confidence:** MEDIUM

## Critical Pitfalls

### Pitfall 1: Test/live crossover and fail-open configuration

**What goes wrong:**
The app looks "live-ready" but still creates checkout flows with test defaults, test price IDs, localhost return URLs, or the wrong webhook secret. Operators think rollout is gated; Stripe sees a different reality.

**Why it happens:**
Existing MVP code often treats mode as an app flag instead of Stripe truth. STOA's current backend already infers mode from config and falls back to synthetic test-like values when price IDs are missing.

**How to avoid:**
- Make Phase 144 define a fail-closed live contract: no live checkout unless live API key, live webhook secret, live product/price IDs, production return URLs, and rollback switch are all present and approved.
- In Phase 145, persist and display Stripe `livemode` from the event/object, not only an app env flag.
- Reject live rollout when any configured price ID or endpoint still points to test or localhost.
- Keep separate named config inventories for `test` and `live`, with operator evidence for both.

**Warning signs:**
- Billing rows show `mode=test` while Stripe dashboard activity is in live mode.
- A production environment still uses `price_test_*`, localhost success URLs, or a webhook secret copied from the CLI.
- Operators cannot prove which Stripe account and webhook endpoint a release is targeting.

**Phase to address:**
Phase 144 primary, Phase 145 verification

---

### Pitfall 2: Granting access on `checkout.session.completed` instead of paid invoice truth

**What goes wrong:**
Parents get premium access before Stripe has actually collected the first subscription payment, or keep access when the first invoice is incomplete, requires action, or later fails.

**Why it happens:**
Checkout success feels like payment success. Stripe's subscription docs explicitly separate Checkout completion, invoice payment, subscription status, and payment-action-required flows.

**How to avoid:**
- In Phase 145, make Stripe invoice/subscription state the source of truth for entitlements.
- Provision only when the subscription is active and the payment state is confirmed via `invoice.paid` plus subscription state, not just `checkout.session.completed`.
- Add handling for `invoice.payment_action_required`, `invoice.payment_failed`, `customer.subscription.updated`, `customer.subscription.deleted`, and paused/unpaid paths.
- Add tests for first-invoice failure, SCA/action-required, incomplete, past_due, unpaid, and canceled transitions.

**Warning signs:**
- A parent reaches paid features after closing Checkout even though the invoice is still open or incomplete in Stripe.
- Support sees active STOA access with Stripe subscription status `incomplete`, `past_due`, or `unpaid`.
- Local tests only cover happy-path checkout completion.

**Phase to address:**
Phase 145

---

### Pitfall 3: Webhook verification that is syntactically correct but operationally unsafe

**What goes wrong:**
Webhook requests are signed, but processing is still brittle: wrong event set, slow synchronous work, duplicate side effects, or 4xx responses that cause Stripe retries and invoice delays.

**Why it happens:**
Teams stop at signature verification and forget delivery semantics. Stripe expects fast 2xx responses and reliable idempotent handling of asynchronous retries.

**How to avoid:**
- In Phase 145, keep signature verification on the raw body and record verification outcome, event ID, event type, request correlation, and `livemode`.
- Make processing idempotent by event ID and safe on replay.
- Return success quickly and push heavier reconciliation work to an async path if needed.
- Decide explicitly whether STOA will subscribe to `invoice.created`; if yes, treat failure handling seriously because Stripe can delay automatic finalization for up to 72 hours when it does not receive a successful response.
- Capture a dead-letter or operator triage path for malformed-but-signed events and unknown parent mappings.

**Warning signs:**
- Stripe dashboard shows repeated webhook retries.
- STOA records duplicate billing events or multiple entitlement changes for one Stripe event.
- `invoice.created` or invoice finalization timing in Stripe does not match STOA expectations.

**Phase to address:**
Phase 145

---

### Pitfall 4: Losing parent/subscription linkage on asynchronous events

**What goes wrong:**
A live webhook cannot be mapped back to the correct STOA parent, or worse, maps to the wrong record. Refunds, subscription updates, and invoice failures become untraceable.

**Why it happens:**
An MVP often relies on Checkout session metadata only. Later events arrive on invoices, charges, refunds, or subscriptions where the original metadata path is incomplete, stale, or missing.

**How to avoid:**
- In Phase 145, persist canonical Stripe IDs for customer, subscription, checkout session, invoice, payment intent, and latest charge as soon as they exist.
- Store a durable mapping row or indexed lookup instead of scanning billing summary rows.
- Put STOA identifiers into Stripe metadata consistently on every object STOA creates, but do not rely on metadata alone.
- For refund handling in Phase 146, follow Stripe's documented chain from refund/charge to PaymentIntent to invoice to subscription when direct metadata is absent.

**Warning signs:**
- Webhook errors include "Unable to resolve parent for provider event."
- Only Checkout events resolve cleanly while invoice/refund events fail.
- Billing lookups depend on table scans or on the session ID alone.

**Phase to address:**
Phase 145 for primary mapping, Phase 146 for refund/invoice extensions

---

### Pitfall 5: Refunds treated as instant, always-successful, and low-audit

**What goes wrong:**
Operators issue a refund, STOA marks it done, but Stripe later leaves it pending, fails it, or requires alternate handling. Finance sees mismatches between customer communications, Stripe balance impact, and STOA records.

**Why it happens:**
Refunds are often added as a button after checkout works. Stripe's refund lifecycle is more nuanced: partial refunds, failed refunds, original-destination-only, balance constraints, and separate refund events.

**How to avoid:**
- In Phase 146, model refund states explicitly: requested, submitted, pending, succeeded, failed, canceled.
- Require operator reason, actor, source invoice/payment, amount, and whether access should change.
- Record Stripe refund IDs and listen for `refund.created`, `refund.updated`, `refund.failed`, plus `charge.refunded` where relevant.
- Do not assume a refund means subscription cancellation; define policy separately.
- Surface Stripe balance/failure constraints in the operator workflow.

**Warning signs:**
- STOA has a single "refunded" status with no Stripe refund object ID.
- Partial refunds are possible in Stripe but STOA only tracks full yes/no.
- Support cannot answer whether money actually returned or only the request was submitted.

**Phase to address:**
Phase 146

---

### Pitfall 6: Invoice, Swiss tax, and accounting handoff data is too thin

**What goes wrong:**
Live payments succeed, but finance cannot reconcile invoices, VAT treatment, refunds, or monthly revenue from STOA exports. Operators fall back to manual Stripe screenshots.

**Why it happens:**
An MVP usually stores subscription tier and status, not invoice identity, hosted invoice links, PDF links, service period, tax amounts, customer tax IDs, refund references, or reconciliation IDs.

**How to avoid:**
- In Phase 146, define a minimum accounting export contract: Stripe invoice ID/number, hosted invoice URL, invoice PDF URL, currency, subtotal, tax amounts/rates, total, paid amount, refund amount, service period, customer legal name/address, customer tax ID if present, Stripe customer/subscription/payment IDs, and timestamps.
- Treat Stripe as the invoice source of truth and STOA as the reconciliation/audit layer.
- If STOA plans to use Stripe Tax or tax-inclusive pricing later, capture the relevant invoice `automatic_tax` and tax line outputs now.
- Validate with STOA's Swiss accountant whether Stripe-hosted invoices plus STOA exports are sufficient, rather than assuming they are.

**Warning signs:**
- Admin billing pages show only tier/status and not invoice numbers or invoice artifacts.
- Operators cannot produce a month-end export without manual dashboard work.
- Refunds and credit effects are not linkable back to the original invoice.

**Phase to address:**
Phase 146

---

### Pitfall 7: Dunning logic collapses distinct Stripe states into one generic failure

**What goes wrong:**
STOA treats `past_due`, `unpaid`, `canceled`, `incomplete`, and payment-action-required as the same thing. Parents get the wrong message, support gives the wrong instruction, and access policy becomes inconsistent.

**Why it happens:**
The MVP often only recognizes `active` and `payment_failed`. Stripe Billing has more states, retry policies, and payment method precedence rules than that.

**How to avoid:**
- In Phase 146, define an explicit parent/admin state machine for `incomplete`, `payment_action_required`, `past_due`, `unpaid`, `canceled`, and `manual_override`.
- Surface `attempt_count` and `next_payment_attempt` from invoice data when available.
- If Smart Retries are enabled, align parent messaging with Stripe's retry schedule instead of inventing a separate retry timeline.
- When payment details are updated, update the payment method at the Stripe field that actually failed, not just any customer-level default.

**Warning signs:**
- The admin UI has one generic "payment failed" badge.
- Parents are told to retry payment while Stripe is actually waiting for a new payment method or customer action.
- Access revocation timing differs case by case because policy is not defined.

**Phase to address:**
Phase 146

---

### Pitfall 8: TWINT is "enabled" but not rollout-ready

**What goes wrong:**
STOA announces TWINT readiness, but the payment method remains pending, cannot be offered reliably in production, or works for one-off payments while subscription setup is incomplete.

**Why it happens:**
Teams confuse Dashboard enablement with merchant readiness. Stripe's TWINT docs add onboarding requirements, CHF/customer-location constraints, and a distinct subscription setup path.

**How to avoid:**
- In Phase 144, decide whether TWINT is v4.4 implementation scope or readiness-only scope.
- If in scope, Phase 145 must create real Checkout sessions with TWINT included for the subscription flow and verify the live capability state.
- Verify the business website/legal notice, CHF pricing, Swiss merchant details, and TWINT capability status before calling it launch-ready.
- Keep a product fallback: Stripe card subscriptions first, TWINT behind an explicit readiness flag until capability is active and end-to-end verified.

**Warning signs:**
- Stripe shows TWINT capability `pending`.
- STOA has no CHF/live price mapping for TWINT subscription products.
- Operators cannot prove that the subscription checkout flow actually presents TWINT in the intended environment.

**Phase to address:**
Phase 144 for scope/readiness, Phase 145 if implemented

---

### Pitfall 9: No operator evidence, canary controls, or rollback discipline

**What goes wrong:**
The backend can technically charge live customers, but there is no safe rollout envelope: no allowlist, no mutation audit bundle, no proof of webhook health, and no crisp rollback move.

**Why it happens:**
Teams treat payment rollout as "just another deploy." Existing STOA milestones already emphasize release evidence, but payment rollout adds external financial side effects and support obligations.

**How to avoid:**
- In Phase 147, require release evidence for live credential presence, Stripe endpoint configuration, webhook delivery success, product/price mapping, refund test path, invoice visibility, dunning visibility, and explicit approval status for real charging.
- Start with a canary cohort or operator allowlist before broad parent availability.
- Keep a rollback switch that stops new live checkout creation without breaking read-only billing inspection.
- Record who approved live charging, when, and under which evidence package.

**Warning signs:**
- The only proof of readiness is "it worked in test mode."
- There is no document showing current Stripe endpoint URLs, event subscriptions, or live-charge approval state.
- Support cannot answer how to pause rollout without code changes.

**Phase to address:**
Phase 147

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Keep local synthetic checkout/session IDs instead of persisting Stripe-created IDs everywhere | Faster MVP tests | Breaks reconciliation, refunds, and live event tracing | Local-only MVP, never for live rollout |
| Treat `checkout.session.completed` as entitlement success | Simpler logic | Paid access drifts from invoice truth | Never once live charging is possible |
| Store only subscription tier/status in admin billing views | Quick UI delivery | No invoice/refund/tax/accounting handoff | Acceptable only before Phase 146 |
| Manual refund in Stripe dashboard with no STOA audit row | Fast operator action | Missing evidence, support confusion, bad finance handoff | Only as emergency break-glass, with retrospective evidence |
| Global live toggle with no cohorting | Simple release | High-blast-radius rollout failure | Never for first live rollout |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Stripe Checkout | Assuming app config determines mode | Verify actual Stripe object/event `livemode` and configured account |
| Stripe Webhooks | Verifying signature but not delivery semantics | Verify raw body, record event metadata, handle retries idempotently, return fast 2xx |
| Stripe Billing | Mapping all failures to one status | Model invoice/subscription states separately and use Stripe retry fields |
| Stripe Refunds | Marking refunded at request time | Track refund lifecycle through Stripe refund events and statuses |
| Stripe Invoices | Ignoring invoice artifacts because Checkout is hosted | Persist invoice IDs, numbers, hosted URLs, PDFs, service period, tax amounts |
| TWINT | Treating Dashboard enablement as production readiness | Verify capability status, CHF flow, merchant onboarding requirements, and subscription-specific flow |
| Swiss accounting handoff | Assuming Stripe dashboard screenshots are enough | Produce a structured export contract agreed with accounting |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Scanning billing rows to resolve parent from webhook objects | Intermittent webhook lookup failures, slow delivery | Add durable ID mapping rows or indexes for customer/subscription/invoice/payment IDs | Breaks earlier than scale suggests because webhook SLAs are latency-sensitive |
| Doing all webhook work inline | Stripe retries, timeouts, duplicate operator incidents | Keep handler thin and move heavy reconciliation to async processing | Usually shows up before high traffic, once a few expensive paths are added |
| Admin list views built on full table scans | Billing pages get slower as live history grows | Add queryable indexes and bounded filters before wider rollout | Likely noticeable once many invoice/refund rows accumulate |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Logging webhook secrets, Stripe signatures, or raw payloads with PII | Secret leakage and financial data exposure | Redact secrets and limit stored payload detail to operator-safe metadata |
| Reusing test secrets or CLI webhook secrets in production | False confidence and rejected live events | Separate approved live credential inventory and evidence |
| Exposing hosted invoice URLs or payment metadata to the wrong role | Billing privacy leak | Keep parent/admin views role-scoped and avoid secret-bearing fields |
| Allowing live checkout from broad production traffic before approval | Real unauthorized charging | Gate live checkout behind explicit release approval and rollout controls |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing "Subscription active" right after redirect return | Parent trusts a state that may still fail | Show pending verification until invoice/subscription state confirms success |
| Hiding why a payment failed | Parent cannot self-recover | Distinguish update-payment-method, complete-authentication, retry-scheduled, and contact-support paths |
| Mixing manual override and Stripe truth in one unlabeled badge | Support confusion and trust loss | Surface manual override as a separate operator state with provenance |

## "Looks Done But Isn't" Checklist

- [ ] **Live credentials:** Often missing account-level proof and rollback switch; verify approved live API key, webhook secret, endpoint URL, and event subscriptions.
- [ ] **Checkout rollout:** Often missing live `livemode` confirmation and production return URLs; verify a canary checkout creates real Stripe objects in the intended account without broad exposure.
- [ ] **Webhook readiness:** Often missing replay-safe idempotency and parent mapping for non-Checkout events; verify duplicate delivery, invoice failure, refund, and unknown-object handling.
- [ ] **Billing operations:** Often missing refund lifecycle, invoice artifacts, and dunning state visibility; verify admin views and exports cover them.
- [ ] **Swiss handoff:** Often missing invoice/tax/refund reconciliation fields; verify accounting can close the month without manual Stripe screenshots.
- [ ] **TWINT readiness:** Often missing capability activation or subscription-specific flow proof; verify capability state and end-to-end subscription presentation.
- [ ] **Release evidence:** Often missing approval trace for real charging; verify who approved live rollout, what evidence was reviewed, and how rollback works.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Test/live crossover | HIGH | Disable live checkout creation, audit current Stripe account/endpoints, reconcile any affected sessions, fix config inventory, rerun canary |
| Wrong entitlement event | HIGH | Recompute entitlement state from Stripe invoice/subscription truth, correct affected parent tiers, notify support |
| Broken webhook mapping | HIGH | Pause mutation actions, backfill missing Stripe ID mappings from dashboard/API, replay stored events where possible |
| Refund drift | MEDIUM | Reconcile Stripe refunds against STOA audit rows, repair parent/admin status, issue alternative refund path if Stripe refund failed |
| Thin Swiss accounting export | MEDIUM | Add backfill job for invoice/refund metadata, regenerate export bundle, have accounting re-review before next close |
| TWINT false readiness | MEDIUM | Hide TWINT from live checkout, keep card flow active, complete capability/onboarding work, rerun targeted smoke |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Test/live crossover and fail-open configuration | Phase 144 | Release evidence proves live account, live prices, live webhook secret, production URLs, and rollback switch |
| Granting access on wrong Stripe event | Phase 145 | Tests cover incomplete, paid, failed, canceled, unpaid, and action-required paths |
| Webhook verification that is syntactically correct but operationally unsafe | Phase 145 | Duplicate delivery, bad signature, unknown event, and retry-path checks pass |
| Losing parent/subscription linkage on asynchronous events | Phase 145 | Live/test fixtures resolve parent from checkout, subscription, invoice, and refund-related objects |
| Refunds treated as instant, always-successful, and low-audit | Phase 146 | Operator flow shows refund request, status updates, failure handling, and audit evidence |
| Invoice, Swiss tax, and accounting handoff data is too thin | Phase 146 | Export bundle contains invoice/refund/tax fields agreed with accounting |
| Dunning logic collapses distinct Stripe states into one generic failure | Phase 146 | Parent/admin views distinguish payment action, retry scheduled, past_due, unpaid, and canceled |
| TWINT is enabled but not rollout-ready | Phase 144 or 145 | Capability state, CHF pricing, merchant onboarding, and subscription presentation evidence are captured |
| No operator evidence, canary controls, or rollback discipline | Phase 147 | Release gate includes canary results, approval record, webhook health, and rollback procedure evidence |

## Sources

- STOA context: `.planning/PROJECT.md`, `.planning/REQUIREMENTS.md`, `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-CONTEXT.md`
- Current backend implementation: `src/stoa/services/subscription_service.py`, `src/stoa/routers/billing.py`, `src/stoa/config.py`, `tests/test_subscription_operations.py`
- Stripe webhooks: https://docs.stripe.com/webhooks
- Stripe Event object (`livemode`, request metadata): https://docs.stripe.com/api/events/object
- Stripe subscriptions + webhooks: https://docs.stripe.com/billing/subscriptions/webhooks
- Stripe Smart Retries and dunning fields: https://docs.stripe.com/billing/revenue-recovery/smart-retries
- Stripe Invoice object (`hosted_invoice_url`, `invoice_pdf`, `attempt_count`, tax/customer fields): https://docs.stripe.com/api/invoices/object
- Stripe refunds guide and refund events: https://docs.stripe.com/refunds and https://docs.stripe.com/api/refunds
- Stripe TWINT overview: https://docs.stripe.com/payments/twint
- Stripe TWINT subscriptions: https://docs.stripe.com/billing/subscriptions/twint

---
*Pitfalls research for: STOA live payment rollout readiness*
*Researched: 2026-06-11*
