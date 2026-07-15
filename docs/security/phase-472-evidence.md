# Phase 472 authorization evidence

Evidence window: 2026-07-15T00:21:21Z–2026-07-15T00:22:08Z UTC  
Source SHA: `c8cb6c6e2b4364ebe98d071b6f6410fa9fe3df05`  
Environment: local offline test process in `/Users/zhdeng/stoa-backend`  
Safety statement: **no production mutation, provider call, AWS call, network access, identity change, group change, grant change, or data mutation was performed.**

## Deterministic artifacts

| Artifact | SHA-256 | Result |
| --- | --- | --- |
| `docs/security/route-authorization-inventory.json` | `7dd3d59314983fc1ad974889723e404368b99f7588b228c68614c28cac08dfcf` | 219 unique registered method/path rows: 109 admin capability, 89 authorized, 14 explicit public, 4 safe-public, 3 authenticated-global |
| `docs/security/client-error-actions.json` | `b4ad8ef27773da0eac8521605eded3ecd3e7c1a23d3bceb3c2058b2bb493d895` | D-29/D-31 deterministic check passed; UI rendering/integration remains Phase 478 |
| local redacted reconciliation output | `dbd6c6109f9eab2d3fd26238a529ad6d90a31a2dca1088feeb1938035dce78f4` | dry-run only; 4 production-shaped fixtures, 11 tightening/isolation proposals, zero role or grant additions |

The OpenAPI `x-stoa-authorization` extension and checked JSON are generated from the same recursive `APIRoute.dependant` inspection. The inventory tests also mutate a newly registered router, a sensitive path, an event identifier, push-token body aliases, unrelated policy metadata, and endpoint-only metadata; each mutation fails closed.

## Exact automated commands and results

