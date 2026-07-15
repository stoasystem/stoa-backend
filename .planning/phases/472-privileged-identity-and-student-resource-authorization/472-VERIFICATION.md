---
phase: 472-privileged-identity-and-student-resource-authorization
verified_at: 2026-07-15T03:30:00Z
status: gaps_found
verifier: gsd-verifier
requirements:
  total: 8
  passed: 6
  gaps: 2
  human_evidence_pending: 6
---

# Phase 472 Verification

## Verdict

**Status: `gaps_found`.** The two original reachable P0 exploit classes are materially tightened: public callers cannot self-provision privileged roles, and the registered student-resource routes now execute central, fail-closed authorization with positive and negative controls. The 459-test Phase 472 focused gate passes independently.

Phase 472 is not complete, however. The strict identity model is not connected end-to-end to ordinary student/parent registration and login, and privileged reconciliation can preserve active capability grants on a conflicted identity. These are phase-owned failures of V9AUTH-04 and the locked D-19/D-24 identity decisions. Four additional phase-owned contract/evidence gaps remain in route-inventory identifier discovery, authorization-event persistence, public provider-error redaction, and login identity selection.

The teacher-takeover race in the review is real, but it is explicitly and consistently owned by Phase 475 / V9DATA-02. It does not by itself fail Phase 472's authorization boundary.

## Automated Verification Performed

