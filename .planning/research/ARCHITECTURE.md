# Architecture Research

**Domain:** Live payment provider rollout for the existing STOA FastAPI billing subsystem
**Researched:** 2026-06-11
**Confidence:** MEDIUM

## Standard Architecture

### System Overview

The right architecture for v4.4 is still a single backend billing domain inside the existing FastAPI app. Do not split payments into a separate service. The change is to stop treating `subscription_service.py` as one flat file that owns every concern and instead turn it into the orchestration boundary over smaller payment-focused components.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI Route Layer                         │
├─────────────────────────────────────────────────────────────────────┤
│  parents.py                 admin.py               billing.py      │
│  checkout + parent          readiness + ops        public Stripe   │
│  billing visibility         visibility + actions   webhook ingest  │
└───────────────┬──────────────────────┬───────────────────────┬─────┘
                │                      │                       │
┌───────────────▼──────────────────────▼───────────────────────▼─────┐
│                    Billing Domain / Service Layer                   │
├─────────────────────────────────────────────────────────────────────┤
│ subscription_service          existing orchestration facade         │
│ billing_readiness_service     config inspection + rollout gating    │
│ stripe_gateway               real Stripe SDK/API boundary          │
│ billing_webhook_service      verify + dedupe + project events      │
│ billing_ops_service          refunds/invoices/tax/dunning views    │
└───────────────┬──────────────────────────────┬──────────────────────┘
                │                              │
┌───────────────▼──────────────┐   ┌───────────▼──────────────────────┐
│ DynamoDB single-table        │   │ Stripe platform surfaces         │
├──────────────────────────────┤   ├──────────────────────────────────┤
│ SUBSCRIPTION_BILLING summary │   │ Checkout Sessions                │
│ BILLING event log            │   │ Webhooks                         │
│ Provider dedupe markers      │   │ Billing / Invoices               │
│ Provider lookup rows         │   │ Refunds / Credit Notes           │
│ Provider readiness snapshot  │   │ Stripe Tax / Smart Retries       │
│ Operator action audit rows   │   │ Dashboard payment methods/TWINT  │
└──────────────────────────────┘   └──────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `parents.py` | Parent checkout start and parent-visible billing state | Thin route layer over `subscription_service` and `billing_ops_service` |
| `admin.py` | Operator readiness, billing detail, refund/invoice/tax/dunning actions and evidence | Thin admin route layer over readiness and ops services |
| `billing.py` | Raw-body Stripe webhook ingress only | Single public endpoint that delegates immediately |
| `subscription_service.py` | Canonical STOA subscription ownership and orchestration | Existing facade retained, but reduced to coordination |
| `stripe_gateway.py` | All real Stripe API calls and provider object normalization | New SDK/API boundary, no router or table logic |
| `billing_webhook_service.py` | Signature verification, event dedupe, lookup resolution, state projection | New event-ingest component |
| `billing_readiness_service.py` | Redacted live-readiness computation and no-real-charge gating | New read-only/admin-focused service |
| `billing_ops_service.py` | Refund eligibility, invoice links, tax/accounting export, dunning projection | New admin/parent read model service |

## Recommended Project Structure

```text
src/
├── stoa/
│   ├── routers/
│   │   ├── parents.py                  # modify existing parent billing responses
│   │   ├── admin.py                    # add readiness and billing ops endpoints
│   │   └── billing.py                  # keep Stripe webhook endpoint thin
│   ├── services/
│   │   ├── subscription_service.py     # keep as orchestration boundary
│   │   ├── billing_readiness_service.py # new
│   │   ├── billing_webhook_service.py   # new
│   │   ├── billing_ops_service.py       # new
│   │   └── payment_provider/
│   │       └── stripe_gateway.py        # new Stripe-specific adapter
│   └── models/
│       └── billing.py                  # optional shared response/action models
└── tests/
    └── test_subscription_operations.py # extend existing focused billing tests
```

### Structure Rationale

- **Keep one billing domain:** v3.9 correctly kept manual requests, provider billing, and manual overrides under `subscription_service`. v4.4 should preserve that product boundary.
- **Add a provider adapter:** live rollout needs real Stripe calls. Those calls should not live in routers or in DynamoDB projection code.
- **Separate read models from ingest:** checkout creation, webhook ingestion, readiness inspection, and operator ops are different concerns with different failure modes.
- **Stay inside the current single-table architecture:** the scale and repo conventions do not justify a second database or a queue-first redesign yet.

