# Phase 202: Entitlement Contract And Access Policy - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Define the effective entitlement contract before implementation. The first enforced product area is student question quota; usage ledger, email/login verification, and broader operations visibility stay deferred to v5.7-v5.9.

</domain>

<decisions>
## Implementation Decisions

### Entitlement Inputs
- Use student profile, parent-student binding, parent profile tier, provider billing row, manual override fields, rollout controls, pending checkout, cancellation/expiry, and payment failure state.
- Treat an active parent-student binding as required before parent-paid access can govern a student.
- Preserve direct student profile tier as deterministic fallback for missing bindings and admin-set student overrides.

### Entitlement Output
- Return effective plan, source, daily question limits, billing state, period, blocking reason, support explanation, binding status, student tier, parent tier, and rollout summary.
- Keep output camelCase for API-facing surfaces.
- Do not expose provider secrets, invoice internals, or raw billing row structure.

### State Precedence
- Manual override wins while billing status is `manual_override`.
- Active provider billing grants the billing row tier.
- Pending checkout, payment failed/past due, canceled/expired, missing binding, and free tier do not grant paid parent access.
- Parent profile tier can explain paid access only when no active provider row exists.

### the agent's Discretion
- Implementation may use a focused backend service rather than changing storage schema.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/stoa/services/subscription_service.py` already owns billing rows, manual override records, rollout controls, and parent/customer billing response shaping.
- `src/stoa/db/repositories/user_repo.py` already exposes parent-student binding writes and parent-to-child lookup.
- `src/stoa/routers/questions.py` already centralizes question quota through `_check_daily_limit`.

### Established Patterns
- FastAPI route modules use route-local Pydantic models and camelCase response contracts.
- DynamoDB access uses single-table keys and small repository helpers.
- Focused tests monkeypatch service dependencies and fake table behavior.

### Integration Points
- Question submission quota.
- Parent `/parents/me/subscription` and `/parents/me/subscription/billing`.
- Admin `/admin/subscriptions/billing/{parent_id}`.

</code_context>

<specifics>
## Specific Ideas

Use an entitlement resolver service that can be reused by future usage ledger and operations visibility milestones.

</specifics>

<deferred>
## Deferred Ideas

- Durable usage ledger and reconciliation events.
- Email verification and login-code policy.
- Full parent/admin operations console.

</deferred>
