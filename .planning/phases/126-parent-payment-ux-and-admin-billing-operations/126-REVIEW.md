# Code Review: Phase 126 Parent Payment UX And Admin Billing Operations

**status:** clean
**reviewed:** 2026-06-09

## Scope

- Frontend subscription operation types, API calls, parent hooks, admin hooks.
- Parent subscription operations card.
- Admin subscription requests page.
- Targeted Playwright subscription operations tests.

## Findings

No blocking findings.

## Review Notes

- Existing manual subscription request workflows remain visible and tested.
- Checkout action is gated to paid non-current tiers.
- Admin billing visibility is read-only and does not add new mutation risk.
- Provider/manual distinction is explicit in parent and admin surfaces.
