# Phase 476: Billing Idempotency And Paid Access Recovery - Research

**Researched:** 2026-07-23
**Domain:** Durable Stripe Checkout commands, webhook convergence, paid entitlements, provider-token allowances, and payment-method reminders
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Purchasable Plans And Checkout Identity

- **D-01:** The first Web test exposes all three paid plans shown on the Pricing page: `student`, `teacher_supported`, and `family`. `free_trial` is visible but never enters Stripe checkout.
- **D-02:** Frontend, backend, persisted billing state, entitlement state, Stripe price configuration, and evidence use one-to-one active plan identities: `free_trial`, `student`, `teacher_supported`, and `family`. Remove active `free`, `standard`, `premium`, and `tutor_supported` translations rather than preserving a hidden legacy tier model. The canonical role and product term is `teacher`; new active code and copy must not use `tutor`.
- **D-03:** A browser refresh, response timeout, repeated click, or identical retry resumes the same durable checkout command and returns the same Stripe Session. The Web, backend, Stripe request, and durable command share the same logical idempotency identity required by V9BILL-01. A fresh purchase can begin only after the earlier command is terminal or the parent explicitly confirms a plan change.
- **D-04:** If a parent changes the selected plan while checkout is pending, STOA asks for confirmation, supersedes the old command, expires the old Stripe Session where Stripe permits it, and creates a new command for the new plan. At most one Session may remain payable for that parent purchase flow.

#### Timeout, Failure, And Recovery Experience

- **D-05:** Returning from Stripe does not prove payment. The result page initially shows a friendly “正在确认付款” state, automatically checks the original durable command, and blocks creation of another checkout while that operation can still converge.
- **D-06:** If confirmation takes longer, the parent can choose “重新检查付款状态” and contact support. Rechecking reconciles only the original operation and cannot create another Stripe Session or charge attempt.
- **D-07:** A failed, cancelled, or expired new purchase or upgrade ends only that attempt. The previous active plan and entitlements remain unchanged, and a new attempt is permitted only after the old provider Session has terminal proof.
- **D-08:** Admin support can see the parent, target plan, timestamps, safe lifecycle state, redacted Stripe identifiers, and failure reason, and can trigger an idempotent provider recheck. An admin cannot manually mark payment successful without authoritative Stripe payment and active-subscription proof.

#### Safe Return URLs And Checkout Result Page

- **D-09:** The backend generates complete Stripe success and cancel URLs from the current environment’s configured exact Web origin and fixed approved paths. The browser does not submit a full return URL.
- **D-10:** The return URL carries a backend-generated opaque checkout reference. A plan query parameter, a path containing “success,” and the Stripe browser redirect itself are never payment proof.
- **D-11:** The dedicated result page reads authoritative STOA state and represents exactly these user-level outcomes: confirming, active, not completed, and support needed. Active state shows the effective plan and beneficiary students and links to Billing and the parent home.
- **D-12:** Production accepts only the configured production origin, staging only its configured staging origin, and local development only explicitly listed localhost origins and ports. Wildcards, request-origin inference, arbitrary HTTPS origins, credentials in URLs, lookalikes, encoded bypasses, and wrong ports are forbidden.

#### Webhooks, Entitlements, And Plan Transitions

- **D-13:** Paid access activates only after a valid signed Stripe webhook proves both the first invoice paid and the subscription active. `checkout.session.completed` and browser return remain confirming signals and cannot activate entitlements alone.
- **D-14:** `student` and `teacher_supported` each cover one explicitly selected active bound student. `family` covers up to three explicitly managed active bound students; it does not silently include every current or future child.
- **D-15:** An upgrade applies its higher allowances immediately without resetting already consumed usage. Paid attachment capacity becomes 15 GB immediately; existing objects remain stored and must not be counted twice.
- **D-16:** Cancellation and downgrade take effect at the end of the already paid period. A failed renewal keeps paid access for a three-day grace period; if unresolved, access falls to `free_trial`. Account and history remain, and storage above the 5 GB free allowance blocks only new uploads rather than deleting existing files.
- **D-17:** Signed webhook processing is monotonic and idempotent: duplicate, delayed, and out-of-order events cannot double-activate, double-assign allowances, or regress a newer active entitlement.

#### Weekly AI And Teacher-Support Allowances

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

#### Payment-Method Expiry Reminders

- **D-24:** Payment-method expiry reminders go to the parent and every beneficiary student through each account’s verified deliverable email and in-app notifications, with a persistent Web billing reminder. SMS and native push are outside this phase.
- **D-25:** Parent and beneficiary students receive the same billing reminder and may see the same billing-processing information. The reminder may include price, billing state, and only a safe masked payment-method summary such as brand, last four digits, and expiry month. Full card data, CVC, provider credentials, and payment-capable secrets are forbidden.
- **D-26:** When Stripe exposes only an expiry month, STOA treats the last calendar day of that month as the expiry date in Europe/Zurich and sends the reminder seven days earlier. Replacing or updating the payment method clears the reminder. The same payment method and expiry month are notified at most once.
- **D-27:** Email is sent only to verified deliverable addresses. Accounts without a usable email still receive the in-app reminder. Failure for one recipient neither blocks other family recipients nor changes billing state.

### the agent's Discretion

- Choose the durable checkout-command schema, public opaque-reference format, transaction boundaries, Stripe idempotency-key derivation, reconciliation lease/backoff, event ordering representation, and terminal-state names while preserving the locked business behavior.
- Choose the token reservation/finalization mechanism and provider-usage evidence schema, provided retries cannot double charge and actual provider cost remains distinguishable from restored user allowance.
- Choose exact structured API error codes, polling cadence, loading visuals, notification scheduling implementation, and friendly localized Web copy. APIs must remain machine-actionable; UI messages must remain short, friendly, and actionable.
- Research and verify current Stripe SDK/API semantics for idempotent Session creation, retrieval, expiration, invoice/subscription evidence, test clocks/events, and configured Bedrock model usage fields before planning implementation. Do not infer provider behavior from existing mocks.

### Deferred Ideas (OUT OF SCOPE)

- Real customer charging, production Stripe mutation, production bulk reminders, and broader rollout require separate explicit operational approval.
- Native Expo/iOS/Android billing, native push, SMS, and app-store subscription work remain deferred until the Web App has launched for testing and is stable.
- Broader role journeys and full production-route closure remain in Phases 477 and 478; Phase 476 implements only the Web billing surfaces required to prove this phase’s paid-access journey.
- Additional markets, annual billing, coupons, proration-product changes, rollover allowances, and new CRM/support providers are outside this phase.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| V9BILL-01 | Each Web checkout business request carries a required idempotency key that is reused by the backend, Stripe, and durable local command state, producing at most one active provider session. | Durable command/open-session guard, immutable intent fingerprint, stable provider key, same-command replay, and supersession protocol below. |
| V9BILL-02 | Provider success with local failure, local success with response timeout, duplicate browser retry, and delayed webhook all reconcile to one support-visible billing state. | Provider-call intent persistence, fact-oriented webhook inbox, reconciliation leases, command projection, and failure-injection matrix below. |
| V9BILL-03 | Checkout success/cancel URLs are parsed structurally and restricted to configured exact Web origins and approved paths for the current environment. | Server-only URL construction, startup origin validation, fixed paths, opaque reference, and negative URL matrix below. |
| V9BILL-04 | A Stripe test-mode browser journey proves signed webhook processing changes parent/student effective entitlement and quota exactly once and remains explainable in parent/admin Web views. | Real sandbox acceptance architecture, signed event evidence, transactional grant projection, parent/admin views, and no-live-charge assertions below. |
</phase_requirements>

## Summary

