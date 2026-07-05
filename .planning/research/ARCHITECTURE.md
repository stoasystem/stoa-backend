# v5.15 Research: Architecture

## Existing Architecture To Reuse

- `usage_ledger_service` defines governed actions and writes privacy-safe ledger events.
- Existing student/question/practice/chat/adaptive/curriculum services already own the business events that may consume quota.
- Parent/admin account operations already aggregate billing, entitlement, verification, child binding, and usage state.
- Frontend parent/admin account operations pages already render bounded operational summaries.

## Recommended Integration Points

- Start with an audit document before changing code.
- Extend existing ledger action definitions and summary builders rather than adding parallel analytics tables.
- Add reconciliation helpers near `usage_ledger_service` so the same logic can feed tests, support summaries, and smoke scripts.
- Add health/smoke commands under `scripts/` or a bounded backend service module rather than introducing new infrastructure.
- Use existing tests as the primary regression gate, then add focused smoke-script tests.

## Data Flow

1. Product flow succeeds.
2. Existing service records a governed usage event with an idempotency key and support-safe metadata.
3. Quota/counter state is updated or intentionally skipped according to the action contract.
4. Reconciliation compares ledger, counters, entitlement limits, and account operations summaries.
5. Parent/admin surfaces receive explanation fields and support actions without private content.
6. Release gate runs smoke checks and records pass/block/fail evidence.

## Build Order

1. Reality audit.
2. Ledger/idempotency closure.
3. Reconciliation and explanations.
4. Health/smoke checks.
5. Release gate evidence.
