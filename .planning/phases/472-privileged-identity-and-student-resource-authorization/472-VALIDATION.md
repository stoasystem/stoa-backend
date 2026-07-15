---
phase: 472
slug: privileged-identity-and-student-resource-authorization
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-14
---

# Phase 472 — Validation Strategy

> Per-phase validation contract for privileged identity and student-resource authorization work.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest>=8.2`, FastAPI `TestClient`, `pytest-asyncio`, botocore `ClientError`; moto only where DynamoDB semantics add value |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py` |
| **Route/matrix command** | `pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` |
| **Migration command** | `pytest -q tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py` |
| **Notification/client-contract command** | `pytest -q tests/test_notifications.py tests/test_websocket_notifications.py tests/test_client_error_actions.py tests/test_teacher_terminology_gate.py` |
| **Focused phase gate** | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | Quick/security under 10s; route matrix under 30s; focused gate under 90s (measure during execution) |

All focused tests inject the clock, JWKS transport, Cognito client, and repositories. They must not use real AWS credentials or network access. The current unrelated full-suite baseline is recorded honestly; Phase 474 owns global green-suite and CI isolation work.

---

## Sampling Rate

- **After every task commit:** Run the smallest changed/new test file plus its direct existing regression file.
- **After every plan wave:** Run the focused phase gate.
- **Before `$gsd-verify-work`:** Run all focused commands, compare the generated route inventory and client error-action contract, execute the semantic teacher-terminology gate plus its mutation test, and record the full-suite result without hiding unrelated failures.
- **Max feedback latency:** 10s for unit/security changes, 30s for inventory/matrix changes, and 90s for a wave gate.
- **Continuity rule:** No three consecutive implementation tasks may lack an automated verification command.

---

## Per-Task Verification Map

