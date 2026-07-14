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
| **Focused phase gate** | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` |
| **Full suite command** | `pytest -q` |
| **Estimated runtime** | Quick/security under 10s; route matrix under 30s; focused gate under 90s (measure during execution) |

All focused tests inject the clock, JWKS transport, Cognito client, and repositories. They must not use real AWS credentials or network access. The current unrelated full-suite baseline is recorded honestly; Phase 474 owns global green-suite and CI isolation work.

---

## Sampling Rate

- **After every task commit:** Run the smallest changed/new test file plus its direct existing regression file.
- **After every plan wave:** Run the focused phase gate.
- **Before `$gsd-verify-work`:** Run all focused commands, compare the generated route inventory, scan for forbidden `tutor` contracts, and record the full-suite result without hiding unrelated failures.
- **Max feedback latency:** 10s for unit/security changes, 30s for inventory/matrix changes, and 90s for a wave gate.
- **Continuity rule:** No three consecutive implementation tasks may lack an automated verification command.

---

## Per-Task Verification Map

The planner may split route migration into additional plans; each resulting task must retain the corresponding requirement and threat reference below.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 472-01-* | 01 | 0 | All | T-472-01..08 | Security contracts and executable red-test fixtures exist before implementation | unit/contract | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py` | ❌ W0 | ⬜ pending |
| 472-02-* | 02 | 1 | V9AUTH-04, V9AUTH-05 | T-472-02, T-472-03 | Tokens are client/issuer/use bound; identity resolves explicitly; conflicts and outages deny | unit/integration | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py` | ❌ W0 | ⬜ pending |
| 472-03-* | 03 | 1 | V9AUTH-01 | T-472-01 | Public flows cannot create teacher/admin privilege and `tutor` is rejected everywhere | API/regression | `pytest -q tests/test_auth_security.py tests/test_auth_account_lifecycle.py` | partial | ⬜ pending |
| 472-04-* | 04 | 2 | V9AUTH-02, V9AUTH-03, V9AUTH-04 | T-472-04, T-472-05 | Grants and privileged lifecycles are scoped, idempotent, auditable, and immediately revocable | API/state-machine | `pytest -q tests/test_teacher_onboarding.py tests/test_identity_authorization.py tests/test_provision_production_admin.py` | partial | ⬜ pending |
| 472-05-* | 05 | 2 | V9ACCESS-01, V9ACCESS-03 | T-472-06, T-472-07 | Central policy enforces owner, formal parent, task-scoped teacher, and purpose capability | policy matrix | `pytest -q tests/test_identity_authorization.py tests/test_student_authorization_matrix.py` | ❌ W0 | ⬜ pending |
| 472-06-* | 06 | 3 | V9ACCESS-02, V9ACCESS-03 | T-472-06, T-472-08 | Every sensitive registered route has executable policy metadata and positive/negative controls | route inventory/matrix | `pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | ❌ W0 | ⬜ pending |
| 472-07-* | 07 | 4 | V9AUTH-02, V9AUTH-04, V9ACCESS-03 | T-472-02, T-472-05, T-472-07 | Reconciliation is dry-run-first, idempotent, auto-tightens only, and redacts evidence | migration/regression | `pytest -q tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py` | partial | ⬜ pending |

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

- [x] Every provisional plan slice has an automated command or explicit Wave 0 dependency.
- [x] Sampling continuity prevents three consecutive tasks without automated verification.
- [x] Wave 0 names every currently missing focused test/fixture.
- [x] Commands contain no watch-mode flags or live-network dependency.
- [x] Expected feedback latency is bounded and will be measured during execution.
- [x] `nyquist_compliant: true` is set because the strategy maps every phase requirement to executable evidence; `wave_0_complete` remains false until the files exist.

**Approval:** pending plan-checker verification
