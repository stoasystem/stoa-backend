# Phase 248 Plan

## Goal

Ensure major successful usage flows emit governed, privacy-safe, idempotent usage events or explicit skip decisions.

## Tasks

1. Add governed practice teacher-help ledger coverage.
2. Add tests that prove practice teacher-help metadata excludes raw message/context content.
3. Add skip test for practice teacher-help when the challenge is missing.
4. Add a mismatched question idempotency guard before quota counter increment.
5. Add test evidence for partial question persistence failure after counter and ledger writes.
6. Run focused backend tests and Ruff.

## Success Criteria

- Missing high-priority ledger coverage discovered in Phase 247 is implemented or explicitly deferred with evidence.
- Duplicate request/action identifiers do not double-charge quota.
- Mismatched duplicate intent is rejected before counter increment.
- Focused tests cover duplicate IDs, repeated submissions, failed operations, partial failures, and metadata privacy.
