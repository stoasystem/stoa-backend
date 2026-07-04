# Phase 246 Plan: v5.14 Verification Login Reliability Gate

## Goal

Close v5.14 with evidence that verification/login reliability is locally complete and externally blocked items are explicit.

## Steps

1. Run focused backend auth/account-operations tests.
2. Run backend Ruff on auth, admin, verification, account operations, and related tests.
3. Confirm frontend build evidence from Phase 245.
4. Run focused frontend e2e for auth and account operations when execution permission is available.
5. Record live Cognito/email smoke as completed or externally blocked.
6. Update roadmap, requirements, state, milestone snapshots, and final audit only after the gate is satisfied.

## Completion Criteria

- Backend focused tests pass.
- Backend Ruff passes.
- Frontend build passes.
- Frontend focused e2e passes or is explicitly accepted as blocked for closure.
- Live Cognito/email smoke status is recorded.
