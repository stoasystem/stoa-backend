# v5.15 Research: Pitfalls

## Pitfalls

- Treating all identical payloads as duplicate usage. Same payload can represent a new user intent; use request/action-specific idempotency keys.
- Counting previews, failed attempts, dry-runs, admin retries, or duplicate submissions as real student quota usage.
- Building new usage analytics that bypass existing ledger/counter/account-operations contracts.
- Returning private learning content or provider payloads inside support explanations.
- Calling a generic health endpoint "healthy" while core product flows are broken. Smoke checks should name exact route/flow failures.
- Treating live BI/APM/provider activation as required for local product stability.

## Prevention

- Add a usage-flow matrix and keep it as release evidence.
- Keep action taxonomy explicit: consume, skip, reconcile, repair, or future-only.
- Test duplicate idempotency keys, mismatched duplicate payloads, partial failures, and counter drift.
- Enforce low-cardinality support codes and metadata-only evidence.
- Separate liveness/readiness style health from product smoke checks.
