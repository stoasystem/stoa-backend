---
phase: 225
name: Admin Account Operations Console
status: active
created: 2026-07-03
---

# Phase 225 Context: Admin Account Operations Console

## Goal

Expose the v5.9 backend admin support endpoint `GET /admin/account-operations/parents/{parent_id}` in the web admin experience.

## Backend Contract

- Route: `GET /admin/account-operations/parents/{parent_id}`
- Optional query: `day=YYYY-MM-DD`
- Auth: admin role only.
- 200 response fields:
  - `parentId`
  - `parent`
  - `billing`
  - `billing.events`
  - `children`
  - `usage`
  - `supportState`
- 404 response: missing parent.

## Frontend Scope

- Add typed admin account operations response, reusing the parent account operations field model and extending billing with `events`.
- Add admin API client, query key, and React Query hook.
- Add `/admin/account-operations` route with direct parent ID lookup.
- Link from `/admin/subscriptions` billing rows/details to the new support view where practical.
- Render support state, parent verification, billing summary/events, child binding/entitlement/usage, and usage reconciliation.
- No demo fallback for account operations data.

## UI Decisions

- Keep the surface operational and dense; admins need a support console, not a marketing page.
- First screen includes parent ID lookup and current support state.
- Missing parent and API failures show explicit states without leaking internals.
- Billing event rows are support evidence, not an editable workflow.
- Admin actions remain read-only in this phase; subscription mutation workflows stay in `/admin/subscriptions`.

## Validation Targets

- Ready state renders parent, billing, child, entitlement, usage, and matched usage.
- Attention/blocked state renders parent verification, child verification, child binding, and billing blockers/warnings.
- Missing parent 404 state renders a clear not-found message.
- API-error state renders a generic unavailable message.
- Subscription page includes an account operations handoff link for selected billing/parent rows.