| Command | Result |
| --- | --- |
| `.venv/bin/pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | **459 passed in 5.86s** |
| Direct reconciliation probe: unapproved admin identity with one syntactically valid active grant | Classified `missing_approval`; proposed suspension/group removal/sign-out, but **no `remove_grant`**; after-state retained `grantCount: 1` |
| Direct route-inventory mutation: explicit-public `/probe` with nested `Depends` query parameter `student_id` | Inventory returned `identifiers=()`, `sensitive=False`, and **zero validation failures** |
| Runtime nested-parameter comparison across the real app | Found 11 registered authorized operations whose nested `question_id`/`student_id` was absent from inventory identifiers, including `/questions/{question_id}` and `/students/{student_id}/summary` |

The previously recorded independent full-suite observation is **932 passed / 23 failed**. The remaining 23 failures are strict production `Settings` fixtures in external activation, report, and subscription suites assigned to Phase 474. They are accurately disclosed and are not treated as a Phase 472 regression or as a green full-suite claim.

## Requirement Verification

| Requirement | Result | Evidence and reasoning |
| --- | --- | --- |
| V9AUTH-01 | PASS | `PublicRegistrationRole` permits only student/parent, and registration validates before provider/repository effects (`src/stoa/models/user.py:14`, `src/stoa/routers/auth.py:309-320`). SEC-001 mutation-recorder cases pass; canonical teacher terminology gate passes. |
| V9AUTH-02 | PASS | Routine admin lifecycle is capability-gated and audited; privileged binding creation is limited to the controlled service path (`src/stoa/services/privileged_identity_service.py:181`). Bootstrap remains a separate guarded path. Focused admin/bootstrap tests pass. |
| V9AUTH-03 | PASS | Teacher activation claims a digest-bound invitation once and creates the explicit binding only in the activation lifecycle (`src/stoa/services/teacher_application_service.py:205`, `:260`). Approval/replay/expiry/same-email/capability tests pass, and teacher role alone does not grant curriculum capability. |
| V9AUTH-04 | **GAP** | Strict protected-request resolution correctly requires a unique active binding and fresh active role/grants (`src/stoa/security/identity.py:95-130`), but ordinary registration stores a Cognito `UserSub` and profile without creating that binding (`src/stoa/routers/auth.py:323-426`). Login then chooses a local profile by email (`src/stoa/routers/auth.py:470-490`). Reconciliation also retains valid active grants for every non-exact/conflicted identity (`src/stoa/security/reconciliation.py:151-195`), so a later account restore can reactivate old capabilities without a separate grant approval. |
| V9AUTH-05 | PASS | Access-token verification is issuer/client/use/signature/time bound (`src/stoa/security/tokens.py:23`) with issuer-isolated bounded JWKS behavior (`src/stoa/security/jwks.py:45`). Wrong issuer/client/use, rotation, unknown-key, expiry, and outage cases pass with fail-closed local evidence. Live Cognito evidence remains NOT RUN. |
| V9ACCESS-01 | PASS, evidence gap | One typed policy decides owner, active bidirectional parent, current/scoped teacher, exact admin capability, and break-glass access (`src/stoa/security/authorization.py:390-528`). Policy matrices and outage/404/403 controls pass. The decision event is constructed but not durably emitted, addressed below. |
| V9ACCESS-02 | PASS for current enforcement, **inventory gap** | All 219 registered method/path operations have an executable classification and the migrated protected routes carry policy specs. However, `_route_identifiers()` inspects only root parameters (`src/stoa/security/route_inventory.py:124-131`), so nested dependency identifiers are invisible even though dependency policy metadata is traversed recursively. This invalidates the claimed identifier-completeness guard and Plan 472-10 mutation acceptance until fixed. |
| V9ACCESS-03 | PASS | The role/resource matrix, registered dependency routes, hidden-resource equivalence, stale/revoked binding/assignment cases, wrong-capability cases, and authorized positive controls all pass within the 459-test gate. |

## Required Gap Closure

### G-01 — Connect public registration and login to the stable subject binding

**Owner:** Phase 472, V9AUTH-04, D-19.  
**Evidence:** Registration receives the provider subject at `src/stoa/routers/auth.py:323-329`, writes only a profile at `:396-426`, and production binding creation occurs only in teacher/admin services. Missing binding is an unconditional identity conflict at `src/stoa/security/identity.py:95-100`. Login selects `Limit=1` email-GSI data at `src/stoa/routers/auth.py:470-490` and `src/stoa/db/repositories/user_repo.py:20-28` rather than resolving the returned token subject.

Create/reconcile the canonical `(issuer, sub) -> user_id` binding in the student/parent registration-confirmation lifecycle with safe, idempotent partial-failure handling. Verify the just-issued access token and use its binding for login response/profile/status decisions. Add end-to-end student and parent tests for register → confirm → Actor resolution, duplicate email profiles, subject mismatch, binding conflict, retry, and revoked status.

### G-02 — Quarantine or revoke every capability on conflicted privileged identities

**Owner:** Phase 472, V9AUTH-04, D-24.  
**Evidence:** `invalid_grants` contains only malformed/inactive/version-zero grants (`src/stoa/security/reconciliation.py:151-154`); non-exact identities remove only that subset (`:181-189`) and retain the remaining count (`:191-195`). Fresh Actor resolution accepts all retained active versioned grants (`src/stoa/security/identity.py:118-130`). The direct probe reproduced a `missing_approval` identity whose valid active global grant remained present.

For every non-`exact_approved_active_match` privileged identity, revoke or quarantine all current grants so account restoration cannot restore them. Require separate, explicit `admin_identity_manager` approval to issue new grant versions. Add missing-approval, duplicate-binding, multi-role, group mismatch, restore, and replay tests with otherwise valid active grants.

### G-03 — Make route identifier discovery recursive

**Owner:** Phase 472, V9ACCESS-02 / Plan 472-10 acceptance.  
**Evidence:** `_walk_dependants()` exists at `src/stoa/security/route_inventory.py:83-92`, but `_route_identifiers()` reads only `route.dependant` at `:124-131`. A synthetic public endpoint with nested `student_id` passed validation as nonsensitive. Eleven real authorized routes also omit nested identifiers from their inventory projection.

Aggregate path/query/body identifiers over the full dependency tree, including nested Pydantic/Annotated/container shapes, and add public/global nested-dependency mutations that must fail.

### G-04 — Persist authorization decisions and probe evidence

**Owner:** Phase 472, D-32 and Plan 472-05 task 03.  
**Evidence:** Policy evaluation creates a redacted event at `src/stoa/security/authorization.py:468-481`, but `authorize_and_resolve()` discards it at `:587-592`. `append_authorization_event()` has no production caller outside break-glass helpers (`src/stoa/db/repositories/security_audit_repo.py:83-87`, `:128-146`).

Wire a durable audit sink for required denials, sensitive allows, and bounded probe aggregation; define audit-outage semantics and prove redaction, persistence, aggregation, and fail-closed behavior where evidence is mandatory.

### G-05 — Normalize public Cognito failures through the safe error boundary

**Owner:** Phase 472, D-28 / Plan 472-01 safe-error truth.  
**Evidence:** Public auth endpoints return interpolated `Cognito error: {code}` at `src/stoa/routers/auth.py:363`, `:468`, `:579`, `:687`, `:748`, `:782`, `:848`, and `:876`, bypassing `{code,message,correlationId}`.

Map unknown provider failures to stable redacted dependency/authentication errors and keep provider codes in internal redacted telemetry only. Add parameterized canary tests for every public auth endpoint.

## Code Review Finding Adjudication

| Finding | Adjudication |
| --- | --- |
| CR-01 missing public registration binding | **Confirmed phase blocker.** G-01; V9AUTH-04/D-19 and legitimate new-account functionality are unmet. |
| CR-02 non-atomic teacher takeover | **Confirmed defect, deferred to Phase 475.** The current read then unconditional write at `src/stoa/routers/teachers.py:182-219` can admit two winners, but ROADMAP Phase 475 success criterion 2 and V9DATA-02 explicitly own the conditional question/session/notification transaction. Phase 472's policy reads current facts and fails closed outside that write race as scoped in research. |
| CR-03 reconciliation preserves valid grants on conflict | **Confirmed phase blocker.** G-02; violates D-24 and V9AUTH-04 reconciliation authority. |
| WR-01 nested dependency identifiers omitted | **Confirmed phase-owned gap.** G-03; current route policy enforcement is green, but the executable completeness proof is unsound. |
| WR-02 authorization events not persisted | **Confirmed phase-owned gap.** G-04; violates D-32 and the Plan 472-05 locked acceptance contract. |
| WR-03 Cognito codes exposed | **Confirmed phase-owned gap.** G-05; access-token verifier remains redacted, but the broader Phase 472 public API error boundary is not. |
| WR-04 login uses email profile | **Confirmed and folded into G-01.** It violates D-19 and can disclose/select the wrong local profile even though later protected requests fail on missing/mismatched binding. |

## External And Cross-Phase Limitations

- All six Cognito sandbox items remain honestly **NOT RUN — approval/configuration unavailable**. Deterministic local substitutes passed, but they are not live provider evidence and do not authorize beta/production rollout.
- The 23 full-suite failures remain Phase 474-owned deterministic-settings/fixture work. No test was weakened.
- The teacher claim/session/notification atomicity defect remains Phase 475-owned V9DATA-02 work and must be closed before Phase 475 can pass.
- No AWS, network, sandbox, or production mutation was performed by this verification.

## Recommended Next Action

Run gap planning for Phase 472 and close G-01 through G-05 before marking the phase complete. Preserve CR-02 as an explicit Phase 475 dependency rather than silently absorbing or forgetting it.

## Verification Complete
