# UI Spec: Phase 126 Parent Payment UX And Admin Billing Operations

## Design Direction

Operational SaaS billing surfaces: compact, clear, low-noise, and built for repeated scanning. Payment state should be legible without marketing-style layout or decorative treatment.

## Parent Surface

- Location: existing parent subscription operations card.
- Add provider billing summary at the top of the card.
- Show status, mode, managed tier, last provider event, and checkout link when available.
- Keep manual request textarea and submit flow visible.
- Add checkout button for paid tiers.
- Disable checkout when the selected tier is `free` or already current.

## Admin Surface

- Location: existing admin subscription requests page.
- Add provider billing visibility section below the request queue/detail area.
- Show provider records as selectable rows.
- Show selected record detail with provider subscription ID, checkout session ID, manual override source, last provider event, and recent billing events.
- Keep manual request approval/apply actions unchanged.

## States

- `none`: no provider billing attached.
- `checkout_pending`: checkout created but webhook has not activated subscription.
- `active`: provider-managed subscription active.
- `past_due` / `payment_failed`: payment needs attention.
- `manual_override`: admin-applied local tier is authoritative.
- `canceled`: provider subscription canceled.
- `provider_unknown`: provider event did not map cleanly.

## Verification

- Parent browser workflow can start checkout and still submit a manual request.
- Admin browser workflow can see provider billing visibility and still approve/apply manual requests.
