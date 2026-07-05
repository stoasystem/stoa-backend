# Phase 254 Plan

## Goal

Verify backend product smoke and support evidence are sufficient for release triage.

## Tasks

1. Run focused backend tests for core smoke, usage ledger, subscription/account operations, auth lifecycle, curriculum, questions, and conversations.
2. Run Ruff over the same backend modules and focused tests.
3. Inspect core smoke output for expected blocker classification and privacy flags.
4. Inspect account operations, usage reconciliation, billing provider readiness, and auth support tests for support-safe metadata.
5. Add contract fields only if release triage evidence is incomplete.
6. Record final evidence and move the milestone to cross-surface journey verification.

## Success Criteria

- Focused backend tests pass.
- Static checks pass for release-support modules.
- Smoke output distinguishes expected provider/auth blocks from regressions.
- Evidence surfaces avoid raw content, provider payloads/secrets, auth tokens, verification codes, and private artifact data.
- No backend contract change is needed unless a concrete evidence gap is found.
