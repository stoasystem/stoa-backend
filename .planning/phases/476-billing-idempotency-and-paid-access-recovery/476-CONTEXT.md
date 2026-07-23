# Phase 476: Billing Idempotency And Paid Access Recovery - Context

**Gathered:** 2026-07-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 476 makes the real parent Web checkout recoverable and authoritative from the first browser request through Stripe test-mode payment, signed webhook processing, local billing convergence, beneficiary entitlement, weekly usage allowances, and parent/admin visibility. One logical purchase must produce at most one payable provider Session and one monotonic local outcome despite retries, timeouts, delayed or duplicate events, and local/provider partial failure.

This phase also aligns the backend with the four plans already presented by the Web Pricing page, replaces request-count quota enforcement with provider-reported weekly input/output token allowances, and adds payment-method expiry reminders. It does not authorize real customer charging, production mutation, native/mobile work, or a broader redesign of unrelated account and learning journeys.

</domain>

<decisions>
## Implementation Decisions

### Purchasable Plans And Checkout Identity

- **D-01:** The first Web test exposes all three paid plans shown on the Pricing page: `student`, `teacher_supported`, and `family`. `free_trial` is visible but never enters Stripe checkout.
- **D-02:** Frontend, backend, persisted billing state, entitlement state, Stripe price configuration, and evidence use one-to-one active plan identities: `free_trial`, `student`, `teacher_supported`, and `family`. Remove active `free`, `standard`, `premium`, and `tutor_supported` translations rather than preserving a hidden legacy tier model. The canonical role and product term is `teacher`; new active code and copy must not use `tutor`.
- **D-03:** A browser refresh, response timeout, repeated click, or identical retry resumes the same durable checkout command and returns the same Stripe Session. The Web, backend, Stripe request, and durable command share the same logical idempotency identity required by V9BILL-01. A fresh purchase can begin only after the earlier command is terminal or the parent explicitly confirms a plan change.
- **D-04:** If a parent changes the selected plan while checkout is pending, STOA asks for confirmation, supersedes the old command, expires the old Stripe Session where Stripe permits it, and creates a new command for the new plan. At most one Session may remain payable for that parent purchase flow.

### Timeout, Failure, And Recovery Experience

- **D-05:** Returning from Stripe does not prove payment. The result page initially shows a friendly “正在确认付款” state, automatically checks the original durable command, and blocks creation of another checkout while that operation can still converge.
- **D-06:** If confirmation takes longer, the parent can choose “重新检查付款状态” and contact support. Rechecking reconciles only the original operation and cannot create another Stripe Session or charge attempt.
- **D-07:** A failed, cancelled, or expired new purchase or upgrade ends only that attempt. The previous active plan and entitlements remain unchanged, and a new attempt is permitted only after the old provider Session has terminal proof.
- **D-08:** Admin support can see the parent, target plan, timestamps, safe lifecycle state, redacted Stripe identifiers, and failure reason, and can trigger an idempotent provider recheck. An admin cannot manually mark payment successful without authoritative Stripe payment and active-subscription proof.

### Safe Return URLs And Checkout Result Page

- **D-09:** The backend generates complete Stripe success and cancel URLs from the current environment’s configured exact Web origin and fixed approved paths. The browser does not submit a full return URL.
- **D-10:** The return URL carries a backend-generated opaque checkout reference. A plan query parameter, a path containing “success,” and the Stripe browser redirect itself are never payment proof.
- **D-11:** The dedicated result page reads authoritative STOA state and represents exactly these user-level outcomes: confirming, active, not completed, and support needed. Active state shows the effective plan and beneficiary students and links to Billing and the parent home.
- **D-12:** Production accepts only the configured production origin, staging only its configured staging origin, and local development only explicitly listed localhost origins and ports. Wildcards, request-origin inference, arbitrary HTTPS origins, credentials in URLs, lookalikes, encoded bypasses, and wrong ports are forbidden.

### Webhooks, Entitlements, And Plan Transitions

