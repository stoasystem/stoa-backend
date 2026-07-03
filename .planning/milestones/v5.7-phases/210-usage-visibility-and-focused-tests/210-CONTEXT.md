# Phase 210: Usage Visibility And Focused Tests - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Expose enough usage and reconciliation visibility for parent/customer and admin support workflows without building the full v5.9 operations console.
</domain>

<decisions>
## Implementation Decisions

### Parent Visibility
- Add a child-scoped parent endpoint that returns consumed, limit, remaining, effective plan/source, billing state, and reconciliation status.
- Reuse existing parent-child authorization checks.

### Admin Visibility
- Add support endpoints for student usage summary, redacted ledger events, and reconciliation preview/repair.
- Return redacted ledger event metadata only; never include raw content or private keys.

### the agent's Discretion
Keep response models small and backward compatible by adding new endpoints rather than changing existing subscription payloads further.
</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Parent routes already resolve parent profile and linked child ownership.
- Admin routes already expose support/billing visibility under `/admin`.

### Established Patterns
- Pydantic response models are route-local.
- Parent/admin API responses use camelCase.

### Integration Points
- `GET /parents/me/children/{child_id}/usage`
- `GET /admin/usage/students/{student_id}`
- `GET /admin/usage/students/{student_id}/events`
- `GET /admin/usage/reconciliation`
</code_context>

<specifics>
## Specific Ideas

Visibility responses explicitly mark `partial`, `stale`, and `unreconciled`.
</specifics>

<deferred>
## Deferred Ideas

Full search/filter dashboards and operator workflows remain v5.9 scope.
</deferred>
