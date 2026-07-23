# Phase 476: Billing Idempotency And Paid Access Recovery - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-23
**Phase:** 476-billing-idempotency-and-paid-access-recovery
**Areas discussed:** Purchasable plans and checkout request identity; timeout, failure, and recovery experience; safe return URLs and checkout result page; webhook, entitlement, quota, and reminder rules

---

## Purchasable Plans And Checkout Request Identity

### Which plans are available in the first Web test?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Open all three paid plans shown on Pricing | ✓ |
| 2 | Show four plans but open only some paid plans | |
| 3 | Redesign the Pricing plan structure first | |

**User's choice:** Open Student, Teacher-supported, and Family; Free Trial does not enter Stripe checkout.
**Notes:** The user corrected the initial two-tier assumption by requiring inspection of the actual frontend Pricing page.

### How should frontend and backend plan identities align?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Four one-to-one active plan identities | ✓ |
| 2 | Keep three backend technical tiers | |
| 3 | Keep existing tiers and add a fourth internal tier | |

**User's choice:** `free_trial`, `student`, `teacher_supported`, and `family`.
**Notes:** Active `standard`, `premium`, and `tutor_supported` mappings are removed. The user previously locked `teacher` as the only active term and rejected `tutor`.

### How should refresh, timeout, and repeated clicks identify the same purchase?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Automatically resume the same purchase and Stripe Session | ✓ |
| 2 | Treat every click as a new purchase | |
| 3 | Permanently reuse one identity per parent and plan | |

**User's choice:** Resume the same durable checkout operation.
**Notes:** A new purchase begins only when the original operation is terminal or the parent explicitly changes plan.

### What happens when the parent changes plan while checkout is pending?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Confirm the switch and terminate/supersede the old checkout | ✓ |
| 2 | Allow multiple payable Sessions | |
| 3 | Block switching until the old Session ends | |

**User's choice:** Confirm the switch, expire the old Session where possible, and start a new command for the new plan.
**Notes:** At most one provider Session may remain payable.

---

## Timeout, Failure, And Recovery Experience

### What should the page show after returning from Stripe while confirmation is pending?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Show “confirming payment” and recover automatically | ✓ |
| 2 | Immediately show failure and allow another checkout | |
| 3 | Expose raw Stripe and webhook states | |

**User's choice:** Show a friendly confirming state, automatically query the original operation, and block another checkout.
**Notes:** The page cannot declare success until authoritative billing and entitlement confirmation exists.

### What can the parent do after automatic confirmation takes longer?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Recheck payment status and offer support | ✓ |
| 2 | Pay again | |
| 3 | Wait only for an administrator | |

**User's choice:** Provide “重新检查付款状态” and contact support.
**Notes:** Recheck is recovery of the original command only and never creates another Session.

### What happens to existing access when a new checkout, upgrade, or payment attempt fails?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Keep the prior plan and allow a later retry | ✓ |
| 2 | Cancel the prior plan too | |

**User's choice:** Keep the prior plan and entitlements.
**Notes:** End only the failed attempt and require terminal proof before a fresh attempt.

### What can an administrator do when checkout remains confirming?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | View safe state and idempotently reconcile with Stripe | ✓ |
| 2 | Directly mark payment successful | |
| 3 | Read only, with no recovery action | |

**User's choice:** Safe visibility plus provider recheck.
**Notes:** Admin sees redacted provider identifiers and failure reason but cannot manufacture payment success without provider proof.

---

## Safe Return URLs And Checkout Result Page

### Who determines Stripe success and cancel return URLs?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Backend generates complete URLs | ✓ |
| 2 | Frontend submits only paths | |
| 3 | Frontend submits complete validated URLs | |

**User's choice:** Backend generation from configured environment origin and fixed paths.
**Notes:** The browser request does not supply a full callback URL.

### How does the result page identify the checkout operation?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Opaque backend checkout reference | ✓ |
| 2 | Stripe Session ID as the public business reference | |
| 3 | Trust plan and success/cancel URL parameters | |

**User's choice:** An opaque STOA reference that loads authoritative state.
**Notes:** The redirect, URL path, and query parameters are not payment proof.

### What page experience follows the Stripe redirect?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Dedicated result page awaiting final STOA state | ✓ |
| 2 | Immediately redirect to the ordinary billing page | |
| 3 | Show only the Stripe redirect result | |

**User's choice:** Dedicated result page with confirming, active, not completed, and support-needed states.
**Notes:** Success shows effective plan and beneficiary students and links to Billing and the parent home.

### Which Web origins are accepted per environment?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Explicit exact origins per environment | ✓ |
| 2 | One shared origin list for every environment | |
| 3 | Derive origin from each request | |

**User's choice:** Production-only production origin, staging-only staging origin, and an explicit local localhost origin/port list.
**Notes:** No wildcard, automatic request-origin inference, arbitrary HTTPS, wrong-port, lookalike, credential-bearing, or encoded bypass.

---

## Webhook, Entitlement, Quota, And Reminder Rules

### What proof activates paid access after first purchase?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Signed paid-invoice and active-subscription proof | ✓ |
| 2 | Checkout completed event alone | |
| 3 | Browser success return | |

**User's choice:** Signed webhook proof of both first invoice paid and active subscription.
**Notes:** Checkout completion and the browser return remain confirming.

### Which students receive each plan?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | One selected child for Student/Teacher-supported and up to three for Family | ✓ |
| 2 | Every plan covers all children | |
| 3 | Plan belongs only to the parent | |

**User's choice:** Explicit beneficiaries: one active bound child for Student and Teacher-supported; up to three for Family.
**Notes:** Membership does not silently expand with future relationships.

