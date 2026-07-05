# v5.15 Research: Features

## Table Stakes

- Usage-flow coverage matrix that maps each real student/admin/support path to ledger event, counter, both, skip, or missing.
- Idempotent usage event contract with explicit duplicate handling and parameter mismatch behavior.
- Reconciliation between ledger rows, daily counters, entitlement limits, and parent/admin account operation summaries.
- Support-safe explanations for why quota was allowed, limited, blocked, skipped, or unreconciled.
- Core health/smoke checks for login, entitlement, curriculum read, question submit, teacher help, and admin support surfaces.

## Differentiators

- Release-gate smoke output that can be used by internal developers without external APM credentials.
- Drift evidence that names the action, quota period, student ID, expected count, observed count, and support action without exposing private learning content.
- Reusable skip taxonomy for previews, failed operations, admin retries, dry-runs, duplicate submissions, and provider-blocked flows.

## Anti-Features

- Broad BI warehouse deployment during this milestone.
- External APM/vendor rollout without explicit approval.
- Raw learning content, prompt bodies, Cognito token material, or provider payloads in support evidence.
- New billing or auth provider activation; v5.15 is about usage/quota stability over already-built flows.
