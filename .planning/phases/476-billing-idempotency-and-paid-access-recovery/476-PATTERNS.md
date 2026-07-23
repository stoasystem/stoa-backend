# Phase 476: Billing Idempotency And Paid Access Recovery - Pattern Map

**Mapped:** 2026-07-24
**Files analyzed:** 24 likely new/modified files across backend and canonical Web
**Analogs found:** 22 / 24

This map covers backend contracts and explicit `/Users/zhdeng/stoa-frontend` integration work. UI detail belongs in the frontend tasks; no separate UI-SPEC is required. Backend plans must nevertheless specify the complete typed API contract, stable error codes, opaque-reference ownership rules, and handoff states consumed by Web.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `src/stoa/models/billing.py` | model | transform | `src/stoa/models/user.py` | role-match |
| `src/stoa/models/allowance.py` | model | transform | `src/stoa/services/usage_ledger_service.py` data contracts | partial |
| `src/stoa/db/repositories/checkout_command_repo.py` | repository | CRUD / event-driven | `src/stoa/db/repositories/notification_repo.py` delivery intent | exact |
| `src/stoa/db/repositories/billing_fact_repo.py` | repository | event-driven | billing event persistence in `src/stoa/services/subscription_service.py` | role-match |
| `src/stoa/db/repositories/allowance_repo.py` | repository | CRUD / transactional | `src/stoa/db/repositories/usage_ledger_repo.py` | exact |
| `src/stoa/services/subscription_service.py` | service | request-response / provider I/O | existing file; delivery intent in `notification_service.py` | exact |
| `src/stoa/services/billing_reconciliation_service.py` | service | event-driven / batch | `src/stoa/services/usage_ledger_service.py` reconciliation | role-match |
| `src/stoa/services/entitlement_service.py` | service | transform / CRUD | existing file | exact |
| `src/stoa/services/allowance_service.py` | service | transactional / transform | `src/stoa/services/usage_ledger_service.py` | exact |
| `src/stoa/services/ai_service.py` | service | provider request-response | existing file | exact |
| `src/stoa/services/payment_reminder_service.py` | service | batch / event-driven | `src/stoa/services/notification_service.py` | exact |
| `src/stoa/services/notification_service.py` | service | event-driven / provider I/O | existing delivery-intent flow | exact |
| `src/stoa/routers/parents.py` | route/controller | request-response | existing subscription endpoints | exact |
| `src/stoa/routers/billing.py` | route/controller | event-driven | existing Stripe webhook route | exact |
| `src/stoa/routers/admin.py` | route/controller | request-response | existing admin operation surfaces | exact |
| `src/stoa/models/user.py` and profile/config initialization | model/config | transform | existing enum/defaults | exact |
| `tests/test_billing_commands.py` | test | request-response / failure injection | `tests/test_subscription_operations.py` | exact |
| `tests/test_allowances.py` | test | transactional / time-driven | `tests/test_usage_ledger.py` | exact |
| `tests/test_payment_reminders.py` | test | event-driven | `tests/test_notifications.py` | exact |
| migration preview/apply module (planner chooses canonical migration path) | migration | batch | no close dedicated billing migration analog found | none |
| Web `src/types/billing.ts` | model | transform | existing file | exact |
| Web `src/services/billing/billingApi.ts` | service | request-response | existing file | exact |
| Web `src/hooks/billing/*` | hook | request-response / polling | `useSubscriptionQuery.ts`, `useCreateCheckoutSessionMutation.ts` | exact |
| Web pricing/billing/result/admin components and E2E | component/test | request-response / event-driven | existing Pricing, Billing, Result and `billing-pricing.spec.ts` | exact |

## Pattern Assignments

### Billing models and plan identity

**Targets:** `src/stoa/models/billing.py`, `src/stoa/models/user.py`, Web `src/types/billing.ts`, Web pricing data.

**Analog:** `src/stoa/models/user.py:7-24`

```python
class UserRole(str, Enum):
    STUDENT = "student"
    PARENT = "parent"
    TEACHER = "teacher"
    ADMIN = "admin"

class SubscriptionTier(str, Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
```

Copy the `str, Enum` convention, but replace the legacy tier values with exactly `free_trial`, `student`, `teacher_supported`, and `family`. Do not add compatibility translations in active contracts. Billing DTOs should use explicit Pydantic models like the response models in `parents.py`, camelCase response fields, safe optional provider summaries, and separate command, invoice, subscription, entitlement, and scheduled-transition dimensions.

Web types follow compact literal-backed object types (`/Users/zhdeng/stoa-frontend/src/types/billing.ts:5-31`). Rename request-count fields to weekly input/output token and teacher-case projections; include UTC window boundaries, percentage/remaining values, beneficiary summaries, command states, safe actions, and masked-card fields.

### Durable checkout command repository