| UTC | Exact command | Result |
| --- | --- | --- |
| 2026-07-15T00:21:21Z | `.venv/bin/pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py` | PASS — 73 passed in 0.58s |
| 2026-07-15T00:21:22Z | `.venv/bin/pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` | PASS — 49 passed in 1.04s |
| 2026-07-15T00:21:23Z | `.venv/bin/pytest -q tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py` | PASS — 26 passed in 0.07s |
| 2026-07-15T00:21:23Z | `.venv/bin/pytest -q tests/test_notifications.py tests/test_websocket_notifications.py tests/test_client_error_actions.py tests/test_teacher_terminology_gate.py` | PASS — 49 passed in 0.86s |
| 2026-07-15T00:21:33Z | `.venv/bin/pytest -q tests/test_auth_security.py -k 'sec001 or sec004 or public_registration'` | PASS — 19 passed, 17 deselected in 0.29s |
| 2026-07-15T00:21:33Z | `.venv/bin/pytest -q tests/test_students.py tests/test_questions.py -k 'sec_002 or positive_controls'` | PASS — 4 passed, 17 deselected in 0.23s |
| 2026-07-15T00:21:34Z | `.venv/bin/python scripts/check_teacher_terminology.py --root . --allowlist docs/security/tutor-term-allowlist.json` | PASS — 13/13 exact negative-input or historical-reconciliation occurrences consumed; active-contract mutation tests also pass |
| 2026-07-15T00:21:34Z | `.venv/bin/python scripts/generate_client_error_actions.py --check` | PASS — byte-for-byte match |
| 2026-07-15T00:21:34Z | `.venv/bin/python scripts/generate_route_authorization_inventory.py --check` | PASS — byte-for-byte match |
| 2026-07-15T00:21:35Z | `.venv/bin/pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 459 passed in 5.60s |
| 2026-07-15T00:21:45Z | `.venv/bin/pytest -q` | OBSERVED RED — 932 passed, 23 failed in 22.40s |
| 2026-07-15T00:23:20Z | `.venv/bin/pytest -q tests/test_auth_security.py tests/test_teacher_onboarding.py tests/test_identity_authorization.py -k 'client or invitation or suspension or rotation'` | PASS — 12 passed, 61 deselected in 0.41s; deterministic local substitute only |

## Old audit reproductions and positive controls

- SEC-001: public registration rejects administrator, teacher, historical, case, Unicode, plural, whitespace, unknown, extra, and nested role selectors before Cognito or repository mutation. Valid student/parent commands remain covered by the focused auth suites.
- SEC-002: unrelated real and random student/question resources produce indistinguishable hidden 404 responses before effects. Owner student, active bidirectional bound parent, current-task teacher, and exact scoped administrator positive controls pass.
- SEC-004: wrong client, wrong issuer, wrong token use, expired token, unknown key, and JWKS outage deny safely. Allowed client, issuer-isolated two-key rotation/cache behavior, bounded known-key outage behavior, and active identity positive controls pass locally.
- Notification/event/push-token: owner reads/mutations pass; unrelated actors, missing IDs, wrong capability, role-only callers, and authorization outages deny before mutation. The two administrator notification routes require distinct exact capabilities.

## Dry-run reconciliation evidence

Command: `.venv/bin/python scripts/reconcile_privileged_identities.py --input /tmp/phase472-reconciliation-fixture.json --run-id phase-472-evidence`  
Mode: `dry-run`; input was deterministic local production-shaped data, not live provider data.

| Redacted item | Classification | Proposed automatic actions | Checkpoint | Manual elevation path |
| --- | --- | ---: | --- | --- |
| `identity_7a5826edb682ffcb0680` | multiple roles | 4 | `45cfadbecd555060f8c5a6db` | required for any restoration/addition |
| `identity_8cc5f748325464deddc8` | invalid capability/version | 4 | `c3d811e8b269cd51929a3fa1` | required for any restoration/addition |
| `identity_bf117a8a3d68bc22130f` | exact approved active match | 0 | `882fe211ec59ba5d522508d1` | not needed |
| `identity_fafcce6c974617d1b058` | missing approval | 3 | `7579fbf77c326037981eada6` | required for any restoration/addition |

The redaction assertion found no raw provider subject, issuer, user ID, group name, grant ID, email, token, or provider payload in output. Automatic apply code accepts only local suspension, excess-group removal, global sign-out, and grant revocation with stable action IDs. Any role addition, account restoration, capability grant, or activation is refused and requires a separately authorized active `admin_identity_manager` command. The CLI itself is read-only and refuses apply.

Rollback is code/config rollback plus continued local suspension and review. It never restores groups or grants broadly. A partial approved non-production batch resumes from per-action checkpoints; repeated actions use the stable action ID and completed actions/audit evidence are not duplicated.

## Full-suite limitation and ownership

The pre-Plan-10 baseline was 903 passed and 33 failed. Plan 10 made the owned reconciliation, route inventory, and stale semantic terminology contracts green. The current observation is 932 passed and 23 failed. All remaining failures are strict production-configuration fixtures in `test_external_activation_smoke.py`, `test_report_service.py`, and `test_subscription_operations.py`; they fail while constructing production `Settings` without the now-required Cognito issuer/access-client allowlists. They are assigned to Phase 474 and were not weakened or represented as Phase 472 success.

## External evidence gate

No separately approved non-production Cognito sandbox configuration was provided. Missing external evidence is therefore visible as NOT RUN, not a pass.

| Manual item | Status | Environment | Redacted identifier | Result | Cleanup / limitation |
| --- | --- | --- | --- | --- | --- |
| Cognito app-client and STOA group inventory | NOT RUN — approval/configuration unavailable | none | none | no provider access attempted | no cleanup; live configured set remains unverified |
| Allowed-client versus wrong-client real tokens | NOT RUN — approval/configuration unavailable | none | none | deterministic local claim cases passed only | no cleanup; real token/client binding remains external evidence |
| Teacher invitation activation and replay | NOT RUN — approval/configuration unavailable | none | none | deterministic local single-use/resume tests passed only | no sandbox identity created; provider convergence remains unverified |
| Suspension with an old valid token | NOT RUN — approval/configuration unavailable | none | none | deterministic fresh-local-status denial passed only | no group/session/profile mutation; real old-token behavior remains unverified |
| JWKS rotation | NOT RUN — approval/configuration unavailable | none | none | deterministic local two-key rotation and outage tests passed | no cleanup; provider rotation remains optional external evidence |
| Privileged identity reconciliation | NOT RUN for provider inventory/apply — approval/configuration unavailable | local fixture only | four `identity_*` values above | redacted dry-run passed; apply not authorized | no cleanup; no live data read and no mutation |

External beta or production rollout must not treat these NOT RUN entries as passed evidence.
