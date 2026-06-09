# Phase 102 UI Spec

## Parent Dashboard

- Show current subscription tier.
- Show Free, Standard, and Premium plan benefit cards with AI question limit, teacher support, and weekly report coverage.
- Disable current tier and all plan actions when an open request exists.
- Allow selecting upgrade, downgrade, or cancellation intent through plan selection.
- Allow an optional parent note.
- Show mutation success/error feedback and recent request status history.

## Admin Subscription Queue

- Add `/admin/subscriptions`.
- Add Admin navigation entry labelled `Subscriptions`.
- Show request metrics for open, approved/ready-to-apply, and closed requests in current filter view.
- Provide filters for status, tier, and parent id.
- Show request queue rows with parent id, requested tier, current tier, status, and created date.
- Show selected request detail, parent note, admin note, effective date, lifecycle, transition actions, and apply action.
- Keep `Apply approved tier` disabled until the selected request is approved.

## States

- Parent: loading, unavailable/error, no open request, pending request, submitted feedback, recent applied/rejected/cancelled requests.
- Admin: loading, unavailable/error, empty filter result, selected detail, transition feedback, apply feedback.