The current checkout creates a provider Session before durable command state, accepts browser-supplied full callback URLs, omits a Stripe idempotency key, and can activate a paid tier from `invoice.paid` or an active subscription independently. Its global `event.created` stale check also assumes an ordering Stripe explicitly does not guarantee. The existing Web flow generates full URLs from `window.location.origin`, offers a virtual checkout/static result path, and translates four customer plans into the backend’s legacy three tiers. These are the direct implementation causes of DATA-002, SEC-008, and all four V9BILL requirements. [VERIFIED: codebase grep] [CITED: https://docs.stripe.com/webhooks]

Use a parent-scoped durable checkout command as the system of record. Create the command and a single-open-command guard transactionally before any provider call; derive one opaque Stripe key from that command; persist provider-call intent; attach the returned Session transactionally; and replay the stored result for every identical Web retry. Stripe retains idempotent results only while its key remains present and may prune keys after at least 24 hours, so STOA must retain the command, Session identity, intent fingerprint, and reconciliation evidence for the whole business lifetime rather than treating Stripe’s cache as durable storage. [CITED: https://docs.stripe.com/api/idempotent_requests]

Treat signed webhooks as fact triggers, not as an ordered state stream. Store/deduplicate the event, retrieve the referenced current Stripe objects when needed, and activate in one DynamoDB transaction only when the expected first invoice is paid and the matching subscription is active. In the same transaction publish the command result, parent billing projection, explicit beneficiary grants, and allowance version. This matches Stripe’s subscription guidance and makes duplicate, delayed, or out-of-order events harmless. [CITED: https://docs.stripe.com/billing/subscriptions/webhooks] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html]

**Primary recommendation:** Plan the phase as one vertical invariant—durable command → exactly one sandbox Session → signed fact convergence → atomic beneficiary/allowance activation → authoritative Web/support projection—then add weekly token finalization and expiry reminders on the same idempotent ledger/notification patterns. [VERIFIED: 476-CONTEXT.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Generate/reuse checkout operation identity | Browser / Client | API / Backend | The browser retains one logical key across refresh/retry; the API authenticates ownership, fingerprints intent, and is authoritative. [VERIFIED: 476-CONTEXT.md] |
| Enforce at most one payable Session | API / Backend | Database / Storage | A parent-scoped conditional guard must precede Stripe creation and survive process/browser failure. [VERIFIED: codebase grep] |
| Create/retrieve/expire Stripe Session | API / Backend | Stripe | Secrets and provider mutation stay server-side; only an open Session is expireable. [CITED: https://docs.stripe.com/api/checkout/sessions/expire] |
| Build return URLs | API / Backend | Browser / Client | The backend constructs one configured origin plus fixed path and opaque reference; the browser never chooses an origin. [VERIFIED: 476-CONTEXT.md] |
| Verify and ingest webhooks | API / Backend | Database / Storage | Raw-body signature verification is an integration boundary; durable inbox/facts make retries safe. [CITED: https://docs.stripe.com/webhooks/signature] |
| Activate/grace/cancel entitlements | Database / Storage | API / Backend | Billing, command, explicit grants, and allowance version change atomically; APIs read projections. [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html] |
| Select beneficiaries | Browser / Client | API / Backend | Parent chooses from authorized active bindings; backend revalidates cardinality and relationship state. [VERIFIED: 475-CONTEXT.md] |
| Reserve/finalize AI tokens | API / Backend | Database / Storage | The provider boundary captures actual usage; conditional ledgers prevent concurrent overspend and double finalization. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html] |
| Compute Zurich allowance/reminder windows | API / Backend | Database / Storage | Domain time is calculated with IANA time-zone rules and stored as explicit UTC boundaries/identity. [CITED: https://docs.python.org/3/library/zoneinfo.html] |
| Deliver expiry reminder | API / Backend | Database / Storage | Scheduler creates per-recipient/channel delivery intents; existing notification workers deliver independently. [VERIFIED: codebase grep] |
| Render billing/result/support state | Browser / Client | API / Backend | TanStack Query polls authoritative command/billing projections; UI never infers payment from URL text. [VERIFIED: codebase grep] |
| Sandbox acceptance evidence | API / Backend | Browser / Client | Browser proves the journey; backend evidence binds command, sandbox request/events, transaction result, and projections. [VERIFIED: 474-CONTEXT.md] |

## Project Constraints (from AGENTS.md)

- The backend repository has no root `AGENTS.md`; the canonical Web repository has one and requires React, TypeScript, Vite, and npm, with Node.js 20 LTS or newer LTS recommended. [VERIFIED: codebase grep]
- Web source follows two-space indentation, single quotes, omitted semicolons, multiline trailing commas, PascalCase components, and existing standard npm scripts. [VERIFIED: ../stoa-frontend/AGENTS.md]
- Use TanStack Query for server state; do not duplicate billing command/projection state into Zustand merely to span routes. Zustand is reserved for durable cross-route client state. [VERIFIED: ../stoa-frontend/AGENTS.md]
- Do not commit `node_modules/`, `dist/`, or local environment files. [VERIFIED: ../stoa-frontend/AGENTS.md]
- Web changes must run through the GSD planned execution workflow; this research artifact itself is being produced by the active GSD phase-planning workflow. [VERIFIED: ../stoa-frontend/AGENTS.md]

## Standard Stack

### Core

| Library / Service | Verified Version | Purpose | Why Standard Here |
|-------------------|------------------|---------|-------------------|
| Python | 3.12.13 virtualenv; project requires `>=3.12` | Domain services, URL/time handling, Lambda application | Existing runtime; `urllib.parse`, `hmac`, `secrets`, `calendar`, and `zoneinfo` cover the new primitives without a package. [VERIFIED: environment probe] |
| FastAPI | 0.136.3 | Parent/admin/status/recheck/webhook APIs | Existing API framework and authorization boundary. [VERIFIED: uv.lock] |
| Stripe Python SDK | 15.2.0, published 2026-05-27 in the lock | Session mutation/retrieval and official webhook verification | Already installed and the correct provider SDK; pass an idempotency key on create and use the SDK webhook constructor rather than new custom HMAC code. [VERIFIED: uv.lock] [CITED: https://docs.stripe.com/webhooks/signature] |
| Boto3 | 1.43.16, published 2026-05-27 in the lock | DynamoDB transactions and Bedrock runtime calls | Existing AWS SDK and repository boundary. [VERIFIED: uv.lock] |
| DynamoDB | Existing single-table repositories | Durable command, guard, facts, grants, counters, evidence | Transactions provide all-or-nothing updates for up to 100 distinct items in one Region. [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html] |
| Amazon Bedrock Anthropic Messages via `InvokeModel` | Configured `eu.anthropic.claude-sonnet-4-6` | AI answer/hint provider and actual usage source | The current response already contains `usage.input_tokens` and `usage.output_tokens`; current code discards that object. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html] |
| React / TanStack Query | React 19.2.6; Query 5.100.14 | Pricing, Billing, checkout result polling, parent/student/admin projections | Existing locked Web stack and intended server-state mechanism. [VERIFIED: ../stoa-frontend/package-lock.json] |
| Playwright | 1.60.0 | Real sandbox browser journey and UI projections | Existing E2E framework; the current config forces mock checkout and therefore needs a separate real-provider project/config. [VERIFIED: codebase grep] |

### Supporting

| Library / Primitive | Version | Purpose | When to Use |
|---------------------|---------|---------|-------------|
| `urllib.parse` | Python 3.12 stdlib | Parse the configured base origin and construct a fixed callback URL | Validate settings at startup; do not validate browser-provided callback URLs because that input must be removed. [CITED: https://docs.python.org/3/library/urllib.parse.html] |
| `secrets` + HMAC/SHA-256 | Python 3.12 stdlib | Opaque public reference and non-PII provider key digest | Generate unrelated public and provider identifiers from one internal command without exposing parent IDs. [VERIFIED: Python stdlib] |
| `zoneinfo.ZoneInfo` + `calendar.monthrange` | Python 3.12 stdlib | DST-safe Zurich week boundaries and card-month end | Build boundaries from local calendar dates, then convert to UTC. [CITED: https://docs.python.org/3/library/zoneinfo.html] [CITED: https://docs.python.org/3/library/calendar.html] |
| pytest / time-machine | 9.0.3 / 3.2.0 | State-machine, DST, grace, reminder, and failure-injection tests | Existing locked dev dependencies. [VERIFIED: uv.lock] |
| Existing notification repository/workers | Repository code | In-app/email delivery intents and retries | Reuse per-recipient durable identities and account-deletion fencing. [VERIFIED: codebase grep] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Durable local command plus Stripe key | Stripe key alone | Rejected: Stripe may prune keys after at least 24 hours, while STOA must recover later and retain ownership/state. [CITED: https://docs.stripe.com/api/idempotent_requests] |
| Fact-oriented webhook convergence | Sort all events by `event.created` | Rejected: delivery order is not guaranteed, and two distinct Events can represent the same object/type. [CITED: https://docs.stripe.com/webhooks] |
| Server-built fixed callback URL | Parse/allowlist browser full URLs | Rejected by D-09 and still leaves unnecessary attack surface; configuration should be parsed once, not user input on every purchase. [VERIFIED: 476-CONTEXT.md] |
| Existing DynamoDB transaction pattern | New workflow/orchestration package | Rejected: the bounded family size and existing repositories fit one transaction; no new dependency is needed. [VERIFIED: codebase grep] |
| Existing `InvokeModel` response usage | Migrate all AI calls to Converse | Not required for this phase: AWS recommends Converse generally, but the current Messages response already exposes the required counts. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages.html] |

**Installation:** No package installation is recommended. Regenerate locks only if implementation discovers a provider SDK defect that cannot be addressed with the installed versions. [VERIFIED: pyproject.toml and package-lock.json]

## Package Legitimacy Audit

No external package is added by this phase, so the Package Legitimacy Gate is not triggered. All named libraries above are already locked in the two canonical repositories; implementation must not introduce a new billing, URL, time-zone, idempotency, or notification package. [VERIFIED: pyproject.toml, uv.lock, and ../stoa-frontend/package-lock.json]

**Packages removed due to slopcheck [SLOP] verdict:** none.

**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```text
Pricing/Billing page
  │ parent selects paid plan + explicit active beneficiary IDs
  │ browser-generated logical key (retained across refresh/retry)
  ▼
Parent checkout API
  ├─ authenticate parent / revalidate bindings / canonicalize intent
  ├─ identical key + fingerprint ───────────────► replay same command/Session
  ├─ same key + different fingerprint ─────────► structured conflict
  └─ new intent
       ▼
  DynamoDB transaction: command + parent open-Session guard + public-ref lookup
       │
       ▼
  conditional provider-create lease + persisted call intent
       │ same opaque Stripe idempotency key and identical parameters
       ▼
  Stripe sandbox Checkout Session
       ├─ provider response ─► transactionally attach Session + lookups
       ├─ ambiguous timeout ─► same-key retry / provider recheck, never new command
       └─ plan change ───────► retrieve; expire only if open; prove terminal; supersede

Stripe browser redirect ─► fixed Web result path + opaque STOA ref
                              │
                              ▼
                         GET command projection
                         confirming / active / not_completed / support_needed

Stripe signed webhook (raw body)
  ▼
signature verification → durable event inbox/dedupe → fact processor/retrieval
                                                     │
                      expected first invoice paid? ──┤
                      matching subscription active? ─┤ no → retain facts/confirming
                                                     │ yes
                                                     ▼
 DynamoDB transaction: command outcome + billing projection + explicit grants
                     + plan version + allowance version + audit evidence
       ├─► Parent / student / admin Query projections
       ├─► Weekly token/support admission
       └─► Payment-method safe summary → per-recipient reminder intents

Bedrock request
  ▼
weekly reservation → InvokeModel → provider usage evidence
  ├─ validation + durable/readable result → finalize actual user debit
  └─ terminal undelivered result → release user reservation, retain provider cost
```

The diagram keeps three independent service boundaries explicit: browser navigation is a hint, Stripe signed/provider evidence is external truth, and DynamoDB is STOA’s durable command/projection truth. Only the signed-fact transaction crosses from confirming to active. [VERIFIED: 476-CONTEXT.md] [CITED: https://docs.stripe.com/billing/subscriptions/webhooks]

### Recommended Project Structure

```text
src/stoa/
├── models/
│   ├── billing.py                 # Four-plan IDs, command/fact/projection DTOs
│   └── allowance.py               # Week, reservation, usage-evidence DTOs
├── db/repositories/
│   ├── checkout_command_repo.py   # command/guard/lookups/leases/transactions
│   ├── billing_fact_repo.py       # event inbox and provider facts
│   └── allowance_repo.py          # token/support reservation/finalization
├── services/
│   ├── subscription_service.py    # provider adapter and public billing orchestration
│   ├── billing_reconciliation_service.py
│   ├── entitlement_service.py
│   ├── allowance_service.py
│   ├── ai_service.py              # returns answer plus provider usage evidence
│   └── payment_reminder_service.py
├── routers/
│   ├── parents.py                 # create/status/recheck/supersede/manage beneficiaries
│   ├── billing.py                 # signature-authenticated webhook ingest
│   └── admin.py                   # read/recheck only
└── tests/                         # focused state-machine and failure-injection tests

../stoa-frontend/src/
├── services/billing/              # typed create/status/recheck API
├── hooks/billing/                 # Query polling and mutation identity lifecycle
├── pages/billing/                 # authoritative Billing and result page
├── pages/pricing/                 # one-to-one plan entry
└── components/billing/            # beneficiaries, allowances, reminder, support state
```

Keep `subscription_service.py` as the public orchestration/provider seam, but move persistence-heavy state machines into focused repositories/services rather than extending the existing 3,000-line module further. This recommendation preserves the current router contracts and reusable provider/readiness helpers while making transaction invariants testable. [VERIFIED: codebase grep]

### Pattern 1: Durable Command Before Provider Mutation

**What:** Persist an immutable command intent, parent-scoped open guard, public reference lookup, and provider-call intent before calling Stripe. The intent fingerprint must cover canonical plan, sorted beneficiary IDs, parent identity, price/catalog version, and environment/mode; it must not include mutable timestamps or browser URLs. [VERIFIED: 475-CONTEXT.md]

**When to use:** Checkout creation, same-operation retry, ambiguous provider timeout, response loss after local commit, and explicit plan supersession.

**Prescriptive lifecycle:**

1. Require an `Idempotency-Key` (or equivalently named typed field plus header) generated once per user checkout intent; retain it in browser session storage until the command is terminal. The backend remains authoritative across tabs and devices. [VERIFIED: 476-CONTEXT.md]
2. Transactionally create `CHECKOUT_COMMAND#<id>`, `CHECKOUT_OPEN#<parent>`, and `CHECKOUT_PUBLIC#<hash>` with conditional nonexistence. A retry with the same key loads the command; a fingerprint mismatch returns `checkout_idempotency_mismatch`. [VERIFIED: 475-CONTEXT.md]
3. Acquire a short conditional provider-call lease and store `provider_request_started_at`, immutable request fingerprint, and opaque provider-key digest before the network call. The Stripe key should be a versioned HMAC/digest of the internal command ID, contain no PII, and remain under Stripe’s 255-character limit. [CITED: https://docs.stripe.com/api/idempotent_requests]
4. Call `stripe.checkout.Session.create(..., idempotency_key=stable_key)` with identical parameters on ambiguous retries. Attach Session ID/status/expiry in a transaction; return the stored Session URL only to the authenticated owner. [CITED: https://docs.stripe.com/api/idempotent_requests]
5. Never release the open guard because the HTTP caller disconnected. Release it only after provider terminal proof (`expired`, definitively not completed, or locally active/settled) or a proven supersession. [CITED: https://docs.stripe.com/api/checkout/sessions]

Stripe returns the saved first result—including a `500`—for a retained key and rejects a reused key with different parameters. Because a pruned key can create a new request, an old ambiguous command must move to support-needed rather than silently retry with a newly derived key. [CITED: https://docs.stripe.com/api/idempotent_requests]

### Pattern 2: Retrieve–Expire–Supersede

**What:** A changed plan is a separate command only after the old Session’s payability is resolved. Retrieve the old Session; if it is `open`, request expiration with an idempotent local effect record; if it is `complete`, reconcile payment/subscription instead of creating a second Session; if provider outcome remains unknown, keep the guard and surface support needed. [CITED: https://docs.stripe.com/api/checkout/sessions/expire]

**When to use:** Parent confirms a plan change while checkout is pending.

Stripe allows expiration only for `open` Sessions, and an expired Session can no longer be completed. A complete Session can still have payment processing in progress, so “complete” is not sufficient proof that starting a replacement is safe. [CITED: https://docs.stripe.com/api/checkout/sessions/expire] [CITED: https://docs.stripe.com/api/checkout/sessions]

### Pattern 3: Fact-Oriented Webhook Convergence

**What:** Verify the raw request with the official SDK; record event ID and a semantic duplicate identity `(event.type, data.object.id)`; store facts by provider object; then reconcile against current provider objects. Do not reduce all lifecycle changes to one timestamp-ranked enum. [CITED: https://docs.stripe.com/webhooks/signature] [CITED: https://docs.stripe.com/webhooks]

**Activation predicate:**

```text
signed_event_observed
AND expected_initial_invoice.id == paid_invoice.id
AND expected_initial_invoice.paid == true
AND subscription.id == command.subscription_id
AND subscription.status == "active"
AND customer/price/environment/beneficiaries match immutable command intent
AND Stripe objects are sandbox objects
```

`invoice.paid` is the authoritative payment event, but Stripe tells integrations to provision only when the subscription is also active. The event processor should store whichever fact arrives first and retrieve missing objects; it must not depend on delivery order. [CITED: https://docs.stripe.com/billing/subscriptions/webhooks] [CITED: https://docs.stripe.com/webhooks]

The activation transaction updates the command, billing projection, explicit grant records, effective plan/version, and allowance version exactly once under conditional state/version checks. A family has at most three beneficiaries, so the bounded write set fits DynamoDB’s 100-item transaction limit. [VERIFIED: 476-CONTEXT.md] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/APIReference/API_TransactWriteItems.html]

Keep separate dimensions for checkout state, invoice facts, subscription lifecycle, entitlement lifecycle, and scheduled transition. A simple “latest event timestamp wins” state loses information and is wrong under Stripe’s delivery contract. [CITED: https://docs.stripe.com/webhooks]

### Pattern 4: Explicit Beneficiary Grants and Monotonic Plan Transitions

**What:** Persist explicit `PLAN_GRANT#<parent>#<student>` records that reference the active subscription/plan version. Validate every selected student against Phase 475’s active, bidirectional relationship contract at command creation and again at activation. Do not derive family coverage by scanning all children. [VERIFIED: 475-CONTEXT.md] [VERIFIED: codebase grep]

**Transitions:**

- New activation publishes selected grants only after the joint provider predicate. [VERIFIED: 476-CONTEXT.md]
- Upgrade publishes the higher plan/version immediately while counters retain the same Zurich week and already-finalized usage. [VERIFIED: 476-CONTEXT.md]
- Cancellation/downgrade records a scheduled transition at the paid `current_period_end`; it does not immediately rewrite the plan. [VERIFIED: 476-CONTEXT.md]
- Renewal failure starts one three-day local grace window per delinquency identity; duplicates do not move the deadline. A later paid invoice clears grace; an unresolved deadline transitions to `free_trial` once. [VERIFIED: 476-CONTEXT.md]
- Downgrade never deletes attachments. Existing attachment enforcement already has 5 GB free/15 GB paid constants; only new uploads must be blocked above the effective limit. [VERIFIED: codebase grep]

### Pattern 5: Provider Usage Evidence + Reservation + Finalization

**What:** Change the AI provider boundary to return a typed result containing validated content plus immutable provider evidence: model/inference profile, provider message/request correlation, `input_tokens`, `output_tokens`, stop reason, observation timestamp, and logical effect ID. Never store prompt/answer content in the redacted usage evidence row. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html]

**State machine:**

```text
available = budget - finalized - active_reservations

admission
  └─ conditional reservation(input preflight, bounded max output, effect_id)
       └─ provider response → immutable provider_usage_observed(actual input/output)
            ├─ technical+safety validation and durable readable result
            │    └─ finalize exact actual debit + release reservation (one transaction)
            └─ terminal undelivered
                 └─ release user reservation + mark restored
                    (provider evidence/cost remains immutable)
```

For input admission, use Amazon’s provider token-count operation against the identical request. AWS says CountTokens is model-specific and matches the charged count for the same input; CRIS-only Claude models require the `bedrock-mantle` count endpoint because the runtime SDK method does not target them. Validate this path against the configured EU inference profile in Wave 0 before relying on it. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html]

Reserve the request’s bounded `max_tokens` for output and finalize from the response’s actual `usage.output_tokens`. Do not use Bedrock service-quota token burndown as the user debit: AWS documents separate quota accounting, including output multipliers for some Claude models, while the Messages response exposes actual input/output token counts. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html] [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html]

Build the week identity from the `Europe/Zurich` local Monday date/ISO week and persist both local identity and UTC start/end instants. Compute the next boundary by local calendar date then convert to UTC; never add 604,800 seconds to a prior UTC boundary across DST. `zoneinfo` supplies IANA rules. [CITED: https://docs.python.org/3/library/zoneinfo.html]

Inventory every `InvokeModel` caller. Current student answer/hint paths are user-facing, while report/title/background generations may be system costs; every call must be explicitly classified as user-allowance or provider-cost-only so the phase does not accidentally charge a student for internal generation. [VERIFIED: codebase grep]

### Pattern 6: One Support Case, One Admission Debit

**What:** Debit teacher-support allowance when a case is successfully admitted, keyed by the durable support case ID. Messages and replies reference that case and never debit again. Use `(student, Zurich week)` counters for `teacher_supported` and `(family subscription/grant version, Zurich week)` for the shared family counter. [VERIFIED: 476-CONTEXT.md]

Existing question/practice help events are request-count ledger events and currently are not quota-enforced, so they are useful as integration points but not as the new allowance source of truth. [VERIFIED: codebase grep]

### Pattern 7: Safe Payment-Method Projection and Reminder Fan-Out

**What:** Resolve the payment method actually used/defaulted for the subscription rather than selecting an arbitrary customer method. Persist only provider ID digest, brand, last four, expiry month/year, source subscription, and observation/version; never persist full PAN/CVC. Stripe exposes safe card summary fields and supports subscription-specific default methods. [CITED: https://docs.stripe.com/api/payment_methods/object] [CITED: https://docs.stripe.com/billing/subscriptions/payment-methods-setting]

Compute month end with `calendar.monthrange(year, month)` in `Europe/Zurich`, subtract seven local calendar days, and schedule a logical reminder keyed by `(payment_method_digest, exp_year, exp_month)`. Fan out separate delivery identities for each recipient and channel. Replacement/update resolves the persistent reminder and permits a new identity for the new method/month. [CITED: https://docs.python.org/3/library/calendar.html] [VERIFIED: 476-CONTEXT.md]

The current profile schema has email verification status, but repository search did not find a durable bounce/suppression/deliverability source. Until such a source is defined, “verified” alone must not be assumed deliverable; the planner must add a conservative email-eligibility resolver and use in-app only when deliverability is unknown. [VERIFIED: codebase grep]

### Pattern 8: Authoritative Web Server State

**What:** Generate a random browser key when a checkout intent begins, persist it across refresh, and submit `{plan, beneficiaryIds}` without callback URLs. TanStack Query owns command/billing polling; the result URL contains only the opaque STOA reference. Clear the retained browser key only at a server-declared terminal state. [VERIFIED: ../stoa-frontend/AGENTS.md] [VERIFIED: 476-CONTEXT.md]

Use one fixed result route and map backend states to exactly `confirming`, `active`, `not_completed`, and `support_needed`. A “recheck” mutation targets the same public reference/command, never the create endpoint. Disable new checkout while the server reports an open command; backend guards remain authoritative under multiple tabs. [VERIFIED: 476-CONTEXT.md]

### Anti-Patterns to Avoid

- **Provider-first creation:** Calling Stripe before persisting a command recreates DATA-002 when local writes fail. [VERIFIED: codebase grep]
- **Stripe cache as database:** The provider key may be pruned; local command retention must be longer. [CITED: https://docs.stripe.com/api/idempotent_requests]
- **Browser success as payment:** Checkout `complete` may still mean payment processing; only signed invoice/subscription proof activates. [CITED: https://docs.stripe.com/api/checkout/sessions]
- **Global event timestamp ordering:** Stripe does not guarantee delivery order. [CITED: https://docs.stripe.com/webhooks]
- **Invoice or subscription fact alone:** Stripe specifically couples `invoice.paid` with active subscription status for provisioning. [CITED: https://docs.stripe.com/billing/subscriptions/webhooks]
- **All-child entitlement scan:** It silently grants current/future children and violates explicit beneficiary selection. [VERIFIED: 476-CONTEXT.md]
- **Daily request counters:** They cannot satisfy provider-reported weekly input/output accounting. [VERIFIED: codebase grep]
- **Finalize before durable result:** It can charge allowance for an unreplayable response. [VERIFIED: 476-CONTEXT.md]
- **Conflate user debit with provider cost:** A restored user allowance does not erase an already-incurred Bedrock request. [VERIFIED: 476-CONTEXT.md]
- **One notification batch outcome:** One unusable email must not suppress other recipients or in-app delivery. [VERIFIED: 476-CONTEXT.md]
- **Hidden plan translations:** `standard` is already translated to both `student` and `family` in current Web code, so preserving translation makes migration ambiguous. [VERIFIED: codebase grep]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stripe retry safety | In-memory click lock or random key per attempt | Stripe idempotency option plus durable STOA command/guard | Provider and local lifetimes differ; both are required. [CITED: https://docs.stripe.com/api/idempotent_requests] |
| Webhook authentication | New bespoke signature parser | Installed Stripe SDK over untouched raw body | Stripe documents raw-body requirements and separate endpoint secrets. [CITED: https://docs.stripe.com/webhooks/signature] |
| Cross-item activation | Sequential profile/grant/counter writes | Existing DynamoDB `TransactWriteItems` repository pattern | Atomic all-or-nothing write is required for plan/grant/allowance convergence. [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html] |
| URL security | Prefix/regex checks on arbitrary URL strings | Server construction from parsed exact configured origin + fixed path | Prefix checks admit lookalikes/credentials/wrong ports and retain needless browser control. [VERIFIED: docs/audit/full-project-audit.md] |
| Time-zone math | Fixed UTC offsets or seconds arithmetic | `zoneinfo`, aware `datetime`, local calendar dates | Europe/Zurich changes offset at DST boundaries. [CITED: https://docs.python.org/3/library/zoneinfo.html] |
| Tokenization | Character heuristics as final accounting | Bedrock CountTokens for admission and response `usage` for finalization | Tokenization is model-specific; provider fields are authoritative. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html] |
| Card storage | PAN/CVC capture or provider-object dump | Stripe-hosted Checkout plus minimal safe payment projection | Phase needs only brand/last4/expiry and forbids payment-capable secrets. [CITED: https://docs.stripe.com/api/payment_methods/object] |
| Notification retry/dedupe | One-off email loops | Existing durable notification and delivery-intent repositories | Existing per-recipient identities and delivery state already solve partial failure. [VERIFIED: codebase grep] |
| Client server-state cache | Duplicate billing state in Zustand | Existing TanStack Query | Billing is authoritative server state and must be invalidated/polled consistently. [VERIFIED: ../stoa-frontend/AGENTS.md] |

**Key insight:** No single provider or library supplies the end-to-end invariant. Stripe protects a provider POST, DynamoDB protects STOA’s state, and the durable command binds them across timeouts and asynchronous events. [CITED: https://docs.stripe.com/api/idempotent_requests] [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html]

## Runtime State Inventory

This phase is both a migration (`free/standard/premium/tutor_supported` → four one-to-one plan identities) and a provider-state convergence change, so source edits alone are insufficient. [VERIFIED: 476-CONTEXT.md]

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | DynamoDB user profiles store `subscription_tier`; billing summaries/requests/events store current/requested/previous tier and provider Price/Session/customer/subscription data; entitlement and usage records store `effective_plan`; Cognito custom attributes are initialized to `free`. The current Web maps `standard` to both `student` and `family`, making legacy `standard` semantically ambiguous. Live row counts were not queried during research. [VERIFIED: codebase grep] | Add a read-only preview/report and idempotent data migration. Resolve from authoritative Stripe Price/subscription plus explicit beneficiary choice; put ambiguous rows in `migration_review_required` without broadening access. Update Cognito/profile initialization. This is both a data migration and a code edit. |
| Live service config | Stripe Dashboard/sandbox contains Prices, Products, event destinations/API versions, Customers, open Sessions, Subscriptions, default payment methods, and events outside git. Backend configuration currently has only standard/premium Price IDs and success/cancel defaults; exact staging origin and three paid Price IDs are not present in repository config. [VERIFIED: codebase grep] | Read-only audit sandbox objects before implementation; configure `student`, `teacher_supported`, `family` recurring CHF/month Prices, exact environment Web origin, sandbox key, test webhook secret/event set/API version, and no-live-mode guard. Reconcile existing open Sessions/subscriptions before releasing the legacy guard. |
| OS-registered state | No launchd, systemd, pm2, Task Scheduler, or checked-in service registration tied to plan names was found in either canonical repository. [VERIFIED: repository search] | None for OS registration. Recheck deployment-managed scheduled jobs separately when the reminder/reconciliation scheduler is provisioned. |
| Secrets/env vars | Backend settings still expect `STRIPE_STANDARD_PRICE_ID`, `STRIPE_PREMIUM_PRICE_ID`, secret key, webhook secret, and legacy callback URL settings; the Web exposes payment/mock flags. No local `.env` file exists in either repository. Secret values and deployed environment variables were not inspected. [VERIFIED: codebase grep and environment probe] | Rename/create non-secret configuration keys for three paid Price IDs and exact Web origins; update secret-manager/deployment names without printing values. Keep sandbox and live credentials separate, reject `sk_live_` for Phase 476 evidence, and rotate nothing without operational approval. Code edit plus external config migration. |
| Build artifacts / installed packages | The Web repository has an existing `dist/` and installed `node_modules/`; generated artifacts can retain legacy strings after source edits. Backend bytecode/installed package metadata are not authoritative source. [VERIFIED: repository search] | Rebuild once through Phase 474’s verified release path; do not edit/commit `dist` or `node_modules`. No package rename/reinstall is required. |

**Canonical post-edit audit:** after repository strings are migrated, separately prove no legacy active plan value remains in DynamoDB/Cognito, Stripe sandbox metadata/config, deployed environment configuration, or newly built Web artifacts. Cosmetic CSS class names containing “premium” are not plan identity and should not be mechanically renamed. [VERIFIED: codebase grep]

## Common Pitfalls

### Pitfall 1: Durable Command Created Too Late

**What goes wrong:** Stripe succeeds, the process fails before local persistence, and the next request creates another payable Session. [VERIFIED: docs/audit/full-project-audit.md]

**Why it happens:** The current provider call occurs before billing summary/event/lookups are written. [VERIFIED: codebase grep]

**How to avoid:** Persist command/open guard/call intent first; retry the same provider key and parameters; attach the response conditionally. [CITED: https://docs.stripe.com/api/idempotent_requests]

**Warning signs:** Provider Session ID exists in Stripe but no command lookup exists locally; a recheck calls create with a new key. [VERIFIED: docs/audit/findings.json]

### Pitfall 2: Reusing a Key With Changed Intent

**What goes wrong:** A parent switches plan or beneficiaries but the same provider key is reused, causing Stripe’s parameter mismatch error or an incorrect replay. [CITED: https://docs.stripe.com/api/idempotent_requests]

**Why it happens:** Browser identity is treated as a button-click token instead of a canonical business-intent identity. [VERIFIED: 476-CONTEXT.md]

**How to avoid:** Store and compare an immutable fingerprint; require explicit supersession for changed intent; generate a new command/key only after the old Session is nonpayable. [VERIFIED: 476-CONTEXT.md]

**Warning signs:** Plan is not in the fingerprint; changed beneficiaries update a pending command in place. [VERIFIED: 475-CONTEXT.md]

### Pitfall 3: Treating Stripe `complete` or Redirect as Settlement

**What goes wrong:** Access activates while payment is still processing or while the subscription is incomplete. [CITED: https://docs.stripe.com/api/checkout/sessions]

**Why it happens:** Session completion, payment, and subscription lifecycle are collapsed into one “success” state. [VERIFIED: codebase grep]

**How to avoid:** Require the signed initial `invoice.paid` fact plus matching current active subscription; redirect/status only drives confirming UX. [CITED: https://docs.stripe.com/billing/subscriptions/webhooks]

**Warning signs:** `checkout.session.completed`, `payment_status`, browser query, or admin action directly writes active entitlement. [VERIFIED: codebase grep]

### Pitfall 4: One Timestamp for All Webhook Ordering

**What goes wrong:** A late-delivered but semantically necessary invoice or cancellation is ignored, or an older object snapshot regresses a newer entitlement. [CITED: https://docs.stripe.com/webhooks]

**Why it happens:** Current code compares every event’s `created` value with one billing-row timestamp. [VERIFIED: codebase grep]

**How to avoid:** Store object-specific facts, dedupe event and semantic identities, retrieve current objects, and apply guarded legal transitions. [CITED: https://docs.stripe.com/webhooks]

**Warning signs:** `if event.created < last_event_created: ignore` is the primary stale-event rule. [VERIFIED: codebase grep]

### Pitfall 5: Stripe API-Version Shape Drift

**What goes wrong:** The webhook adapter cannot find the subscription reference on Invoice objects after an event-destination version change. [CITED: https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects]

**Why it happens:** Since `2025-03-31.basil`, invoicing objects use `invoice.parent.subscription_details.subscription` in place of deprecated top-level fields. Event payload shape is governed by the event destination’s API version. [CITED: https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects] [CITED: https://docs.stripe.com/webhooks]

**How to avoid:** Pin/record the sandbox event destination version, implement a small version-aware extractor, and fixture-test the exact received shape. [CITED: https://docs.stripe.com/webhooks]

**Warning signs:** Tests use only hand-built legacy events with top-level `invoice.subscription`. [VERIFIED: codebase grep]

### Pitfall 6: Ambiguous Legacy `standard` Migration

**What goes wrong:** Existing families become single-student plans or a student plan silently expands to family coverage. [VERIFIED: codebase grep]

**Why it happens:** Current Web code maps both `student` and `family` to backend `standard`. [VERIFIED: codebase grep]

**How to avoid:** Preview migration using actual Stripe Price/subscription and explicit beneficiary evidence; quarantine ambiguous records for operator review. Never infer family from number of current children alone. [VERIFIED: 476-CONTEXT.md]

**Warning signs:** A global string replacement maps every `standard` row to one new value. [VERIFIED: codebase grep]

### Pitfall 7: Incorrect Weekly/DST Boundaries

**What goes wrong:** A Zurich week is one hour early/late around DST or usage is assigned to the wrong week. [CITED: https://docs.python.org/3/library/zoneinfo.html]

**Why it happens:** UTC offset or seven-day seconds arithmetic replaces local calendar arithmetic. [CITED: https://docs.python.org/3/library/zoneinfo.html]

**How to avoid:** Derive each Monday 00:00 from a Zurich local date and store its converted UTC instant; test both DST transitions. [CITED: https://docs.python.org/3/library/zoneinfo.html]

**Warning signs:** `start + timedelta(seconds=604800)` is used on UTC timestamps as the business rule. [VERIFIED: 476-CONTEXT.md]

### Pitfall 8: Provider Usage Captured but User Debit Finalized Too Early

**What goes wrong:** The provider incurs cost and user allowance is charged even though validation/storage fails and no stable replay exists. [VERIFIED: 476-CONTEXT.md]

**Why it happens:** Provider response receipt is treated as delivery completion. [VERIFIED: codebase grep]

**How to avoid:** Persist provider evidence separately; finalize user debit in the same transaction that commits the validated readable result; release only the user reservation for terminal non-delivery. [VERIFIED: 475-CONTEXT.md]

**Warning signs:** Token counter increments in `ai_service.py` before the question/conversation command stores a result. [VERIFIED: codebase grep]

### Pitfall 9: Free Trial Start Resets

**What goes wrong:** Profile edits, rebindings, or retrying activation grants another 14 days. [VERIFIED: 476-CONTEXT.md]

**Why it happens:** Trial expiry is computed from mutable account/profile update timestamps. [VERIFIED: codebase grep]

**How to avoid:** Conditional-write one immutable `first_student_activation_at`; derive expiry once and retain it across relationship/plan changes. [VERIFIED: 475-CONTEXT.md]

**Warning signs:** Missing trial date defaults to “now” on every entitlement read. [VERIFIED: 476-CONTEXT.md]

### Pitfall 10: Reminder Suppression Is Too Coarse

**What goes wrong:** One invalid email blocks all family recipients, or replacing a card does not clear the old persistent reminder. [VERIFIED: 476-CONTEXT.md]

**Why it happens:** One batch status represents all recipients/channels or identity omits payment-method version. [VERIFIED: codebase grep]

**How to avoid:** Use per-recipient/channel delivery intents and a reminder identity including payment method plus expiry month; resolve old projection on update. [VERIFIED: 476-CONTEXT.md]

**Warning signs:** A single `reminder_sent` boolean exists on the subscription row. [VERIFIED: 476-CONTEXT.md]

## Code Examples

Verified patterns from official sources, adapted to STOA’s existing Python/DynamoDB stack:

### Stripe Session Creation With Stable Provider Key

```python
# Source: https://docs.stripe.com/api/idempotent_requests
# `command` and its provider-call intent have already been persisted.
session = stripe.checkout.Session.create(
    mode="subscription",
    customer=command.provider_customer_id,
    line_items=[{"price": command.provider_price_id, "quantity": 1}],
    success_url=callback_url(command.public_ref, "return"),
    cancel_url=callback_url(command.public_ref, "return"),
    client_reference_id=command.provider_reference,
    metadata={"stoa_checkout_command": command.provider_reference},
    idempotency_key=command.stripe_idempotency_key,
)
```

The actual implementation should keep return parameters non-authoritative and avoid parent/student IDs in Stripe metadata. [CITED: https://docs.stripe.com/api/idempotent_requests]

### Exact Origin + Fixed Result Path

```python
# Source: https://docs.python.org/3/library/urllib.parse.html
from urllib.parse import urlencode, urlsplit, urlunsplit

APPROVED_RESULT_PATH = "/billing/checkout/result"

def validate_web_origin(configured: str, *, allow_http_localhost: bool) -> tuple[str, str]:
    parsed = urlsplit(configured)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("web_origin_must_be_an_origin")
    if parsed.path not in {"", "/"} or not parsed.hostname or parsed.scheme not in {"http", "https"}:
        raise ValueError("web_origin_must_be_an_origin")
    if parsed.scheme != "https" and not (allow_http_localhost and local):
        raise ValueError("web_origin_requires_https")
    return parsed.scheme, parsed.netloc

def callback_url(origin: tuple[str, str], public_ref: str) -> str:
    scheme, netloc = origin
    return urlunsplit((scheme, netloc, APPROVED_RESULT_PATH, urlencode({"ref": public_ref}), ""))
```

Validate every environment’s exact configured origin at startup; never substitute `Origin`, `Host`, forwarded headers, or a browser body field. [VERIFIED: docs/audit/full-project-audit.md]

### DST-Safe Zurich Week

```python
# Source: https://docs.python.org/3/library/zoneinfo.html
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")

def zurich_week(now_utc: datetime) -> tuple[str, datetime, datetime]:
    local_day = now_utc.astimezone(ZURICH).date()
    monday = local_day - timedelta(days=local_day.weekday())
    next_monday = monday + timedelta(days=7)
    start_local = datetime.combine(monday, time.min, ZURICH)
    end_local = datetime.combine(next_monday, time.min, ZURICH)
    iso = monday.isocalendar()
    return (
        f"{iso.year}-W{iso.week:02d}",
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )
```

### Capture Actual Bedrock Usage

```python
# Source:
# https://docs.aws.amazon.com/bedrock/latest/userguide/
# model-parameters-anthropic-claude-messages-request-response.html
payload = json.loads(response["body"].read())
usage = payload["usage"]
provider_result = AIProviderResult(
    content=validated_content(payload["content"]),
    model=str(payload.get("model") or settings.bedrock_model_id),
    provider_message_id=str(payload["id"]),
    input_tokens=int(usage["input_tokens"]),
    output_tokens=int(usage["output_tokens"]),
    stop_reason=str(payload.get("stop_reason") or "unknown"),
)
```

Return this typed result to the durable question/conversation effect; do not finalize allowance inside the low-level provider function. [VERIFIED: 475-CONTEXT.md]

### Fact-Based Activation Guard

```python
# Source: https://docs.stripe.com/billing/subscriptions/webhooks
def activation_ready(command, invoice, subscription) -> bool:
    return (
        invoice.id == command.initial_invoice_id
        and invoice.paid is True
        and subscription.id == command.subscription_id
        and subscription.status == "active"
        and invoice.customer == command.provider_customer_id
        and subscription.customer == command.provider_customer_id
        and invoice.livemode is False
        and subscription.livemode is False
    )
```

The transaction must repeat ownership, price, environment, and conditional command-version checks; this predicate is illustrative, not the entire authorization boundary. [VERIFIED: 476-CONTEXT.md]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Read Invoice subscription from top-level `invoice.subscription` | Read `invoice.parent.subscription_details.subscription` after verifying `parent.type` | Stripe API `2025-03-31.basil` | Pin/test event shape and maintain a small compatibility extractor for existing events. [CITED: https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects] |
| Assume webhook delivery order | Persist/dedupe facts and retrieve missing current objects | Current Stripe webhook contract | Event-created timestamp cannot be a global ordering oracle. [CITED: https://docs.stripe.com/webhooks] |
| Locally estimate tokens or count requests | Count provider input before inference and finalize actual response usage | Current Bedrock CountTokens/Messages APIs | Weekly allowance can use provider-specific counts while provider cost remains separate. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html] |
| Treat service-quota tokens as billable/user tokens | Use actual response input/output; keep quota burndown operational only | Current Bedrock quota guidance | Avoid output multipliers/max-token reservation becoming final user charges. [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html] |
| Mock-only Stripe Checkout proof | Real sandbox Checkout + signed webhook + Web projections | Phase 476 requirement | Test clocks/simulations can exercise renewal/grace/expiry without real funds. [CITED: https://docs.stripe.com/billing/testing] |

**Deprecated/outdated:**

- Active `free`, `standard`, `premium`, and `tutor_supported` plan identities are phase-owned migration inputs, not supported active aliases. [VERIFIED: 476-CONTEXT.md]
- Browser-submitted `successUrl`/`cancelUrl` and `_safe_url(...startswith...)` are prohibited callback patterns. [VERIFIED: docs/audit/full-project-audit.md]
- `invoice.paid`-alone, `subscription.active`-alone, and manual-admin activation are not payment success. [VERIFIED: 476-CONTEXT.md]
- Global `last_provider_event_at` suppression is not an adequate out-of-order strategy. [CITED: https://docs.stripe.com/webhooks]
- Existing daily question/chat/hint request limits are not the new paid allowance model. [VERIFIED: 476-CONTEXT.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | No implementation recommendation relies on an unverified factual claim. Exact staging origin, Stripe sandbox Price IDs/API version, legacy live-row mapping, and email-deliverability source are deliberately left as open questions rather than assumed. | Entire document | Planner must create discovery/checkpoint tasks for these external-state values. |

## Open Questions

1. **What exact staging Web origin and local origin/port list are approved?**
   - What we know: production defaults include `https://app.stoaedu.ch`, and current local Web commonly uses port 5173. [VERIFIED: codebase grep]
   - What's unclear: no locked exact staging origin or complete local allowlist is present. [VERIFIED: codebase grep]
   - Recommendation: Wave 0 should obtain explicit environment values and fail startup when missing; do not infer them from requests.

2. **How are legacy `standard` subscriptions divided between `student` and `family`?**
   - What we know: current Web maps both plans to `standard`, so the stored tier alone is insufficient. [VERIFIED: codebase grep]
   - What's unclear: Stripe sandbox/live Price/product history and existing beneficiary intent were not queried. [VERIFIED: environment probe]
   - Recommendation: produce a migration preview using provider Price/subscription evidence and require operator resolution for ambiguous rows before apply.

3. **What is the authoritative “deliverable email” signal?**
   - What we know: profile verification state exists, but no bounce/suppression/deliverability repository was found. [VERIFIED: codebase grep]
   - What's unclear: whether deployed SES/provider suppression state is available outside git. [VERIFIED: environment probe]
   - Recommendation: define a conservative resolver; unknown/bounced/suppressed means in-app-only, never “best effort” email.

4. **Does the deployed identity/configuration permit token counting for the configured EU Sonnet 4.6 path?**
   - What we know: the configured model is an EU cross-Region inference profile; AWS documents `bedrock-mantle` token counting for CRIS-only Claude and says the SDK does not expose that endpoint directly. [VERIFIED: codebase grep] [CITED: https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html]
   - What's unclear: endpoint availability, IAM `bedrock-mantle:CountTokens`, project resource, and exact model name in the target AWS account were not exercised. [VERIFIED: environment probe]
   - Recommendation: Wave 0 must run a no-content-leak probe against the exact request model; if unavailable, block hard quota admission rather than silently use character estimates.

5. **How should historical students without a recorded first activation timestamp be migrated?**
   - What we know: the locked rule is 14 days from first student activation, and current data did not store that invariant. [VERIFIED: 476-CONTEXT.md] [VERIFIED: codebase grep]
   - What's unclear: whether a trustworthy historical activation event exists in live data. [VERIFIED: environment probe]
   - Recommendation: preview available evidence and require a documented migration policy; never default to “now” per request.

6. **Which Stripe event-destination API version and payment methods are enabled in the sandbox?**
   - What we know: event shape depends on destination version, and Checkout `complete` can precede final processing. [CITED: https://docs.stripe.com/webhooks] [CITED: https://docs.stripe.com/api/checkout/sessions]
   - What's unclear: deployed sandbox destination configuration was not accessible from repository state. [VERIFIED: environment probe]
   - Recommendation: record/pin it in acceptance evidence and test the exact enabled methods; do not generalize card-only timing to asynchronous methods.

## Environment Availability

| Dependency | Required By | Available | Version / State | Fallback |
|------------|-------------|-----------|-----------------|----------|
| Backend Python virtualenv | Implementation/tests | ✓ | Python 3.12.13 | — [VERIFIED: environment probe] |
| `uv` | Dependency sync/reproducibility | ✓ | 0.11.16 | Existing `.venv` for read-only tests. [VERIFIED: environment probe] |
| pytest | Focused backend validation | ✓ | 9.0.3; existing billing suite 35 passed in 5.59s with `PYTHONPATH=.` | — [VERIFIED: environment probe] |
| Node/npm | Web build/E2E | ✓ | Node 26.0.0, npm 11.12.1 | CI’s approved LTS runner if Node 26 compatibility differs. [VERIFIED: environment probe] |
| Playwright | Web browser proof | ✓ package | 1.60.0; browser executable not independently probed | Phase 474 staging runner. [VERIFIED: environment probe] |
| AWS CLI | Read-only identity/config probes and evidence | ✓ CLI | 2.34.58 | Boto3/admin evidence endpoint. [VERIFIED: environment probe] |
| AWS credentials/Bedrock/DynamoDB access | Real provider/token and persistence proof | ? | Not probed; no authority inferred | Focused mocks only for development, not exit evidence. [VERIFIED: environment probe] |
| Stripe Python SDK | Backend provider adapter | ✓ | 15.2.0 | — [VERIFIED: environment probe] |
| Stripe CLI | Local webhook forwarding/resend | ✗ | Not installed | Public sandbox endpoint/Workbench delivery for acceptance; CLI is optional. [VERIFIED: environment probe] |
| Stripe sandbox key, webhook secret, Prices, destination | V9BILL-04 | ✗ locally / external unknown | No local `.env`; repository values are empty/default config | Authorized sandbox secrets/config must be supplied; no mock fallback for exit evidence. [VERIFIED: environment probe] |
| Docker CLI | Optional local isolation | ✓ CLI | 29.6.1; daemon not needed/probed for this phase | Direct venv/Web runner. [VERIFIED: environment probe] |
| Context7 | Documentation lookup | ✗ | MCP and `ctx7` CLI unavailable | Official Stripe/AWS/Python documentation used. [VERIFIED: environment probe] |

**Missing dependencies with no fallback:**

- Authorized Stripe sandbox configuration and a reachable signed webhook destination are required for V9BILL-04 exit evidence. [VERIFIED: 476-CONTEXT.md]
- Authorized AWS access to the exact Bedrock/DynamoDB test environment is required for integrated token/persistence evidence; mocks cannot close the phase. [VERIFIED: 474-CONTEXT.md]

**Missing dependencies with fallback:**

- Stripe CLI is absent, but Workbench/public sandbox delivery can exercise signed webhooks. [CITED: https://docs.stripe.com/webhooks]
- Context7 is absent, but current official provider documentation was available and used. [VERIFIED: environment probe]

## Validation Architecture

### Test Framework

| Property | Backend | Web |
|----------|---------|-----|
| Framework | pytest 9.0.3 + pytest-asyncio 1.4.0 + moto 5.2.1 + time-machine 3.2.0 [VERIFIED: uv.lock] | Playwright 1.60.0, TypeScript 5.9.3, Vite 6.4.3 [VERIFIED: ../stoa-frontend/package-lock.json] |
| Config file | `pyproject.toml`, `tests/conftest.py`, Phase 474 pytest guard [VERIFIED: codebase grep] | `../stoa-frontend/playwright.config.ts` [VERIFIED: codebase grep] |
| Quick run command | `PYTHONPATH=. .venv/bin/pytest tests/test_billing_checkout_commands.py tests/test_billing_webhook_convergence.py tests/test_token_allowances.py -q -x` | `npm run typecheck && npm run test:e2e -- billing-paid-access.spec.ts --project=chromium` |
| Full suite command | Phase 474 bounded full pytest/mypy/release command from its generated gate artifact; do not invent a second global gate. [VERIFIED: 474-CONTEXT.md] | `node scripts/verify-release.mjs verify` plus the Phase 474 locked E2E invocation with `--fail-on-flaky-tests`. [VERIFIED: 474-RESEARCH.md] |

The current billing test suite is healthy (`35 passed`), but it asserts that `invoice.paid` alone activates legacy tiers. Treat it as a migration baseline, not acceptance of the new state machine. [VERIFIED: environment probe] [VERIFIED: codebase grep]

The current Playwright config forces `VITE_ENABLE_MOCK_CHECKOUT=true` and `VITE_ENABLE_PAYMENT=false`; existing billing tests intercept routes or use a virtual checkout. Add a distinct real-sandbox project/config that cannot silently fall back to mocks and whose credentials/endpoints come from the authorized test environment. [VERIFIED: codebase grep]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| V9BILL-01 | Concurrent identical create calls, response timeout retry, refresh, and repeat click return one command/Session; changed intent conflicts; supersession proves old Session nonpayable | unit + repository concurrency + provider contract | `PYTHONPATH=. .venv/bin/pytest tests/test_billing_checkout_commands.py -q -x` | ❌ Wave 0 |
| V9BILL-02 | Provider success/local attach failure, local success/HTTP timeout, duplicate Web retry, lease recovery, delayed event, and admin recheck converge one support state | failure-injection integration | `PYTHONPATH=. .venv/bin/pytest tests/test_billing_reconciliation.py -q -x` | ❌ Wave 0 |
| V9BILL-03 | Exact production/staging/local origins; fixed paths; reject lookalike, userinfo, encoded delimiter/backslash, scheme-relative, wrong port, wildcard, query/fragment base, arbitrary HTTPS | parameterized unit/API | `PYTHONPATH=. .venv/bin/pytest tests/test_billing_callback_urls.py -q -x` | ❌ Wave 0 |
| V9BILL-04 | Real sandbox browser → Stripe hosted checkout → signed webhook → exact-once grant/allowance → parent/admin Web projection; evidence asserts sandbox mode | Playwright E2E + provider integration | `npm run test:e2e -- billing-paid-access.spec.ts --project=stripe-sandbox` | ❌ Wave 0 |
| D-01/D-02 | Four identities agree across API, storage, Prices, Pricing/Billing UI, evidence; no active legacy translation | contract/migration | `PYTHONPATH=. .venv/bin/pytest tests/test_plan_identity_migration.py -q -x && npm run typecheck` | ❌ Wave 0 |
| D-13/D-17 | Both event orders, duplicates by same/different Event IDs, equal timestamps, stale subscription snapshots, invalid signature, and API-version Invoice shapes | state-machine/property matrix | `PYTHONPATH=. .venv/bin/pytest tests/test_billing_webhook_convergence.py -q -x` | ❌ Wave 0 |
| D-14–D-16 | Explicit one/up-to-three grants, inactive binding refusal, immediate upgrade without reset, end-period downgrade, three-day grace/recovery, storage nondeletion | integration + time travel | `PYTHONPATH=. .venv/bin/pytest tests/test_paid_entitlement_transitions.py -q -x` | ❌ Wave 0 |
| D-18–D-23 | Input/output reservation, actual finalization, duplicate replay, terminal restore/provider cost retention, disconnect no restore, Zurich DST weeks, immutable 14-day trial | unit + transaction + provider contract | `PYTHONPATH=. .venv/bin/pytest tests/test_token_allowances.py tests/test_free_trial_window.py -q -x` | ❌ Wave 0 |
| D-20 | One successfully admitted case debits once; messages/replies do not; family shared/teacher per-beneficiary week limits | unit + integration | `PYTHONPATH=. .venv/bin/pytest tests/test_teacher_support_allowances.py -q -x` | ❌ Wave 0 |
| D-24–D-27 | Month end/seven-day schedule, PM replacement clearing, same identity once, parent+beneficiaries, email eligibility, per-recipient/channel failure isolation | unit + notification integration | `PYTHONPATH=. .venv/bin/pytest tests/test_payment_method_expiry_reminders.py -q -x` | ❌ Wave 0 |

### Required Failure-Injection Matrix

| Injection Point | Expected Durable Outcome |
|-----------------|--------------------------|
| Fail before command transaction | No provider call and no open guard. [VERIFIED: 476-CONTEXT.md] |
| Fail after command/guard, before Stripe | Same command re-acquires lease and creates one Session with the same key. [CITED: https://docs.stripe.com/api/idempotent_requests] |
| Stripe succeeds, client sees timeout | Command remains provider-outcome-unknown; same-key retry/recheck attaches that Session, never a second command. [CITED: https://docs.stripe.com/api/idempotent_requests] |
| Stripe response received, local attach transaction fails | Provider lookup/reconciliation recovers; open guard prevents another payable Session. [VERIFIED: docs/audit/full-project-audit.md] |
| Local attach succeeds, HTTP response is lost | Browser retry loads and returns the same command/Session. [VERIFIED: 476-CONTEXT.md] |
| Duplicate signed Event ID | Inbox reports duplicate and no entitlement/counter mutation repeats. [CITED: https://docs.stripe.com/webhooks] |
| Different Event IDs for same type/object | Semantic dedupe/reconciliation reaches same facts and one activation. [CITED: https://docs.stripe.com/webhooks] |
| Subscription event before invoice, then reverse | Both orders retain facts and activate once only when joint predicate holds. [CITED: https://docs.stripe.com/webhooks] |
| Activation transaction fails halfway | No command/grant/allowance partial state; retried processor completes all. [CITED: https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html] |
| Bedrock response arrives, result validation/storage fails terminally | Provider evidence remains; user reservation is restored; no final debit. [VERIFIED: 476-CONTEXT.md] |
| Browser disconnect after durable result | Replay returns the result and final debit remains. [VERIFIED: 476-CONTEXT.md] |
| One reminder email fails | Other recipients/channels proceed and billing state remains unchanged. [VERIFIED: 476-CONTEXT.md] |

### Sampling Rate

- **Per task commit:** run the focused file(s) owned by that task and Web typecheck for API-type changes. [VERIFIED: 474-CONTEXT.md]
- **Per wave merge:** run all Phase 476 focused backend tests plus Web lint/typecheck/build and mock-independent billing E2E where provider access is not required. [VERIFIED: 474-CONTEXT.md]
- **Provider integration wave:** run the real Stripe sandbox E2E once per immutable candidate and capture request/event/object IDs, command/reconciliation rows, parent/admin screenshots/API projections, and `livemode=false`. [CITED: https://docs.stripe.com/testing] [VERIFIED: 474-CONTEXT.md]
- **Phase gate:** run Phase 474’s build-once common backend/Web gate, then the authorized sandbox journey without rebuilding or production mutation. [VERIFIED: 474-CONTEXT.md]

### Wave 0 Gaps

- [ ] `tests/test_billing_checkout_commands.py` — V9BILL-01 command/guard/replay/supersession/concurrency.
- [ ] `tests/test_billing_reconciliation.py` — V9BILL-02 partial failure/lease/admin recheck.
- [ ] `tests/test_billing_callback_urls.py` — V9BILL-03 structural negative matrix.
- [ ] `tests/test_billing_webhook_convergence.py` — signed facts, duplicates, event orders, API versions.
- [ ] `tests/test_plan_identity_migration.py` — four-plan schema and preview/apply conflicts.
- [ ] `tests/test_paid_entitlement_transitions.py` — explicit grants, upgrade/downgrade/grace/storage.
- [ ] `tests/test_token_allowances.py` — reservation/evidence/finalize/restore/DST.
- [ ] `tests/test_free_trial_window.py` — immutable first activation/expiry.
- [ ] `tests/test_teacher_support_allowances.py` — case admission identity and plan limits.
- [ ] `tests/test_payment_method_expiry_reminders.py` — month end/fan-out/eligibility/dedupe.
- [ ] `../stoa-frontend/tests/e2e/billing-paid-access.spec.ts` — authoritative result/projection and real sandbox journey.
- [ ] Separate Playwright `stripe-sandbox` project/config with mock/demo flags prohibited and secret-safe environment preflight.
- [ ] Provider fixture capture for the exact Stripe event-destination API version, including post-Basil Invoice shape.
- [ ] Authorized no-live-charge sandbox preflight (`sk_test_`, test Prices, test endpoint secret, every object/event `livemode=false`).
- [ ] Bedrock CountTokens/InvokeModel exact-model probe and IAM check.

## Security Domain

The following stack-specific controls use the project’s required ASVS category checklist as a verification organizer; OWASP describes ASVS as a basis for testing Web application technical security controls and secure-development requirements. [CITED: https://owasp.org/www-project-application-security-verification-standard/]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing Cognito JWT authentication for parent/student/admin APIs; webhook uses provider signature authentication. [VERIFIED: codebase grep] [CITED: https://docs.stripe.com/webhooks/signature] |
| V3 Session Management | yes | Browser retains an opaque logical checkout key/reference only; no Stripe secret or payment credential enters browser storage. Server command ownership is checked on every status/recheck. [VERIFIED: 476-CONTEXT.md] |
| V4 Access Control | yes | Parent can manage only self and active bound beneficiaries; student receives read-only safe state; admin rechecks but cannot assert payment success. [VERIFIED: 476-CONTEXT.md] |
| V5 Input Validation | yes | Pydantic request models, four-plan literal, bounded beneficiary IDs, immutable fingerprint, structural configured-origin parsing, fixed callback paths, Stripe object/customer/price/environment matching. [VERIFIED: codebase grep] |
| V6 Cryptography | yes | Official Stripe SDK signature verification; `secrets` for public refs; HMAC/SHA-256 for opaque derived identities; never hand-roll payment cryptography. [CITED: https://docs.stripe.com/webhooks/signature] |
| V7 Error/Logging | yes | Structured safe codes, correlation IDs, redacted Stripe IDs, no callback secret/card/prompt/answer leakage. [VERIFIED: 476-CONTEXT.md] |
| V8 Data Protection | yes | Persist only safe brand/last4/expiry and redacted usage evidence; keep provider credentials and full payment data out of APIs/evidence. [VERIFIED: 476-CONTEXT.md] |
| V10 Malicious Code | no new package path | No new dependencies; existing locks remain authoritative. [VERIFIED: package audit above] |
| V13 API/Web Service | yes | Required idempotency identity, ownership checks, conditional command versions, signed raw-body webhook, bounded polling/recheck. [VERIFIED: 476-CONTEXT.md] |

### Known Threat Patterns for FastAPI + Stripe + DynamoDB

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Arbitrary/lookalike callback redirects (SEC-008) | Spoofing / Information Disclosure | Remove callback URL input; parse exact configured origin at startup and append fixed path/opaque ref. [VERIFIED: docs/audit/full-project-audit.md] |
| Forged/replayed webhook | Spoofing / Tampering | Official SDK over raw body, correct endpoint secret/mode, event + semantic dedupe, object ownership match. [CITED: https://docs.stripe.com/webhooks/signature] [CITED: https://docs.stripe.com/webhooks] |
| Duplicate payable Session | Tampering / Repudiation | Parent open guard + durable command + stable Stripe key + retrieve/expire/supersede protocol. [CITED: https://docs.stripe.com/api/idempotent_requests] |
| Cross-parent command/ref access | Information Disclosure / Elevation of Privilege | High-entropy opaque public ref plus authenticated owner check; never authorize from ref alone. [VERIFIED: 476-CONTEXT.md] |
| Admin-forged paid state | Elevation of Privilege | Admin endpoint can retrieve/reconcile only; activation transaction requires signed invoice and active subscription evidence. [VERIFIED: 476-CONTEXT.md] |
| Test/live environment confusion | Tampering / Financial harm | Phase-specific test-only preflight rejects live key prefixes and requires `livemode=false` on all linked objects/events/evidence. [CITED: https://docs.stripe.com/keys] [CITED: https://docs.stripe.com/testing] |
| Stale webhook entitlement regression | Tampering | Object-specific fact model, provider retrieval, legal-transition CAS, immutable activation/grant version. [CITED: https://docs.stripe.com/webhooks] |
| Counter race/allowance overspend | Tampering | Conditional reservation with finalized + reserved totals and effect-ID dedupe. [VERIFIED: 475-CONTEXT.md] |
| Token evidence leaks learning content | Information Disclosure | Evidence stores counts/model/correlation/status only, never prompt/answer; role-specific authorization on exact counts. [VERIFIED: 476-CONTEXT.md] |
| Card data leakage | Information Disclosure | Stripe hosted Checkout; safe brand/last4/expiry projection only; redact IDs in parent/student and partially in admin. [CITED: https://docs.stripe.com/api/payment_methods/object] |
| Reminder enumeration/cross-family disclosure | Information Disclosure | Resolve recipients from explicit active grants; same safe summary only; one authenticated account per delivery intent. [VERIFIED: 476-CONTEXT.md] |
| Idempotency-key collision/mismatch | Tampering / Repudiation | Entropic browser key, authenticated scope, immutable fingerprint comparison, versioned non-PII provider derivation. [CITED: https://docs.stripe.com/api/idempotent_requests] |

### Security Verification Matrix

- Prove unsigned, wrong-secret, mutated-body, old/replayed semantic duplicate, and live-mode events cannot mutate billing. [CITED: https://docs.stripe.com/webhooks/signature]
- Prove callback configuration rejects credentials, lookalikes, wrong ports, encoded/backslash bypasses, query/fragment base origins, arbitrary HTTPS, wildcard, and request-origin inference. [VERIFIED: docs/audit/findings.json]
- Prove parent A cannot read/recheck/supersede parent B’s opaque command and a student cannot mutate billing. [VERIFIED: 476-CONTEXT.md]
- Prove admin cannot mark payment successful and logs/evidence never include keys, checkout URLs after terminal retention, PAN/CVC, prompt, or answer. [VERIFIED: 476-CONTEXT.md]
- Prove sandbox evidence contains only `sk_test_` configuration fingerprints and `livemode=false` provider objects; never print the actual secret. [CITED: https://docs.stripe.com/keys]

## Sources

### Primary (HIGH confidence)

- [Phase 476 CONTEXT](./476-CONTEXT.md) — locked business decisions, canonical references, integration points, and deferrals.
- [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests) — saved results, mismatch behavior, 255-character limit, and ≥24-hour pruning.
- [Stripe Checkout Sessions](https://docs.stripe.com/api/checkout/sessions) — Session lifecycle, status/payment semantics, and provider references.
- [Stripe expire Session](https://docs.stripe.com/api/checkout/sessions/expire) — open-only expiration and nonpayability after expiration.
- [Stripe subscription webhooks](https://docs.stripe.com/billing/subscriptions/webhooks) — `invoice.paid` plus active subscription provisioning and retry behavior.
- [Stripe webhook guide](https://docs.stripe.com/webhooks) — duplicate identities, non-ordering, retries, API versioning, and asynchronous handling.
- [Stripe signature guide](https://docs.stripe.com/webhooks/signature) — raw body, official library, and endpoint-secret rules.
- [Stripe Basil Invoice change](https://docs.stripe.com/changelog/basil/2025-03-31/adds-new-parent-field-to-invoicing-objects) — new parent subscription reference.
- [Stripe testing](https://docs.stripe.com/testing) and [Billing test clocks](https://docs.stripe.com/billing/testing) — simulated funds and lifecycle testing.
- [Stripe keys](https://docs.stripe.com/keys) — sandbox/live key separation.
- [Stripe payment methods](https://docs.stripe.com/api/payment_methods/object) and [subscription payment methods](https://docs.stripe.com/billing/subscriptions/payment-methods-setting) — safe card fields and default method semantics.
- [Bedrock Anthropic request/response](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-request-response.html) — actual response usage fields.
- [Bedrock CountTokens](https://docs.aws.amazon.com/bedrock/latest/userguide/count-tokens.html) — provider-specific preflight counts and CRIS/mantle constraint.
- [Bedrock token burndown](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html) — service-quota versus actual token accounting.
- [DynamoDB transactions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis.html) — atomicity, idempotency window, isolation, and limits.
- [Python `zoneinfo`](https://docs.python.org/3/library/zoneinfo.html), [`calendar`](https://docs.python.org/3/library/calendar.html), and [`urllib.parse`](https://docs.python.org/3/library/urllib.parse.html) — calendar/time-zone and structural URL primitives.
- [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) — security-control verification framework.
- Repository inspection of backend and `/Users/zhdeng/stoa-frontend` — current call ordering, tier drift, URL behavior, provider usage discard, notification patterns, tests, locks, and runtime state. [VERIFIED: codebase grep]

### Secondary (MEDIUM confidence)

- None. Critical provider claims were checked against current official documentation.

### Tertiary (LOW confidence)

- None. Unavailable external-state values are listed as open questions rather than asserted.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — existing locked dependencies and official provider/stdlib documentation; no new package.
- Architecture: HIGH — directly addresses inspected failure ordering and follows Stripe/DynamoDB documented semantics plus Phase 475 command conventions.
- Pitfalls: HIGH — observed in current code or explicitly documented by Stripe/AWS.
- Token admission: MEDIUM — response usage is verified, but exact configured EU CRIS CountTokens authorization/endpoint must be probed in Wave 0.
- Runtime migration: MEDIUM — source schemas are verified, but live DynamoDB/Cognito/Stripe row/object inventory was not authorized or available.
- Sandbox acceptance: MEDIUM — test architecture is specified, but credentials, destination, Price IDs, and live provider access are missing locally.

**Research date:** 2026-07-23
**Valid until:** 2026-08-22 for stable architecture; re-check Stripe event/API-version and Bedrock model/token-count documentation immediately before implementation.