## New Vs Modified Components

### Modified Components

| Component | Change |
|-----------|--------|
| `src/stoa/services/subscription_service.py` | Keep as the canonical subscription facade, but move Stripe API calls, webhook projection, and ops/readiness logic into focused helper services. |
| `src/stoa/routers/billing.py` | Keep `/billing/webhooks/stripe`, but delegate to `billing_webhook_service` and return richer processing metadata. |
| `src/stoa/routers/parents.py` | Extend `GET /parents/me/subscription/billing` to expose invoice/receipt links, payment-failure context, and dunning summary. Keep checkout path unchanged. |
| `src/stoa/routers/admin.py` | Add readiness, live-rollout evidence, refund handoff/action, invoice/tax export, and dunning visibility under the existing admin subscription namespace. |
| `tests/test_subscription_operations.py` | Add tests for readiness gating, live-disabled checkout refusal, lookup-row webhook resolution, invoice metadata projection, refund state, and dunning transitions. |
| `src/stoa/config.py` | Split credential presence from live-charge enablement and add explicit rollout/readiness config fields. |

### New Components

| Component | Why It Should Exist |
|-----------|---------------------|
| `src/stoa/services/payment_provider/stripe_gateway.py` | Real Stripe Checkout/refund/invoice retrieval calls need one isolated boundary with redaction and provider-specific request shaping. |
| `src/stoa/services/billing_readiness_service.py` | Admins need a computed, redacted live-readiness surface that is separate from any one customer billing record. |
| `src/stoa/services/billing_webhook_service.py` | Production webhook processing needs dedicated verification, idempotency, event mapping, and summary/index writes. |
| `src/stoa/services/billing_ops_service.py` | Refunds, invoices, tax handoff, and dunning are operator/read-model concerns, not checkout concerns. |
| `BILLING_PROVIDER_LOOKUP` rows | Current fallback webhook parent resolution scans billing summaries. Live rollout should replace that with O(1) provider-id lookup rows. |
| `BILLING_PROVIDER_READINESS` row | Readiness is environment/provider state, not parent state. It needs its own surface and audit trail. |
| `BILLING_OPERATOR_ACTION` rows or equivalent event entries | Refund requests, export generation, and rollout verification need append-only operator evidence. |

## Architectural Patterns

### Pattern 1: Separate Readiness State From Charge Enablement

**What:** Do not reuse `billing_status` or the current binary `stripe_live_charges_enabled` flag to answer rollout questions. Introduce a computed readiness model for the environment and keep charge enablement as a separate explicit switch.

**When to use:** Immediately in Phase 145 before any production checkout path is allowed.

**Trade-offs:** One more state surface to maintain, but it removes the most dangerous failure mode: live credentials accidentally implying live charging.

**Example:**
```python
def compute_rollout_state(settings: Settings) -> str:
    if not settings.stripe_api_key or not settings.stripe_webhook_secret:
        return "mock_or_incomplete"
    if not settings.stripe_live_charges_enabled:
        return "live_ready_but_blocked"
    return "live_enabled"
```

Recommended environment-level states:

- `mock`
- `stripe_test`
- `live_ready_but_blocked`
- `live_enabled`
- `rollback_blocked`

### Pattern 2: Provider Adapter Plus Local Projection

**What:** Stripe remains the source of truth for checkout, invoices, refunds, tax calculation, and retry scheduling. STOA stores a small local projection optimized for parent/admin visibility and entitlement decisions.

**When to use:** For all live Checkout and webhook work.

**Trade-offs:** Local state can lag provider state by one webhook, but the model stays simple and auditable.

**Example:**
```python
session = stripe_gateway.create_subscription_checkout(...)
subscription_service.record_checkout_pending(parent_id, session)

event = stripe_gateway.verify_and_parse_webhook(raw_body, signature)
billing_webhook_service.apply_provider_event(event)
```

This is the right place to use Stripe dynamic payment methods. Stripe’s current docs say Checkout can manage payment methods from the Dashboard and dynamically show eligible methods, which is the cleanest way to make TWINT readiness a provider capability instead of a separate STOA provider implementation.

### Pattern 3: Append-Only Billing Events With Provider Lookup Rows

