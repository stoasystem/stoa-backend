# Phase 219: Admin Parent Operations Detail - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 219 exposes support-grade parent account operations detail to admins.

</domain>

<decisions>
## Implementation Decisions

- Admin route is parent-ID scoped.
- Missing/non-parent records return bounded 404.
- Admin detail can include bounded billing events already exposed by `subscription_service`.
- Support state surfaces parent verification blockers and child/binding warnings.

</decisions>

<code_context>
## Existing Code Insights

Admin routes already use `require_role("admin")` and expose billing, usage, reconciliation, and verification support endpoints.

</code_context>

<specifics>
## Specific Ideas

Add `GET /admin/account-operations/parents/{parent_id}`.

</specifics>

<deferred>
## Deferred Ideas

Cross-account search and broad CRM workflow remain out of scope.

</deferred>
