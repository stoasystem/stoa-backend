# Account Operations Visibility Contract

## Response Slices

- `parent`: user ID, email, name, role, verification state.
- `billing`: status, mode, provider, tier, period, dunning/refund/accounting readiness, bounded events for admin detail only.
- `children`: child profile, binding, entitlement, usage, verification.
- `usage`: per-child privacy-safe usage summaries.
- `supportState`: aggregate state, blockers, and warnings.

## Support State

| State | Meaning |
|-------|---------|
| `ready` | No blockers or warnings. |
| `attention` | No blockers, but support-visible warnings exist. |
| `blocked` | Parent verification or billing state blocks normal operations. |

## Privacy Boundary

Operations responses must not contain raw question/answer content, private S3 keys, auth tokens, verification codes, full provider payloads, or unredacted invoice internals.

## Data Sources

- User profile and parent/student bindings: `user_repo`.
- Billing: `subscription_service`.
- Entitlement: `entitlement_service`.
- Usage: `usage_ledger_service`.
- Verification: `account_verification_service`.
