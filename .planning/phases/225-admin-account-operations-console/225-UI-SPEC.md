---
phase: 225
status: active
---

# Phase 225 UI Spec: Admin Account Operations Console

## Route

- `/admin/account-operations`
- Query string: `?parentId=parent-1&day=2026-07-03`

## Page Structure

1. Header
   - Eyebrow: `Account operations`
   - Title: `Parent support console`
   - Description: support-grade account state for one parent.

2. Lookup form
   - Parent ID text input.
   - Optional day input.
   - Submit updates query string and triggers detail query.

3. Empty state
   - Shows when no parent ID is supplied.
   - Explains that admins should enter a parent ID or open from subscription billing.

4. Detail state
   - Support state band: ready/attention/blocked.
   - Fact cards: parent verification, billing, linked children, usage rows.
   - Billing evidence: provider/mode/tier/period/manual override/readiness/events.
   - Child rows: profile, binding status, verification, effective plan, usage.
   - Usage summary: matched/reconciling badge.

5. Error states
   - 404: parent not found.
   - Other errors: account operations unavailable.

## Interaction

- Submitting the lookup navigates in-place.
- Changing selected billing parent on `/admin/subscriptions` exposes an account operations link.
- No write actions are included in this phase.

## Accessibility

- Error states use `role="alert"`.
- Form controls have visible labels.
- Cards use semantic headings and concise labels.