**What:** Keep the existing event log and dedupe-marker approach, but add lookup rows keyed by provider customer/subscription/session identifiers.

**When to use:** Before production webhook verification.

**Trade-offs:** More writes per event, but far safer than table scans on webhook delivery paths.

**Example:**
```python
lookup_keys = [
    ("customer", customer_id),
    ("subscription", subscription_id),
    ("checkout_session", checkout_session_id),
]
for kind, provider_id in lookup_keys:
    put_lookup(kind=kind, provider_id=provider_id, parent_id=parent_id)
```

The existing `_find_parent_id_for_provider_object()` scan path should become a fallback only for migration, not the steady-state production design.

## Data Flow

### Request Flow

#### Parent Checkout

```text
Parent POST /parents/me/subscription/checkout
    ↓
parents.py
    ↓
subscription_service.create_checkout_session(...)
    ↓
billing_readiness_service.assert_checkout_allowed(...)
    ↓
stripe_gateway.create_checkout_session(...)
    ↓
Persist billing summary + lookup rows + checkout event
    ↓
Return checkout URL + requested tier + provider mode
```

#### Stripe Webhook

```text
Stripe webhook POST /billing/webhooks/stripe
    ↓
billing.py reads raw body only
    ↓
billing_webhook_service.verify_and_parse(...)
    ↓
Deduplicate by provider event id
    ↓
Resolve parent via lookup rows
    ↓
Project event into billing summary + event log + operator evidence
    ↓
Return received / deduplicated / processing-result metadata
```

#### Admin Operator Flow

```text
Admin GET/POST /admin/subscriptions/...
    ↓
admin.py
    ↓
billing_readiness_service or billing_ops_service
    ↓
Read summary rows + provider metadata + event log
    ↓
Optional Stripe action (refund) or export generation
    ↓
Append operator action evidence
    ↓
Return redacted status/result
```

### State Management

There are three separate state surfaces and they should stay separate:

1. **Environment rollout state**
   - Provider credentials present or absent
   - Webhook secret configured or absent
   - Live charge flag enabled or blocked
   - Price mapping complete or incomplete
   - TWINT capability state: `deferred`, `pending`, `active`, or `unsupported`

2. **Per-parent billing summary**
   - Existing `subscription_tier`, `billing_status`, provider ids
   - New invoice/refund/dunning projection fields
   - Last provider event metadata
   - Last webhook processing result metadata

3. **Append-only billing evidence**
   - Checkout creation events
   - Webhook events and dedupe outcomes
   - Refund requests/results
   - Invoice export generation
   - Readiness verification snapshots

### Key Data Flows

1. **Checkout gating flow:** readiness state must be checked before any live Checkout session is created.
2. **Webhook projection flow:** provider events should update STOA billing summary fields, not expose raw provider payloads directly to parent/admin APIs.
3. **Invoice/tax handoff flow:** invoice and tax metadata should be exported from local projection plus selected provider fields, not from ad hoc Dashboard screenshots.
4. **Refund flow:** operator input creates either a provider refund action or a documented handoff record; the local summary is updated only after provider confirmation or explicit pending state.
5. **Dunning flow:** Stripe remains retry engine; STOA projects retry state (`payment_failed`, `past_due`, `next_payment_attempt_at`, attempt count) for parent/admin visibility.

## Recommended State/Data Changes

### Existing `SUBSCRIPTION_BILLING#{parent_id}` Summary Row

Keep the current row and extend it with fields like:

- `provider_execution_mode` or keep `billing_mode` but make it explicit
- `provider_payment_method_type`
- `latest_invoice_id`
- `latest_invoice_status`
- `latest_invoice_url`
- `latest_invoice_pdf_url`
- `latest_receipt_url`
- `currency`
- `amount_due`
- `amount_paid`
- `tax_amount`
- `tax_country`
- `dunning_status`
- `dunning_attempt_count`
- `next_payment_attempt_at`
- `latest_refund_id`
- `latest_refund_status`
- `latest_refund_amount`
- `last_webhook_result`
- `last_webhook_request_id`

Do not store raw card data, raw webhook payloads, or secrets.

### New Lookup Rows

Add rows keyed by provider identifiers, for example:

- `BILLING_PROVIDER_LOOKUP#stripe#customer#{customer_id}`
- `BILLING_PROVIDER_LOOKUP#stripe#subscription#{subscription_id}`
- `BILLING_PROVIDER_LOOKUP#stripe#checkout_session#{session_id}`