### How does an upgrade affect current-period consumption?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Apply higher limits immediately without resetting usage | ✓ |
| 2 | Reset usage on activation | |
| 3 | Wait until the next billing period | |

**User's choice:** Immediate higher limits with consumed usage retained.
**Notes:** Paid storage becomes 15 GB, existing files remain, and stored objects cannot be double-counted.

### When do cancel, downgrade, and failed renewal reduce access?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Reduce after paid period with a grace state | ✓ |
| 2 | Reduce immediately | |
| 3 | Keep paid access until manual admin action | |

**User's choice:** Cancel/downgrade after the paid period; failed renewal has a three-day grace period, then Free Trial.
**Notes:** History is retained. If storage exceeds 5 GB after fallback, only new uploads are blocked.

### What is the AI quota unit?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Actual weekly provider-reported input and output tokens | ✓ |
| 2 | Weekly question/message/hint counts | |
| 3 | Record tokens but enforce request counts | |

**User's choice:** Actual provider tokens.
**Notes:** The user explicitly questioned request-based units because the AI provider already reports token usage. Parent sees percent/remaining; admin can inspect exact safe evidence.

### What weekly input/output token budgets apply?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Same AI budget for all paid plans | |
| 2 | Increasing paid-plan token budgets | ✓ |
| 3 | Owner-provided custom values later | |

**User's choice:** Free Trial 50,000/10,000; Student 500,000/100,000; Teacher-supported 1,000,000/200,000; Family 1,000,000/200,000 per selected beneficiary.
**Notes:** Values are input/output token pairs per week.

### How is teacher support quota measured?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Successfully admitted teacher-support cases | ✓ |
| 2 | Teacher service minutes | |
| 3 | Messages sent to a teacher | |

**User's choice:** Teacher-supported includes two cases per beneficiary/week; Family shares ten cases/family/week.
**Notes:** Multiple replies inside one case count once.

### How long is the failed-renewal grace period?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Seven days | |
| 2 | Three days | ✓ |
| 3 | No grace period | |

**User's choice:** Three days.
**Notes:** The user explicitly corrected this duration.

### How is a weekly allowance period defined?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Europe/Zurich Monday boundary | ✓ |
| 2 | Rolling seven days | |
| 3 | UTC Monday boundary | |

**User's choice:** Monday 00:00 to the next Monday 00:00 in Europe/Zurich.
**Notes:** Daylight-saving transitions must be correct.

### Do unused allowances roll over?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | No rollover | ✓ |
| 2 | Rollover for one week | |
| 3 | Indefinite accumulation | |

**User's choice:** No rollover.
**Notes:** Token and teacher-support allowances restart each Monday.

### What counts as a delivered answer for user token charging?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Validated, safe, durably stored, replay-readable result | ✓ |
| 2 | Student marks the answer useful | |
| 3 | Administrator reviews the answer | |

**User's choice:** Objective technical delivery, not subjective quality.
**Notes:** A terminally undelivered result restores user allowance but retains actual provider-cost evidence. A browser disconnect after durable storage remains chargeable.

### How long does Free Trial last?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Fourteen days | ✓ |
| 2 | Thirty days | |
| 3 | Permanent limited free plan | |

**User's choice:** Fourteen days from first student learning-account activation.
**Notes:** After expiry, history and parent viewing remain; new AI and teacher support pause.

### Which channels receive payment-method expiry reminders?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Verified email plus in-app notification | ✓ |
| 2 | Verified email only | |
| 3 | Web in-app only | |

**User's choice:** Verified email and in-app for the parent and all beneficiary students, plus persistent Web billing reminder.
**Notes:** No SMS or native push.

### Do parent and student reminder contents differ?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Role-specific content | |
| 2 | Identical billing reminder | ✓ |
| 3 | Student in-app reminder only | |

**User's choice:** Parent and student receive completely identical payment reminders and students can see payment-method and billing-processing information.
**Notes:** This explicitly reverses the earlier role-specific idea. Information remains safely masked: brand, last four digits, and expiry month only; never full card/CVC/provider credentials.

### How is an expiry month converted to the seven-day reminder date?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Treat the last calendar day as expiry | ✓ |
| 2 | Treat the first calendar day as expiry | |
| 3 | Wait only for a provider event | |

**User's choice:** Use the last day of the expiry month in Europe/Zurich and remind seven days earlier.
**Notes:** Updating the payment method clears the reminder. The same method and expiry month are notified once.

### What happens for missing, unverified, or undeliverable email?

| Option | Description | Selected |
|--------|-------------|----------|
| 1 | Email verified deliverable addresses only; retain in-app delivery | ✓ |
| 2 | Email any recorded address | |
| 3 | Stop the whole family reminder if one recipient fails | |

**User's choice:** Verified deliverable email only, with in-app fallback.
**Notes:** Failure for one family member does not block others and does not alter billing state.

---

## the agent's Discretion

- Internal durable-command schema, transaction/fencing details, reconciliation scheduling, Stripe key derivation, and exact state/code names.
- Token reservation/finalization implementation and safe provider-usage evidence representation.
- Exact friendly copy, polling cadence, notification job mechanism, and localized presentation within the locked behavior.
- Provider behavior must be researched from current official Stripe and Bedrock documentation before planning; it was not delegated as a product-policy choice.

## Deferred Ideas

- Real charging, production Stripe mutation, and bulk production reminders require separate operational approval.
- Native/mobile billing, native push, SMS, and app-store subscriptions wait until the Web App is live for testing and stable.
- Annual plans, coupons, new markets, rollover, and unrelated CRM/support expansion are outside Phase 476.

---

*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Discussion log generated: 2026-07-23*
