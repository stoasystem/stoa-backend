# Phase 224 UI Spec: Parent Account Operations UI

**Status:** Approved
**Date:** 2026-07-03

## Product Surface

- `/parent/account-operations` parent detail page.
- Parent dashboard account operations entry/summary.

## Layout Contract

- Use `DashboardLayout` and `PageContainer`.
- Page header: concise operational title and one-sentence description.
- Top band: support state (`ready`, `attention`, `blocked`) with blockers/warnings rendered as compact chips.
- Main content:
  - billing summary panel,
  - parent verification panel,
  - child operations list,
  - usage summary strip/table.
- Empty/no-child state must be a full-width operational notice, not a marketing card.

## State Contract

Render:

- Loading: stable skeleton-like rows or muted loading panel.
- API error: explicit account operations unavailable message; no demo data.
- Ready: positive operational state.
- Attention: warnings list.
- Blocked: blockers list with stronger visual tone.
- No child: no-linked-child notice.
- Child row: binding status, email verification, effective plan, consumed/remaining quota, reconciliation state.

## Copy Contract

- Use user-facing operational copy.
- Avoid backend/provider/internal terms.
- Translate known codes:
  - `parent_email_unverified`: Verify parent email.
  - `billing_inactive`: Billing needs attention.
  - `no_linked_children`: No linked child account.
  - `child_email_unverified`: Child email is not verified.
  - `usage_unreconciled`: Usage is still being reconciled.
  - `child_binding_*`: Child link needs review.

## Visual Contract

- Cards use existing 8px-ish radius and border/card tokens.
- Status colors:
  - ready: secondary/positive text where available,
  - attention: primary/amber-style soft tone,
  - blocked: destructive soft tone.
- No decorative gradients, orbs, nested cards, or hero imagery.
- Keep rows responsive: one column on mobile, grid rows on desktop.

## Accessibility Contract

- Status summary uses text, not color only.
- Error state uses `role="alert"`.
- Loading uses `aria-busy` where appropriate.
- Links/buttons have visible text labels.

## Test Contract

- Parent account operations page tests cover ready, attention, blocked, no-child, loading, and API-error states.
- Dashboard test covers the route entry/summary link.
