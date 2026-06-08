# Phase 102 Context

**Phase:** Parent Subscription Management UI And Admin Queue
**Milestone:** v3.3 Subscription Operations MVP
**Started:** 2026-06-08

## Inputs

- Phase 100 defined the manual subscription contract: Free, Standard, Premium; parent intents; admin lifecycle; entitlement effects; and no new infrastructure.
- Phase 101 shipped backend APIs for parent subscription views/requests and admin request list/detail/update/apply actions.
- Frontend implementation lives in sibling repo `/Users/zhdeng/stoa-frontend`.

## UI Placement

- Parent controls are added to the parent dashboard at `/parent`.
- Admin operations get a dedicated queue route at `/admin/subscriptions` and an Admin navigation item.

## Constraints

- Payment processing remains outside v3.3. UI labels keep Stripe/TWINT deferred and do not imply automated charging.
- The parent create request payload must map frontend camelCase state to backend snake_case request fields.
- Browser auth in the shared in-app browser could verify protected-route redirects but could not type or seed local storage because of browser-environment restrictions, so workflow rendering/action verification uses the repo Playwright E2E harness.