- **D-13:** Paid access activates only after a valid signed Stripe webhook proves both the first invoice paid and the subscription active. `checkout.session.completed` and browser return remain confirming signals and cannot activate entitlements alone.
- **D-14:** `student` and `teacher_supported` each cover one explicitly selected active bound student. `family` covers up to three explicitly managed active bound students; it does not silently include every current or future child.
- **D-15:** An upgrade applies its higher allowances immediately without resetting already consumed usage. Paid attachment capacity becomes 15 GB immediately; existing objects remain stored and must not be counted twice.
- **D-16:** Cancellation and downgrade take effect at the end of the already paid period. A failed renewal keeps paid access for a three-day grace period; if unresolved, access falls to `free_trial`. Account and history remain, and storage above the 5 GB free allowance blocks only new uploads rather than deleting existing files.
- **D-17:** Signed webhook processing is monotonic and idempotent: duplicate, delayed, and out-of-order events cannot double-activate, double-assign allowances, or regress a newer active entitlement.

### Weekly AI And Teacher-Support Allowances

- **D-18:** AI allowance is measured with actual provider-reported input and output tokens, not question, chat, or hint request counts. Accounting is weekly and idempotent. Parent views show percentage and remaining allowance; admin views can inspect exact redacted token evidence.
- **D-19:** Weekly input/output budgets are:
  - `free_trial`: 50,000 input / 10,000 output tokens.
  - `student`: 500,000 input / 100,000 output tokens.
  - `teacher_supported`: 1,000,000 input / 200,000 output tokens.
  - `family`: 1,000,000 input / 200,000 output tokens for each selected beneficiary.
- **D-20:** Teacher support counts successfully admitted support cases, not messages, replies, or minutes. `teacher_supported` includes two cases per beneficiary per week. `family` shares ten cases per family per week. Multiple messages or teacher replies within one case consume only one case.
- **D-21:** Every weekly allowance window is a Europe/Zurich calendar week from Monday 00:00 to the next Monday 00:00, including daylight-saving transitions. Unused token and teacher-support allowance expires; there is no rollover.
- **D-22:** A user token charge becomes final only when the response passes technical validation and safety checks, is durably stored, and is readable immediately or through stable replay. Subjective answer quality does not change accounting. A terminally undelivered result restores the user allowance while retaining separate provider-cost evidence. A browser disconnect after a valid result was durably stored does not restore allowance.
- **D-23:** `free_trial` lasts 14 days from the first activation of the student learning account. At expiry, account, learning history, and parent viewing remain available, while new AI and teacher-support use pauses and the family is directed to paid plans.

### Payment-Method Expiry Reminders

- **D-24:** Payment-method expiry reminders go to the parent and every beneficiary student through each account’s verified deliverable email and in-app notifications, with a persistent Web billing reminder. SMS and native push are outside this phase.
- **D-25:** Parent and beneficiary students receive the same billing reminder and may see the same billing-processing information. The reminder may include price, billing state, and only a safe masked payment-method summary such as brand, last four digits, and expiry month. Full card data, CVC, provider credentials, and payment-capable secrets are forbidden.
- **D-26:** When Stripe exposes only an expiry month, STOA treats the last calendar day of that month as the expiry date in Europe/Zurich and sends the reminder seven days earlier. Replacing or updating the payment method clears the reminder. The same payment method and expiry month are notified at most once.
- **D-27:** Email is sent only to verified deliverable addresses. Accounts without a usable email still receive the in-app reminder. Failure for one recipient neither blocks other family recipients nor changes billing state.

### the agent's Discretion

- Choose the durable checkout-command schema, public opaque-reference format, transaction boundaries, Stripe idempotency-key derivation, reconciliation lease/backoff, event ordering representation, and terminal-state names while preserving the locked business behavior.
- Choose the token reservation/finalization mechanism and provider-usage evidence schema, provided retries cannot double charge and actual provider cost remains distinguishable from restored user allowance.
- Choose exact structured API error codes, polling cadence, loading visuals, notification scheduling implementation, and friendly localized Web copy. APIs must remain machine-actionable; UI messages must remain short, friendly, and actionable.
- Research and verify current Stripe SDK/API semantics for idempotent Session creation, retrieval, expiration, invoice/subscription evidence, test clocks/events, and configured Bedrock model usage fields before planning implementation. Do not infer provider behavior from existing mocks.

