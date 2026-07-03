# Phase 203: Entitlement Resolver Service And Parent Child Mapping - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Implement the backend resolver that converts student profile, active parent binding, parent profile, provider billing, and manual override signals into one effective entitlement result.

</domain>

<decisions>
## Implementation Decisions

### Resolver Location
- Add `src/stoa/services/entitlement_service.py`.
- Keep storage reads aligned with existing user repository and subscription billing key patterns.
- Do not change the DynamoDB schema.

### Mapping Behavior
- Resolve parent-paid access only when the student profile has an active parent binding and the formal binding row is active.
- Add reverse binding repository support for future callers, but keep question quota deterministic when no parent binding is present.
- Return free/local fallback rather than raising for incomplete account state.

### Test Coverage
- Cover active provider billing, pending checkout, and manual override precedence.
- Use focused fake-table tests rather than live AWS dependencies.

### the agent's Discretion
- Keep resolver output as dictionaries to match existing service response style.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `user_repo.get_user`, `get_parent_student_binding`, and `list_parent_student_bindings`.
- Subscription billing rows keyed as `SUBSCRIPTION_BILLING#{parent_id}` / `SUMMARY`.

### Established Patterns
- Services return plain dictionaries for broad frontend/API contracts.
- Tests use monkeypatched fake table methods.

### Integration Points
- Imported by subscription and question modules.

</code_context>

<specifics>
## Specific Ideas

Return support-oriented explanations such as active provider billing, pending checkout, missing binding, or manual override.

</specifics>

<deferred>
## Deferred Ideas

Ledger event emission waits for v5.7.

</deferred>
