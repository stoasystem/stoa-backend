---
last_mapped_commit: ddd2a559cb3f5c82345252fdef0d4c948f0c2155
date: 2026-07-15
---

# Testing

**Mapped:** 2026-07-15
**Scope:** Whole-repository reference, incrementally refreshed from `.gitignore`, `.planning/`, `docs/`, and `mobile/`

## Current Test State

- The previous map's statement that no tests existed is obsolete. Phase 472 evidence records a 1,106-test full-suite observation: 1,083 passed and 23 failed, with zero errors or skips.
- The 23 failures are the accepted Phase 474-owned strict production `Settings` fixture boundary, not Phase 472 regressions. They are grouped in `tests/test_external_activation_smoke.py` (2), `tests/test_report_service.py` (3), and `tests/test_subscription_operations.py` (18).
- `docs/security/phase-472-evidence.md` and `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-VERIFICATION.md` are the current source-bound records for counts, commands, timestamps, and limitations.
- Phase 472 is independently passed for its focused authorization/security scope. The global suite remains observed red until Phase 474 modernizes the strict production fixtures and establishes deterministic gated delivery.

## Python Test Tooling

- `pyproject.toml` declares pytest 8.2+, `pytest-asyncio`, Moto AWS extras, Ruff, and mypy.
- Pytest uses automatic asyncio mode and discovers under `tests/`.
- FastAPI routes are exercised with `TestClient`; async behavior uses pytest-asyncio where needed.
- Botocore `ClientError` fixtures cover provider failures. Moto is used only where AWS service semantics materially matter; most Phase 472 tests inject repositories and provider clients directly.
- Focused security tests inject clocks, JWKS transport, Cognito clients, and repositories. They must not rely on real AWS credentials or network access.

## Test Organization And Patterns

- Test modules are organized by behavior or boundary, for example `tests/test_auth_security.py`, `tests/test_identity_authorization.py`, `tests/test_student_authorization_matrix.py`, and `tests/test_route_authorization_inventory.py`.
- Security assertions include both deny/adversarial cases and legitimate positive controls so a blanket-deny implementation cannot pass.
- Authorization tests exercise the Actor/identity/policy boundary rather than bypassing it with raw claims.
- State-machine tests cover replay, stale expected state, partial failure, outage, restore, and revocation behavior.
- Mutation sentinels assert that rejected requests and audit outages produce zero protected effects.
- Public-error tests assert exact allowlisted fields, stable HTTP/action mapping, safe copy, bounded retry semantics, and absence of provider canaries.
- Redaction tests search responses, logs, audit rows, generated evidence, and exceptions for forbidden identifiers or secret material.
- Generated-contract tests compare checked artifacts byte-for-byte and include mutation cases that prove the check fails when source and artifact diverge.
- Terminology tests use a semantic allowlist for exact negative/historical fixtures and mutation controls; active contracts use teacher.

## Phase 472 Focused Gates

The validation contract is `.planning/phases/472-privileged-identity-and-student-resource-authorization/472-VALIDATION.md`.

- Quick identity/security: `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py`
- Route and resource matrix: `pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py`
- Reconciliation: `pytest -q tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py`
- Notification and client contract: `pytest -q tests/test_notifications.py tests/test_websocket_notifications.py tests/test_client_error_actions.py tests/test_teacher_terminology_gate.py`
- Final six-finding gate: `pytest -q tests/test_public_identity_lifecycle.py tests/test_auth_account_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_admin_authorization.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_route_authorization_inventory.py`
- Full suite observation: `pytest -q`

The latest independent Phase 472 verification records 321/321 for the final six-finding gate and 610/610 for the extended phase gate. Exact historical commands and counts remain in the phase validation/evidence documents rather than being normalized into a single claimed result.

## Contract And Terminology Checks

- Route inventory check: `.venv/bin/python scripts/generate_route_authorization_inventory.py --check`
- Client error action check: `.venv/bin/python scripts/generate_client_error_actions.py --check`
- Semantic terminology check: `.venv/bin/python scripts/check_teacher_terminology.py --root . --allowlist docs/security/tutor-term-allowlist.json`
- The checked outputs are `docs/security/route-authorization-inventory.json` and `docs/security/client-error-actions.json`.
- Release evidence requires two byte-identical generator runs before the `--check` pass and records SHA-256 artifact digests.

## Mobile Quality Surface