This map follows the actual ten plans and waves 0–5. Every plan task inherits its row's requirements and threat references.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 472-01-* | 01 | 0 | All | T-472-01..09 | Security/error/action contracts and executable red-test fixtures exist before implementation | unit/contract | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py` | ❌ W0 | ⬜ pending |
| 472-02-* | 02 | 1 | V9AUTH-04, V9AUTH-05 | T-472-02, T-472-03 | Tokens are client/issuer/use bound; identity resolves explicitly; conflicts and outages deny | unit/integration | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py` | ❌ W0 | ⬜ pending |
| 472-03-* | 03 | 1 | V9AUTH-01 | T-472-01, T-472-08 | Public flows cannot create privilege; semantic gate forbids active tutor contracts while preserving exact negative/historical fixtures | API/regression/gate | `pytest -q tests/test_auth_security.py tests/test_auth_account_lifecycle.py tests/test_teacher_terminology_gate.py` | partial | ⬜ pending |
| 472-04-* | 04 | 2 | V9AUTH-02, V9AUTH-03, V9AUTH-04 | T-472-04, T-472-05 | Grants and privileged lifecycles are scoped, idempotent, auditable, and immediately revocable | API/state-machine | `pytest -q tests/test_teacher_onboarding.py tests/test_identity_authorization.py tests/test_provision_production_admin.py` | partial | ⬜ pending |
| 472-05-* | 05 | 3 | V9ACCESS-01, V9ACCESS-03 | T-472-05, T-472-06, T-472-07 | Central policy enforces owner, formal parent, task-scoped teacher, and purpose capability | policy matrix | `pytest -q tests/test_identity_authorization.py tests/test_student_authorization_matrix.py` | ❌ W0 | ⬜ pending |
| 472-06-* | 06 | 4 | V9ACCESS-02, V9ACCESS-03 | T-472-06, T-472-07 | Student, question, and conversation identifiers use executable policy with allow/deny controls | API/matrix | `pytest -q tests/test_student_authorization_matrix.py tests/test_questions.py` | partial | ⬜ pending |
| 472-07-* | 07 | 4 | V9ACCESS-02, V9ACCESS-03 | T-472-06, T-472-07 | Practice, adaptive, and parent resources enforce owner/formal-binding scope | API/matrix | `pytest -q tests/test_student_authorization_matrix.py tests/test_parent_children.py tests/test_adaptive_learning.py` | partial | ⬜ pending |
| 472-08-* | 08 | 4 | V9ACCESS-02, V9ACCESS-03 | T-472-05, T-472-06 | Teacher, help, conversation, assistance, and AI-tool access remains assignment/purpose scoped | API/matrix | `pytest -q tests/test_student_authorization_matrix.py tests/test_teacher_dispatch.py tests/test_ai_teacher_tools.py` | partial | ⬜ pending |
| 472-09-* | 09 | 4 | V9AUTH-02, V9ACCESS-02, V9ACCESS-03 | T-472-05, T-472-06, T-472-07 | Admin operations require exact capabilities; notification event/push-token resources are Actor-owned and both admin notification routes are separately scoped | API/inventory | `pytest -q tests/test_admin_authorization.py tests/test_notifications.py tests/test_websocket_notifications.py` | partial | ⬜ pending |
| 472-10-* | 10 | 5 | All | T-472-01..09 | All registered routers are inventoried; terminology/client contracts are deterministic; reconciliation auto-tightens only; evidence is honest | inventory/migration/evidence | `pytest -q tests/test_route_authorization_inventory.py tests/test_teacher_terminology_gate.py tests/test_client_error_actions.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py` | ❌ W0/partial | ⬜ pending |
| 472-11-* | 11 | 6 | V9AUTH-04, V9AUTH-05 | G-01 | Public student/parent lifecycle establishes and resolves one issuer-subject binding; email is never an authorization fallback | API/integration | `pytest -q tests/test_public_identity_lifecycle.py` | ✅ | ✅ green |
| 472-12-* | 12 | 6 | V9AUTH-04 | G-02 | Every non-exact privileged identity loses all current grants and restore cannot revive them | reconciliation/state-machine | `pytest -q tests/test_privileged_identity_reconciliation.py` | ✅ | ✅ green |
| 472-13-* | 13 | 7 | V9ACCESS-02, V9ACCESS-03 | G-03 | Recursive dependency and annotation identifiers are classified and require compatible executable policy | inventory/mutation | `pytest -q tests/test_route_authorization_inventory.py` | ✅ | ✅ green |
| 472-14-* | 14 | 6 | V9ACCESS-01, V9ACCESS-02, V9ACCESS-03 | G-04 | Deny, probe, and sensitive allow decisions persist redacted evidence and sensitive effects fail closed on audit outage | audit/integration | `pytest -q tests/test_authorization_audit.py` | ✅ | ✅ green |
| 472-15-* | 15 | 8 | V9AUTH-05 | G-05 | All eight public provider operations expose only stable actionable structured errors and redacted telemetry | API/contract | `pytest -q tests/test_public_auth_error_boundary.py tests/test_client_error_actions.py` | ✅ | ✅ green |
| 472-16-* | 16 | 9 | V9AUTH-04, V9AUTH-05, V9ACCESS-01, V9ACCESS-02, V9ACCESS-03 | G-01..G-05 | All five closures and earlier Phase 472 controls pass together; generated contracts and limitations are recorded truthfully | integration/evidence | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/security/conftest.py` — Actor, binding, relationship, assignment and grant builders; frozen clock; RSA/JWKS fixtures; fake Cognito and repositories.
- [ ] `tests/test_auth_security.py` — public role barrier plus access-token, client, issuer, token-use and JWKS validation.
- [ ] `tests/test_identity_authorization.py` — explicit identity binding, one-role intersection, active state, grant authority, revocation, outage and safe-error behavior.
- [ ] `tests/test_teacher_onboarding.py` — immutable application/review/invitation/activation state machine.
- [ ] `tests/test_student_authorization_matrix.py` — actor-resource-action-purpose matrix across all route families with positive controls.
- [ ] `tests/test_route_authorization_inventory.py` — registered route coverage and deterministic OpenAPI/inventory projection.
- [ ] `tests/test_privileged_identity_reconciliation.py` — dry-run/apply, automatic tightening only, checkpoints, idempotency and evidence redaction.
- [ ] `tests/test_client_error_actions.py` — exhaustive structured-code mapping, correlation-ID support, one refresh, 403/404 no-retry, 409 recovery, Retry-After and bounded idempotent-read/non-idempotent-write behavior.
- [ ] `tests/test_teacher_terminology_gate.py` — exact allowlist semantics and an active tutor-contract mutation that must fail.

Existing regression files to extend include `test_auth_account_lifecycle.py`, `test_parent_children.py`, `test_questions.py`, `test_teacher_dispatch.py`, `test_adaptive_learning.py`, `test_ai_teacher_tools.py`, `test_curriculum_ops.py`, and `test_provision_production_admin.py`. Tests that claim to verify authorization must exercise the Actor/identity/policy boundary rather than bypass it with a bare raw-claims override.

---

## Threat Coverage