**Target:** `src/stoa/db/repositories/checkout_command_repo.py`

**Primary analog:** `src/stoa/db/repositories/notification_repo.py:575-580, 910-969`

```python
def delivery_intent_pk(owner_id: str) -> str:
    return f"NOTIFICATION_DELIVERY#{owner_id}"

def delivery_intent_sk(operation_id: str) -> str:
    return f"INTENT#{operation_id}"

existing = _optional_item(
    _get_item(target, Key=key, ConsistentRead=True).get("Item")
)
if existing:
    if not _delivery_identity_matches(...) or existing.get("channel") != channel:
        raise account_deletion_repo.AccountDeletionConflict(
            "delivery intent identity changed"
        )
    return dict(existing)
...
_put_item(
    target,
    Item=item,
    ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)",
)
```

Use the same immutable identity/replay contract for command key + canonical intent fingerprint. Create the command, `CHECKOUT_OPEN#<parent>` guard, and opaque public-reference lookup in one transaction. A duplicate identity returns the existing command; changed intent raises a typed conflict. Preserve a provider-effect state/version and lease before Stripe mutation.

**Lease orchestration analog:** `src/stoa/services/notification_service.py:447-528`

```python
intent = notification_repo.register_delivery_intent(...)
prior_status = str(intent.get("outcome_status") or intent.get("status") or "")
if prior_status in {"accepted", "provider_acceptance_unknown", ...}:
    return {"status": prior_status}
recovered = notification_repo.recover_delivery_intent(...)
claimed = notification_repo.claim_delivery_intent(
    ..., lease_expires_at=now_epoch + lease_seconds, ...
)
if not claimed:
    return {"status": "retryable_claim_conflict"}
```

Copy register → recover → conditional claim → pre-effect boundary → provider call → durable outcome. Never release the parent open guard because an HTTP response was lost.

### Subscription/provider orchestration

**Target:** `src/stoa/services/subscription_service.py`

Keep this as the public provider seam but move persistence-heavy state machines into the focused repositories/services above.

**Imports/conventions:** `subscription_service.py:3-26` uses stdlib hashing/HMAC/time, typed protocols for Dynamo dependencies, `Settings`, repository imports, and FastAPI `HTTPException`.

**Existing guard identity:** `subscription_service.py:1011-1020`

```python
def _request_pk(request_id: str) -> str:
    return f"SUBSCRIPTION_REQUEST#{request_id}"

def _open_guard_key(parent_id: str) -> dict[str, str]:
    return {"PK": f"SUBSCRIPTION_OPEN#{parent_id}", "SK": "GUARD"}
```

Evolve this idea to checkout-command keys; do not reuse the manual subscription-request lifecycle as payment truth.

Provider create must pass one stable non-PII Stripe idempotency key and identical parameters for ambiguous retries. Server settings construct the exact configured origin plus fixed success/cancel paths and opaque STOA reference. Browser callback URLs and `window.location.origin` are removed from the request.

### Webhook boundary and billing facts

**Targets:** `src/stoa/routers/billing.py`, `billing_fact_repo.py`, `billing_reconciliation_service.py`.

**Router analog:** `src/stoa/routers/billing.py:26-37`

```python
@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
@explicit_route_classification("public", "provider-signature authenticated webhook")
async def handle_stripe_webhook(request: Request, stripe_signature: str | None = Header(...)):
    payload = await request.body()
    return subscription_service.handle_stripe_webhook(
        payload=payload, signature_header=stripe_signature, settings=settings
    )
```

**Signature analog:** `subscription_service.py:2022-2048`

```python
event = stripe.Webhook.construct_event(
    payload,
    signature_header,
    settings.stripe_webhook_secret,
)
```

Retain raw-body verification through the official SDK. Do not copy the custom signature fallback into the production path.

Facts must dedupe provider event ID and semantic `(event.type, data.object.id)` identity, then reconcile current Stripe objects. Do **not** copy the global timestamp sort at `subscription_service.py:1752-1769`; Stripe delivery order is not authoritative. Activation requires matching paid first invoice **and** active subscription, matching immutable command/customer/price/test-mode facts, then one conditional transaction publishing command outcome, billing projection, explicit grants, plan/allowance version, and evidence.

### Entitlements and beneficiaries

**Target:** `src/stoa/services/entitlement_service.py`

**Analog:** `entitlement_service.py:23-74`

```python
binding = _active_parent_binding(parent_id, student_id) if parent_id else None
billing = _get_billing_item(parent_id) if parent_id else None
decision = _billing_decision(
    billing=billing,
    parent_profile=parent_profile,
    student_tier=student_tier,
    has_active_binding=bool(binding),
)
return {
    "studentId": student_id,
    "effectivePlan": effective_plan,
    "source": decision["source"],
    "limits": {...},
    "billingState": decision["billing_state"],
}
```

