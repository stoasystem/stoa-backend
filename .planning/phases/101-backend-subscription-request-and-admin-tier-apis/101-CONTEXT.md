# Phase 101: Backend Subscription Request And Admin Tier APIs - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Mode:** Autonomous, user delegated grey-area decisions to the agent

<domain>
## Phase Boundary

Implement backend support for the v3.3 manual subscription operations MVP. Parent users can view their current plan and submit bounded upgrade, downgrade, or cancellation intents. Admin users can list/filter/open requests, transition them through the manual review lifecycle, and explicitly apply an approved request to update `subscription_tier`.

</domain>

<decisions>
## Implementation Decisions

### Data Model
- Reuse the existing DynamoDB single-table style for the MVP.
- Store subscription request summaries under `PK=SUBSCRIPTION_REQUEST#<request_id>`, `SK=SUMMARY`.
- Store lifecycle events under the same partition with `SK=EVENT#<timestamp>#<event_id>`.
- Use bounded scans for pilot-volume admin filtering instead of adding a new GSI/CDK scope in this phase.

### Lifecycle
- Parent request statuses are `requested`, `in_review`, `approved`, `applied`, `rejected`, and `cancelled`.
- Approval records admin intent only.
- The `subscription_tier` profile field is mutated only by the explicit admin apply action.
- Terminal requests cannot be reopened in Phase 101.

### Verification Scope
- Focus on functional backend behavior: parent current-plan/read/create/list, admin list/detail/update/apply, role gating, duplicate open request handling, invalid transitions, and tier mutation on apply.
- Keep payment processing, invoices, refunds, tax handling, Stripe/TWINT webhooks, CDK changes, and broad compliance evidence out of scope.

</decisions>

<code_context>
## Existing Code Insights

- `src/stoa/routers/parents.py` already resolves the authenticated parent profile and uses camelCase API response models.
- `src/stoa/routers/admin.py` already exposes admin-only operational endpoints through `require_role("admin")`.
- `src/stoa/models/user.py` defines `SubscriptionTier` as `free`, `standard`, and `premium`.
- Existing question quota behavior already reads `subscription_tier`; Phase 101 must preserve that field contract.
- Existing admin user update code already mutates `subscription_tier`; Phase 101 adds a request-driven operational path around that mutation.

</code_context>

<specifics>
## Specific Ideas

- Add a focused `subscription_service` to keep lifecycle rules and DynamoDB writes out of router handlers.
- Return API-safe request objects with camelCase fields for parent/admin clients.
- Record lifecycle history events without storing payment-provider data.
- Reject a second open parent request to keep manual operations unambiguous for MVP support.

</specifics>

<deferred>
## Deferred Ideas

- Stripe/TWINT payment provider integration.
- Payment-provider webhooks and automated provisioning.
- New DynamoDB indexes or CDK resources for larger operational volume.
- External billing/support-system writes.

</deferred>