Each lookup row should map back to `parent_id` and the canonical billing summary key.

### New Readiness Row

One environment-scoped readiness row is enough:

- `BILLING_PROVIDER_READINESS#stripe#production`

Suggested contents:

- secret refs present flags, not secret values
- price/product mapping completeness
- webhook endpoint configured flag
- live charge flag
- TWINT capability status
- latest verified by / verified at
- explicit `charge_execution_state`

## Provider-Specific Guidance

### Checkout And TWINT

- Use Stripe Checkout as the payment UI boundary.
- Prefer Stripe dynamic payment methods over hardcoding `payment_method_types`. Stripe’s docs say Checkout can manage payment methods from the Dashboard, which is the cleanest path for TWINT enablement.
- Model TWINT as a Stripe capability inside readiness, not as a new STOA provider.
- Keep TWINT blocked until capability state is verified because Stripe documents a pending onboarding state and explicit merchant-site requirements for TWINT.

### Webhooks

- Keep raw-body verification exactly on the public webhook route.
- Add `invoice.updated` support in addition to the current `invoice.payment_failed` path if Smart Retries or Billing automations are used, because Stripe documents that `next_payment_attempt` can move there.
- Preserve idempotency with provider-event markers.
- Return processing metadata suitable for operator evidence: event id, event type, mode, dedupe result, parent resolution path, and projection result.

### Refunds, Invoices, Tax, And Dunning

- Refunds: prefer Stripe-hosted refund primitives first. If Phase 146 implements actual refund actions, run them through `stripe_gateway` and store explicit pending/succeeded/failed states.
- Invoices: surface `hosted_invoice_url` and invoice PDF links where present instead of building custom invoice rendering.
- Tax: prefer Stripe Tax built into Checkout and Billing rather than a custom tax calculator. Stripe’s docs explicitly recommend native Checkout/Subscriptions tax integrations when those products are used.
- Dunning: let Stripe Billing handle retries and dunning schedule; STOA should project the state for parent/admin views and export, not invent its own retry engine in v4.4.

## Build Order For Phases 145-147

### Phase 145: Production Checkout And Webhook Verification

Build in this order:

1. Add readiness config and `billing_readiness_service`.
2. Introduce `stripe_gateway` with a dual execution path:
   - local/mock for existing tests and development
   - real Stripe API path for approved test/live credentials
3. Add provider lookup rows and migrate webhook resolution away from scan-first behavior.
4. Expand webhook projection and evidence fields.
5. Extend admin billing visibility with readiness plus webhook verification evidence.

Why first: every later refund, invoice, tax, and dunning feature depends on stable provider ids, verified webhook processing, and safe rollout gating.

### Phase 146: Refunds, Invoices, Tax, And Dunning Readiness

Build in this order:

1. Add `billing_ops_service` and extend billing summary projection fields.
2. Surface invoice/receipt metadata and hosted links to parents/admins.
3. Add tax/accounting export shape from local projection plus provider invoice fields.
4. Add refund eligibility and operator handoff, then optional provider refund action.
5. Add dunning projection from invoice/subscription events, including next retry metadata.

Why second: this phase consumes the stable billing summary and webhook evidence produced in Phase 145.

### Phase 147: Release Gate And Support Audit

Build in this order:

1. Add release-evidence queries on top of readiness and billing event surfaces.
2. Run read-only config/webhook verification first.
3. Run explicit live-charge deferral verification by default.
4. Only if separately approved, run named safe-fixture live smoke through the existing evidence discipline.

Why last: Phase 147 should verify and package the architecture already built, not invent new payment state.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-1k users | Current monolith is fine. The priority is correctness, no-real-charge gating, and replacing scan-based webhook lookup. |
| 1k-100k users | Keep the monolith, but make webhook writes idempotent and cheap, add lookup rows, and consider async event processing only if webhook latency becomes noisy. |
| 100k+ users | Move webhook ingestion to queue-backed processing and consider separating billing projections from synchronous API reads. Do not do this in v4.4. |

### Scaling Priorities

1. **First bottleneck:** webhook lookup by scan. Fix with lookup rows now.
2. **Second bottleneck:** `subscription_service.py` becoming an untestable god object. Fix with the service split above, not with a microservice.

## Anti-Patterns

