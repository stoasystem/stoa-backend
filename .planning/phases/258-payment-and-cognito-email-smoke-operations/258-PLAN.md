# Phase 258 Plan: Payment And Cognito Email Smoke Operations

## Objective

Make Stripe/TWINT and Cognito/email activation status operationally verifiable through a single admin-facing smoke report.

## Tasks

1. Add a provider activation smoke service that combines payment readiness with Cognito/email readiness.
2. Add a redacted admin endpoint for the combined report.
3. Add focused tests for blocked, read-only, and locally-ready states.
4. Record verification evidence and update milestone tracking.

## Verification

- Run focused tests for the new smoke report plus existing payment/account verification coverage.
- Run Ruff on touched source and test files.
- Confirm blocked states fail closed and secrets remain absent from responses.