</decisions>

<specifics>
## Specific Ideas

- The Pricing page is the current product source of truth: Free Trial CHF 0, Student CHF 29/month, Teacher-supported CHF 89/month, and Family CHF 149/month. The old backend `free/standard/premium` model and frontend `tutor_supported` identifier are implementation drift to remove.
- Payment recovery should feel like continuing one purchase, not asking the parent to pay again. “重新检查付款状态” means re-read and reconcile the original command only.
- The result page must wait for both billing and entitlement convergence, not merely show a cheerful page because Stripe redirected the browser to a success-looking URL.
- Students and parents intentionally receive identical payment reminders and can see the same safe billing information. This supersedes the earlier idea of role-specific reminder copy.
- Storage is durable: Free Trial allows 5 GB and paid access 15 GB; downgrade never deletes historical content.
- All integrated payment evidence uses Stripe sandbox/test mode. No real customer charge is permitted by this phase.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone And Phase Contract

- `.planning/ROADMAP.md` — Phase 476 boundary, DATA-002/SEC-008 ownership, success criteria, required evidence, and exit gate.
- `.planning/REQUIREMENTS.md` — Authoritative V9BILL-01 through V9BILL-04 contracts and Web-first milestone Definition of Done.
- `.planning/PROJECT.md` — Product history, AWS/Stripe integration context, and v9.0 Web-first constraints.
- `.planning/phases/474-deterministic-verification-and-gated-delivery/474-CONTEXT.md` — Required deterministic gate, build-once evidence, staging proof, owner approval, and prohibition on unapproved production mutation.
- `.planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-CONTEXT.md` — Compatible command, idempotency, recovery, usage, and relationship-convergence conventions.

### Audit Baseline

- `docs/audit/full-project-audit.md` — DATA-002 provider/local atomicity failure and SEC-008 callback validation finding.
- `docs/audit/findings.json` — Machine-readable finding ownership, severity, affected code, and required evidence.

### Backend Billing, Entitlement, And Usage

- `src/stoa/routers/parents.py` — Existing parent checkout, subscription, and billing API contracts.
- `src/stoa/routers/billing.py` — Public Stripe webhook adapter and signature-authenticated integration boundary.
- `src/stoa/routers/admin.py` — Existing admin billing, provider-readiness, refund, rollout, and support surfaces.
- `src/stoa/services/subscription_service.py` — Current checkout/provider/webhook/reconciliation implementation and legacy three-tier plan mapping.
- `src/stoa/services/entitlement_service.py` — Current effective-entitlement resolution and request-count plan limits.
- `src/stoa/services/usage_ledger_service.py` — Existing deterministic logical-usage identities and reconciliation patterns.
- `src/stoa/services/ai_service.py` — Bedrock request/response boundary where provider-reported input/output token evidence must be captured.
- `src/stoa/services/notification_service.py` — Existing durable in-app/email notification integration point.
- `src/stoa/models/user.py` — Current legacy `SubscriptionTier` enum that must converge with the four product identities.

### Authoritative Web Product Surface

