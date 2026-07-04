# Phase 245 Plan: Frontend Verification Recovery And Admin Support Visibility

## Goal

Make verification/login recovery states clear and actionable for users and support/admins.

## Steps

1. Add bounded backend support fields for verification recovery state and support action.
2. Ensure `/admin/account-verification/{user_id}` includes the same support-safe recovery fields.
3. Ensure parent/admin account operations include recovery state/action through profile verification summaries.
4. Render recovery evidence in parent and admin account operations views.
5. Verify backend focused tests, Ruff, and frontend build.

## Non-Goals

- No raw verification code visibility.
- No token, secret, or Cognito challenge material in support surfaces.
- No admin verification override mutation in this phase.