Keep centralized effective-entitlement projection and active-binding revalidation. Replace all-child inference with explicit grant lookup: Student/Teacher-supported exactly one selected active student; Family up to three. Remove manual-success activation. Model upgrades, end-period downgrade/cancel, three-day grace, and free-trial fallback monotonically. Storage remains 5 GB free / 15 GB paid and downgrade blocks only new uploads.

### Allowance repository/service and AI evidence

**Targets:** `allowance_repo.py`, `allowance_service.py`, `allowance.py`, `ai_service.py`.

**Stable ledger identity analog:** `usage_ledger_service.py:294-308, 447-537`

```python
def build_usage_idempotency_key(*, action: str, resource_id: str, ...):
    get_usage_action_definition(action)
    if not resource_id:
        raise ValueError("resource_id is required for usage idempotency")

event = {
    "SK": f"EVENT#{action}#{quota_period}#{idempotency_key}",
    "entity_type": "usage_ledger_event",
    "idempotency_key": idempotency_key,
    ...
}
created = usage_ledger_repo.put_usage_event(event)
return {**event, "idempotency_status": "created" if created else "duplicate"}
```

**Conditional persistence analog:** `usage_ledger_repo.py:93-180` uses deterministic keys, `attribute_not_exists(PK) AND attribute_not_exists(SK)`, consistent reads, and owner-fenced transactions.

Extend the pattern into reservation → immutable provider observation → exact finalization or user restoration. Keep provider-cost evidence even when user allowance is restored. Use Europe/Zurich local Monday calendar calculations and persist local identity plus UTC start/end; test both DST transitions. Teacher support debits once on successfully admitted durable case ID, never per message/reply.

**Provider seam:** `ai_service.py:290` and `:354`

```python
response = client.invoke_model(modelId=settings.bedrock_model_id, body=body)
```

Change this boundary to return validated content plus immutable `usage.input_tokens` / `usage.output_tokens`, model/profile, stop reason, correlation/effect ID, and observation time. Do not put prompts or answer text in redacted usage evidence. Inventory every `invoke_model` caller and classify it as user allowance or provider-cost-only.

### Reconciliation and support projections

**Targets:** `billing_reconciliation_service.py`, parent/admin routes.

**Analog:** `usage_ledger_service.py:620-677`

```python
events = usage_ledger_repo.list_usage_events(...)
ledger_count = sum(...)
counter = usage_ledger_repo.get_daily_usage_counter(...)
status = _reconciliation_status(counter_count, ledger_count, ...)
support = _reconciliation_support_state(...)
return {
    "status": status,
    "supportAction": support["action"],
    "explanation": support["explanation"],
    "partial": not _reconciliation_is_ok(status),
}
```

Copy the read → compare authoritative evidence → optionally conditional repair → redacted support explanation shape. Parent status/recheck routes authorize ownership of opaque reference. Recheck only reconciles the original command. Admin exposes redacted provider identifiers, timestamps, lifecycle dimensions, failure reason, and idempotent recheck; it must not offer “mark paid.”

Use Pydantic request/response models and authenticated dependencies as in `parents.py:220-260, 727-742`. Return stable machine-actionable codes such as identity mismatch, open-command conflict, provider outcome unknown, invalid beneficiary, and recheck lease conflict rather than UI prose as `detail`.

### Payment-method reminders

**Targets:** `payment_reminder_service.py`, `notification_service.py`, `notification_repo.py`.

**Analog:** notification delivery identities and owner-fenced transactions at `notification_repo.py:583-631, 910-969`; delivery lease flow at `notification_service.py:447-528`.

Persist only payment-method digest, brand, last4, expiry month/year, subscription source, and observation version. Reminder identity is `(payment_method_digest, exp_year, exp_month)` and fan-out has independent per-recipient/per-channel operation IDs. Compute expiry as Zurich month-end and trigger seven local calendar days earlier. Verified-and-deliverable email is required for email; in-app remains independent. One failed recipient/channel cannot alter billing or suppress other recipients.

### Parent APIs and Web contract

**Backend targets:** `parents.py`, `admin.py`.

Required contract:

- `POST /parents/me/subscription/checkout`: required logical identity (prefer `Idempotency-Key` header), body `{ plan, beneficiaryIds }`; never callback URLs. Returns opaque `checkoutRef`, lifecycle state, safe actions, and existing `checkoutUrl` only when owner-visible and payable.
- `GET .../checkout/{checkoutRef}`: exactly `confirming | active | not_completed | support_needed`, effective plan, beneficiaries, redacted explanation/actions.
- `POST .../checkout/{checkoutRef}/recheck`: reconcile same command only.
- Explicit confirmed supersession endpoint/action for plan changes.
- Parent billing/allowance/reminder projection and equivalent redacted admin read/recheck projection.