- `mobile/package.json` exposes `npm run typecheck`, which runs `tsc --noEmit` under strict Expo TypeScript configuration.
- `mobile/package.json` exposes `npm run test:contracts`, which runs `mobile/scripts/validate-mobile-contracts.mjs`.
- The mobile contract script statically checks required packages, the deep-link scheme, route-group declarations, and required public environment names. It does not render screens, call providers, or validate runtime endpoint response shapes.
- `mobile/docs/RELEASE_EVIDENCE.md` records a historical v5.19 focused command, `pytest tests/mobile`, with 26 passing Python-side mobile contract tests. That document also states that dependencies, native builds, EAS builds, physical-device QA, and live push smoke were not run in that milestone.
- No JavaScript unit-test runner is declared in `mobile/package.json`; current mobile-local automation is TypeScript compilation plus static contract validation.

## Mobile Test Targets And Invariants

- `mobile/src/config/mobileConfig.ts`: required environment values, trailing-slash normalization, release-channel fallback, and enforced no-demo-fallback mode.
- `mobile/src/services/auth/amplifyAuth.ts`: token absence, role filtering, verification-required transitions, session restoration, and provider error normalization.
- `mobile/src/services/auth/signOutCleanup.ts`: push revocation, query-cache clearing, secure metadata clearing, and sign-out order/failure behavior.
- `mobile/src/services/api/mobileApiClient.ts`: bearer header, JSON encoding, empty/non-JSON error bodies, and `MobileApiError` status/body preservation.
- `mobile/src/services/auth/accountState.ts`: status/code precedence and safe mapping for verification, entitlement, billing, child binding, quota, provider, 401, 403, and unknown failures.
- `mobile/src/services/notifications/deepLinks.ts`: signed-out, blocked-account, role-mismatch, unknown-target, identifier encoding, and allowed target cases.
- `mobile/src/services/offline/readThroughCache.ts`: TTL boundaries, stale marking at exact expiry, and cache clearing.
- `mobile/src/providers/AppProviders.tsx`: one retry for reads and zero retries for mutations.
- `mobile/src/features/student/studentScreens.ts` and `mobile/src/features/parent/parentScreens.ts`: route/endpoint parity, complete state sets, and online-only mutation classification.
- `mobile/src/release/deviceQa.ts` and `mobile/src/release/releaseTelemetry.ts`: forbidden evidence/telemetry fields and blocker classification.

## Phase 472 / Phase 474 Boundary

- Phase 472 owns focused identity and resource-authorization behavior, adversarial/positive regressions, deterministic authorization/client contracts, and truthful local evidence.
- Phase 472 success requires zero new phase-owned failures. Its full-suite run is an observation and may remain red only by the exact accepted Phase 474 set.
- Phase 474 owns clean Python 3.12 bootstrap, deny-network/AWS isolation, frozen-time reliability, repair of strict production fixtures, repeatably green full-suite runs, Ruff/mypy/dependency gates, Linux-arm64 package smoke, and CI verify/build/deploy separation.
- Do not weaken production validation, edit focused assertions to absorb global failures, reassign known failures, or state that a red full suite passed.
- Phase 475 separately owns transactional teacher claim/session/notification behavior and other multi-write consistency; those atomicity cases are not Phase 472 or Phase 474 closure evidence.

## Security Evidence Rules

- Record exact command, UTC timestamp, result/count, tested source SHA, and relevant artifact digest.
- Separate focused green gates, full-suite observations, deterministic local substitutes, and external checks.
- Record unavailable external checks as `NOT RUN — approval/configuration unavailable`; local provider doubles do not prove live-provider behavior.
- Keep evidence redacted and canary-tested. Never copy credentials, tokens, raw provider payloads, private object keys, prompts, answers, transcripts, billing payloads, or raw identifiers.
- State whether network, AWS, provider, or production mutation occurred. If an external operation is approved, record its environment, redacted identifier, and cleanup limitation.
- Preserve historical results in `docs/security/phase-472-evidence.md`; append new source-bound observations instead of rewriting old counts.

## GSD Verification Cadence

- After each task: run the smallest changed test plus its direct regression module.
- After each wave: run the phase-focused gate.
- Before phase verification: run every focused family, deterministic generator checks, terminology mutation checks, and the full suite as a separately classified observation.
- Validation maps tasks to requirements and executable commands; verification independently inspects source and reruns evidence before declaring a phase passed.
- `.planning/config.json` enables plan checking, verification, Nyquist validation, and source-grounded review; automatic phase advance remains disabled.

## General Verification Commands

- Full Python suite: `uv run python -m pytest -q --tb=short`
- Ruff: `uv run ruff check src tests`
- Mypy baseline: `uv run mypy src`
- Mobile TypeScript: `cd mobile && npm run typecheck`
- Mobile static contracts: `cd mobile && npm run test:contracts`

Phase 474 is responsible for turning these into a repeatable clean-checkout, no-network/AWS, gated delivery baseline. Until then, command results must be reported exactly rather than assumed from configuration.