- `/Users/zhdeng/stoa-frontend/src/pages/pricing/PricingPage.tsx` — Actual four-card Pricing page and paid-plan entry point.
- `/Users/zhdeng/stoa-frontend/src/components/pricing/pricingPlans.ts` — Current plan identities, CHF prices, audience, and feature summaries; contains the legacy `tutor_supported` identifier to replace.
- `/Users/zhdeng/stoa-frontend/src/components/pricing/FeatureComparison.tsx` — Cross-plan feature comparison presented to customers.
- `/Users/zhdeng/stoa-frontend/src/i18n/locales/en/pricing.json` — Pricing structure and customer-visible English plan language.
- `/Users/zhdeng/stoa-frontend/src/pages/billing/BillingPage.tsx` — Parent billing and checkout entry surface.
- `/Users/zhdeng/stoa-frontend/src/pages/billing/CheckoutResultPage.tsx` — Current preview/static result behavior to replace with authoritative convergence states.
- `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts` — Current Web billing adapter and checkout request contract.
- `/Users/zhdeng/stoa-frontend/src/types/billing.ts` — Current Web billing/plan type identities.

### Current AI Provider References

- `https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html` — Official Bedrock token accounting and token-burndown behavior; verify configured-model applicability.
- `https://aws.amazon.com/bedrock/pricing/` — Official Bedrock pricing and provider-cost reference; user allowance accounting must remain separate from provider cost.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/stoa/services/subscription_service.py` already has Stripe webhook signature processing, event deduplication/lifecycle handling, provider readiness, admin billing projections, and checkout helpers that should be evolved into the durable command rather than discarded wholesale.
- `src/stoa/services/usage_ledger_service.py` and `src/stoa/db/repositories/usage_ledger_repo.py` provide stable usage identities and reconciliation concepts that can inform token finalization and replay.
- `src/stoa/services/notification_service.py` and `src/stoa/db/repositories/notification_repo.py` provide durable notification identity/delivery behavior suitable for payment-method reminders.
- The Web repository already has Pricing, Billing, CheckoutButton, billing hooks, a result page, and parent/admin billing adapters. These are real integration surfaces, although several currently expose preview/demo or static-success behavior.

### Established Patterns

- Phase 475 establishes durable commands, conditional/transactional state transitions, stable replay, typed dependency outcomes, and idempotent repair. Billing should reuse those patterns.
- Signed provider evidence is authoritative; browser navigation, query parameters, optimistic local writes, and admin assertion are not.
- APIs expose stable structured error codes and safe actions. The Web presents simple, friendly, actionable text without Stripe internals or hidden identifiers.
- One account has one role, roles are exactly `student`, `parent`, `teacher`, or `admin`, and all new active terminology uses `teacher`, never `tutor`.
- Phase 474’s common backend/Web verification and immutable evidence path governs phase-closing proof. Mocks can support focused tests but cannot replace the Stripe test-mode browser/webhook evidence.

### Integration Points

- `src/stoa/routers/parents.py:create_my_subscription_checkout` must accept/reuse the logical business identity without accepting arbitrary full callback URLs, and expose safe command-status/recheck behavior.
- `src/stoa/services/subscription_service.py:create_checkout_session`, provider creation helpers, webhook transitions, and billing projections are the main provider/local convergence boundary.
- `src/stoa/services/entitlement_service.py`, question/chat/hint admission paths, and `src/stoa/services/ai_service.py` must converge on weekly provider-token allowances instead of existing daily request counters.
- Parent/student relationship records determine explicit plan beneficiaries; Family membership changes must not silently broaden paid access.
- The frontend Pricing and Billing route groups must remove demo/virtual success from the release path, reuse one checkout operation across retries, and show the authoritative result states.
- Parent and admin Web views consume billing/allowance projections; student notification/billing views need the explicitly approved masked payment information.

</code_context>

<deferred>
## Deferred Ideas

- Real customer charging, production Stripe mutation, production bulk reminders, and broader rollout require separate explicit operational approval.
- Native Expo/iOS/Android billing, native push, SMS, and app-store subscription work remain deferred until the Web App has launched for testing and is stable.
- Broader role journeys and full production-route closure remain in Phases 477 and 478; Phase 476 implements only the Web billing surfaces required to prove this phase’s paid-access journey.
- Additional markets, annual billing, coupons, proration-product changes, rollover allowances, and new CRM/support providers are outside this phase.

</deferred>

---

*Phase: 476-Billing Idempotency And Paid Access Recovery*
*Context gathered: 2026-07-23*