| Ref | Threat | Required automated evidence |
|-----|--------|-----------------------------|
| T-472-01 | Public payload, confirmation, login or refresh creates privileged role, including case/Unicode/legacy aliases | Exact self-service allowlist; zero provider/database mutation on rejection; `teacher`, `admin`, `tutor`, variants and replay denied |
| T-472-02 | Validly signed token is accepted from the wrong issuer, client, token use or stale/rotated key | Wrong issuer/client/use denial; issuer-keyed bounded cache; unknown-`kid` refresh; rotation and outage behavior |
| T-472-03 | Email fallback, multiple groups or request-time repair binds/broadens the wrong identity | Explicit `(issuer, sub)` binding only; zero/multiple/mismatched groups denied; no authentication-path mutation |
| T-472-04 | Invitation replay/concurrency or provider partial failure activates duplicate/excess teacher privilege | Conditional single consumption; same verified email; idempotent resumption; local non-active until reconciled |
| T-472-05 | Broad admin role or stale grant enables privilege management/student access | Exact current capability/scope/version required; old token denied immediately after suspension or revocation |
| T-472-06 | Unrelated parent/teacher/admin accesses student resources through a forgotten or indirect identifier route | Generated registered-route inventory plus full negative and positive policy matrix |
| T-472-07 | Outage, missing fact or error differences leak resource existence or fail open | Repository exceptions return safe 503; 403/404 existence policy; no handler mutation or secret/provider leakage |
| T-472-08 | Hand-maintained authorization inventory drifts from executable FastAPI dependencies | Synthetic unprotected sensitive route makes inventory test fail; OpenAPI projection equals dependency metadata |
| T-472-09 | Client recovery mapping leaks detail, loops refresh, or retries denied/non-idempotent operations | Exhaustive generated code/action contract; one-refresh cap; 403/404 no retry; 409 recovery; bounded Retry-After idempotent-read behavior; no automatic non-idempotent write replay |

Every route-family matrix includes at least one authorized positive control so blanket denial cannot pass. Responses, logs and audit records use canary assertions to exclude tokens, emails, content, object keys and raw provider messages.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Inventory configured Cognito app clients and STOA groups | V9AUTH-01, V9AUTH-05 | Depends on separately approved sandbox configuration | Read-only inventory without client secrets; compare exact allowed client/group set to configuration. |
| Allowed-client versus wrong-client access tokens | V9AUTH-05 | Requires real sandbox-issued tokens | Call the same protected endpoint; allowed client succeeds and different same-pool client receives the safe authentication error. |
| Teacher invitation activation and replay | V9AUTH-03 | Validates Cognito/local convergence | Approve and consume one sandbox invitation; verify one teacher group/profile/binding and that replay creates no change. |
| Suspension with an old still-valid token | V9AUTH-04, V9ACCESS-01 | Validates provider plus fresh local status | Suspend sandbox account, remove group/global session as defense in depth, then confirm backend denies the old token from local state. |
| JWKS rotation | V9AUTH-05 | Sandbox may not expose safe rotation controls | Exercise if safely available; otherwise retain deterministic local two-key rotation evidence and document limitation. |
| Reconciliation production-shaped evidence | V9AUTH-02, V9AUTH-04 | External identities and mutation need separate authority | Run dry-run only; do not apply any production mutation without a separate explicit approval. |

---

## Validation Sign-Off

- [x] Every actual Plan 01–10 slice and Wave 0–5 has an automated command or explicit Wave 0 dependency.
- [x] Sampling continuity prevents three consecutive tasks without automated verification.
- [x] Wave 0 names every currently missing focused test/fixture.
- [x] Commands contain no watch-mode flags or live-network dependency.
- [x] Expected feedback latency is bounded and will be measured during execution.
- [x] `nyquist_compliant: true` is set because the strategy maps every phase requirement to executable evidence; `wave_0_complete` remains false until the files exist.

**Approval:** pending plan-checker verification

## Plan 472-16 Execution Observation

- **Tested source SHA:** `6d7b54c682e032660461b907d19ab112c5b5a8d6` (the Task 1 verification-only commit; implementation source is unchanged from `14000ce906e8945fb6b254975fdc92953c934acf`).
- **G-01..G-05 reproduction gate:** `114 passed in 1.69s`; no skips or xfails.
- **Extended focused Phase 472 gate:** `546 passed in 10.11s`.
- **Teacher terminology semantic gate:** PASS; all 13 exact negative/historical occurrences consumed, with `10 passed` in the mutation/contract module.
- **Generated contracts:** both generators were run twice, compared byte-for-byte, and passed `--check`. Route inventory SHA-256 is `0d5e6d193febd94f6a80c48b5002e813d05b6b7fe815f1cef1b34d2bfa86a139`; client actions SHA-256 is `32567c792e1f216a263342c0e60d1323b03744d68d4cf3b7db502d19ddf40f15`.
- **Full-suite observation:** `1019 passed, 23 failed in 33.60s`. The delta from the accepted Phase 474 baseline is zero. All failures remain strict production `Settings` fixtures in `tests/test_external_activation_smoke.py` (2), `tests/test_report_service.py` (3), and `tests/test_subscription_operations.py` (18); no Phase 472 failure is hidden or reassigned.
- **External evidence:** the six Cognito sandbox checks remain **NOT RUN — approval/configuration unavailable**. No AWS, network, provider, sandbox, or production write was attempted.
- **Cross-phase boundary:** teacher takeover/session/notification atomicity remains Phase 475/V9DATA-02 and is not claimed closed here.