### Anti-Pattern 1: Binary Test/Live Logic

**What people do:** Treat `stripe_live_charges_enabled` as both readiness and approval.

**Why it’s wrong:** It cannot represent “live credentials verified but customer charging still blocked,” which is the core safety requirement of v4.4.

**Do this instead:** Introduce an explicit rollout/readiness model and keep live execution behind a separate flag.

### Anti-Pattern 2: Webhook Scan Resolution

**What people do:** Scan all `subscription_billing` rows to resolve provider ids.

**Why it’s wrong:** It is slow, brittle, and unnecessary on a hot public webhook path.

**Do this instead:** Write provider lookup rows whenever checkout or webhook processing learns a new provider id.

### Anti-Pattern 3: Custom Billing Automation Before Provider Primitives

**What people do:** Build custom invoice rendering, retry scheduling, or tax logic immediately.

**Why it’s wrong:** Stripe already provides hosted invoices, tax calculation, and retry scheduling. Replacing those now creates more surface area with less safety.

**Do this instead:** Use provider-hosted primitives first and only project the minimum metadata STOA needs.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| Stripe Checkout | `stripe_gateway.create_checkout_session()` | Prefer Dashboard-managed dynamic payment methods so TWINT rollout is provider configuration, not backend branching. |
| Stripe Webhooks | `billing.py` raw body -> `billing_webhook_service` | Signature verification must happen before JSON mutation. |
| Stripe Billing / Invoices | Webhook projection plus targeted provider reads | Surface hosted invoice URLs and invoice status instead of copying invoice documents into STOA. |
| Stripe Refunds | Admin-triggered provider action or documented handoff | Track pending/failure outcomes explicitly. |
| Stripe Tax | Native Checkout/Subscriptions tax integration | Do not add a custom tax calculator for v4.4. |
| Stripe Revenue Recovery / Smart Retries | Provider-managed dunning engine | STOA should project retry metadata and status only. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `parents.py` ↔ `subscription_service.py` | Direct service call | Keep parent routes simple and read-focused beyond checkout creation. |
| `admin.py` ↔ `billing_readiness_service.py` | Direct service call | Readiness is environment state, not parent state. |
| `admin.py` ↔ `billing_ops_service.py` | Direct service call | Refund/invoice/tax/dunning views should not live in router code. |
| `billing.py` ↔ `billing_webhook_service.py` | Direct service call with raw body | No business logic should remain in the router. |
| `billing_webhook_service.py` ↔ DynamoDB | Transactional writes | Preserve dedupe markers, summary projection, and append-only event evidence. |
| `subscription_service.py` ↔ `stripe_gateway.py` | Adapter boundary | All real provider I/O should cross one seam. |

## Sources

- Local code: `src/stoa/services/subscription_service.py`
- Local code: `src/stoa/routers/billing.py`
- Local code: `src/stoa/routers/parents.py`
- Local code: `src/stoa/routers/admin.py`
- Local tests: `tests/test_subscription_operations.py`
- Project context: `.planning/PROJECT.md`
- Milestone requirements: `.planning/REQUIREMENTS.md`
- Phase context: `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-CONTEXT.md`
- Phase contract: `.planning/phases/144-live-payment-rollout-contract-and-credential-readiness/144-LIVE-PAYMENT-ROLLOUT-CONTRACT.md`
- Stripe Checkout Sessions API: https://docs.stripe.com/api/checkout/sessions/create
- Stripe webhook signature guidance: https://docs.stripe.com/webhooks/signature
- Stripe dynamic payment methods: https://docs.stripe.com/payments/payment-methods/dynamic-payment-methods
- Stripe TWINT overview: https://docs.stripe.com/payments/twint
- Stripe subscriptions with TWINT overview: https://docs.stripe.com/billing/subscriptions/twint
- Stripe Hosted Invoice Page: https://docs.stripe.com/invoicing/hosted-invoice-page
- Stripe refunds: https://docs.stripe.com/refunds
- Stripe Tax with Checkout: https://docs.stripe.com/tax/checkout
- Stripe Tax with subscriptions: https://docs.stripe.com/tax/subscriptions
- Stripe revenue recovery / Smart Retries: https://docs.stripe.com/billing/revenue-recovery/smart-retries

---
*Architecture research for: v4.4 live payment provider rollout*
*Researched: 2026-06-11*
