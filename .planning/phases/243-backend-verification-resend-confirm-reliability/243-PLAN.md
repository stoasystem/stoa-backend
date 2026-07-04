# Phase 243 Plan: Backend Verification Resend Confirm Reliability

## Goal

Make backend registration verification, resend, confirm, activation, and local profile state consistent for deterministic local behavior.

## Steps

1. Add idempotent confirm behavior for locally verified profiles.
2. Repair stale local state when Cognito reports the user is already confirmed.
3. Normalize verification errors into support-safe `detail.code` responses.
4. Add focused backend tests for the new reliability cases.
5. Run focused auth lifecycle tests and Ruff.

## Non-Goals

- No frontend UX changes in this phase.
- No passwordless/custom-auth implementation in this phase.
- No live Cognito/email smoke without approved external credentials.
