# Phase 242 Plan: Verification And Login Reality Audit

## Goal

Define the exact v5.14 verification/login reliability contract from the current backend, frontend, and support surfaces.

## Steps

1. Map backend registration, login, resend, confirm, login-code, and password-reset behavior to concrete routes/services/tests.
2. Map frontend verification screens and auth API behavior, including demo fallback boundaries.
3. Classify behavior as implemented, partial, deferred, demo-only, or externally blocked.
4. Document the canonical v5.14 policy contract and release evidence expectations.

## Non-Goals

- Do not implement custom passwordless auth in Phase 242.
- Do not perform live Cognito/email smoke without approved credentials and environment.
- Do not change frontend UI in the audit phase.

## Completion Criteria

- Reality audit document exists with file/route/service evidence.
- Login-code/passwordless references are classified.
- Roadmap, requirements, state, and milestone snapshots mark AUTHREL-01 complete and move active work to Phase 243.