### Canonical Web integration

**Targets:** `/Users/zhdeng/stoa-frontend/src/services/billing/billingApi.ts`, `src/types/billing.ts`, billing hooks/pages/components, pricing identifiers/locales, admin projection, and E2E.

**API adapter pattern:** `billingApi.ts:13-25` uses the shared authenticated `httpClient` and returns mapped typed data. Preserve that. Replace `billingApi.ts:28-41`, which currently submits `window.location.origin` callback URLs, with plan + beneficiary IDs and one retained logical identity.

**Query pattern:** `useSubscriptionQuery.ts:1-9`

```typescript
return useQuery({
  queryKey: ['billing', 'subscription'],
  queryFn: getSubscription,
  retry: false,
})
```

Create command-status and allowance query keys in the same billing namespace. Poll status while `confirming`; stop on backend-declared terminal state. Recheck is a mutation against the same reference. Do not mirror authoritative billing state into Zustand. Session storage may retain only the browser logical checkout key/reference across refresh until terminal.

**Mutation pattern:** `useCreateCheckoutSessionMutation.ts:8-26` supplies `useMutation` and redirect-on-success, but remove preview/demo branching and random/new identity on retries. Disable create while an open server command exists.

**Result page replacement:** `CheckoutResultPage.tsx:11-68` is a useful layout/component analog only. Replace URL-derived `success/cancel` and `plan` inference with opaque-reference query + authoritative four states. Active links to Billing and parent home; confirming polls; delayed state offers recheck and support.

**Plan convergence:** `pricingPlans.ts:3-41` is the product/price source. Rename `tutor_supported` to `teacher_supported`; keep CHF 0/29/89/149. Remove the lossy translations at `billingApi.ts:106-115`.

**E2E analog:** `tests/e2e/billing-pricing.spec.ts:4-47` shows route, auth, and failure-state assertions. Replace virtual checkout proof with a separate real Stripe test-mode Playwright project: browser checkout, signed webhook, exactly-once entitlement/allowance convergence, parent/admin projections, duplicate/delayed event checks, and explicit no-live-charge evidence. Focused mocks remain appropriate for UI state branches.

## Shared Patterns

### Authentication and ownership

Parent routes use the authenticated parent dependency and revalidate every beneficiary against active bindings. Public webhook routes are authenticated only by raw-body provider signature. Admin mutations use existing admin authorization and are limited to recheck/read.

### Conditional transactions

Use deterministic PK/SK identities, consistent reads on replay, conditional nonexistence for first creation, expected state/version on transition, and bounded DynamoDB transactions. `notification_repo.py:599-629` is the concrete transaction-builder pattern.

### Error handling

At integration boundaries, convert malformed/unavailable dependencies to stable typed outcomes. Preserve retry ambiguity as `provider_acceptance_unknown`/support-needed; never interpret an exception as proof that Stripe did not create or accept an effect. The notification flow at `notification_service.py:485-528` is the closest precedent.

### Redaction

Use the existing safe identifier projection at `subscription_service.py:1833-1839`:

```python
if len(cleaned) <= 8:
    return "configured"
return f"...{cleaned[-6:]}"
```

No provider secrets, full card data, prompts, answers, or payment-capable values enter parent/admin evidence.

### Terminology and migration

All active code, config, persisted projections, API types, Web copy, and evidence use the same four plan IDs and `teacher`. Legacy rows require a read-only preview and idempotent migration based on authoritative Stripe Price/subscription plus explicit beneficiary choice; ambiguous `standard` rows become `migration_review_required` and must not broaden access.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| billing plan runtime migration module | migration | batch | No close dedicated billing migration analog was found; use research’s preview/apply/review contract and repository transaction conventions. |
| configured-model Bedrock CountTokens probe/evidence harness | test/utility | provider request-response | Existing AI code invokes Bedrock but has no authoritative token preflight pattern; implement from verified AWS SDK semantics and retain probe evidence. |

## Planner Handoff Notes

- Plan this as a cross-repo vertical invariant, not independent backend and UI “success” features.
- Backend work owns precise contracts and secure fixed return URL construction. Frontend work owns friendly rendering and polling behavior; no UI-SPEC is required.
- A browser redirect, `checkout.session.completed`, invoice fact alone, subscription fact alone, admin action, or query parameter is never paid-access proof.
- Keep Stripe sandbox acceptance distinct from mock-focused tests and Phase 474’s immutable evidence gate.
- No new packages are required.

## Metadata

**Analog search scope:** `src/stoa`, `tests`, and canonical `/Users/zhdeng/stoa-frontend/src`, `/tests/e2e`
**Strong analogs read:** subscription, entitlement, usage ledger, AI, notification repositories/services/routes; Web billing API/types/hooks/pages/pricing/E2E
**Pattern extraction date:** 2026-07-24
