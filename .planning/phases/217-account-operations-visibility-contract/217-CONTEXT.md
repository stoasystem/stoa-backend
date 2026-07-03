# Phase 217: Account Operations Visibility Contract - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 217 defines a shared account operations visibility contract that composes parent profile, billing, child bindings, entitlement, usage, verification, and support state.

</domain>

<decisions>
## Implementation Decisions

### Data Sources
- Reuse v5.6 `entitlement_service`, v5.7 `usage_ledger_service`, v5.8 `account_verification_service`, existing `subscription_service`, and `user_repo`.
- Add no new tables, indexes, provider storage, or analytics warehouse.

### Support State
- Use bounded `ready`, `attention`, and `blocked` states.
- Blockers cover parent verification and inactive billing.
- Warnings cover child verification, non-active bindings, missing children, and unreconciled usage.

### Privacy
- Do not expose raw learning content, private artifact keys, auth tokens, verification codes, or provider payload internals.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- Parent routes already resolve parent identity and ownership.
- Admin routes already expose billing, usage, and verification support slices.
- Services already provide entitlement resolution, usage summaries, and verification public state.

### Integration Points
- `src/stoa/services/account_operations_service.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/admin.py`

</code_context>

<specifics>
## Specific Ideas

Keep route responses dict-heavy for nested slices so they can evolve without duplicating many existing schemas.

</specifics>

<deferred>
## Deferred Ideas

Frontend/native UI, production smoke, CRM workflows, and cross-account search remain future work.

</deferred>
