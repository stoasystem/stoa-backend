# Phase 205: Entitlement Visibility And Focused Tests - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning
**Mode:** Autonomous smart discuss

<domain>
## Phase Boundary

Expose enough effective entitlement visibility for parent/customer and admin support surfaces without building the full operations console.

</domain>

<decisions>
## Implementation Decisions

### Parent Visibility
- Add `effectiveEntitlements` to `/parents/me/subscription` and `/parents/me/subscription/billing`.
- Keep all existing billing fields backward compatible.

### Admin Visibility
- Add `effectiveEntitlements` to admin subscription billing detail/list response model.
- Include entitlement source and support explanation in each child entitlement summary.

### Test Coverage
- Extend existing subscription operation tests so provider pending and manual override states are visible.

### the agent's Discretion
- Return a list because a parent can have multiple active child bindings.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Parent and admin billing response models already allow dict/list style operational metadata.

### Established Patterns
- API response models are route-local and camelCase.

### Integration Points
- `parents.py`, `admin.py`, and `subscription_service.py`.

</code_context>

<specifics>
## Specific Ideas

Visibility should help support answer "why does this student have this access?" without exposing provider internals.

</specifics>

<deferred>
## Deferred Ideas

Full parent/admin operations visibility remains v5.9 scope.

</deferred>
