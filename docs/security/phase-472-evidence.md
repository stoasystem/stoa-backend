# Phase 472 authorization evidence

Evidence window: 2026-07-15T18:20:13Z–2026-07-15T18:21:23Z UTC<br>
Tested source SHA: `9ed55ae9b85c5dff21f74615cfcb207c2338b082` (includes post-wave ordering test `69da80319cf2e6abb0f6c2d8d85fc42aca6ca211`, integration fix `f80e23f53459163307632c3194e4c73be0bb4879`, and the Plan 22 multi-target integration matrix)<br>
Environment: local offline test process in `/Users/zhdeng/stoa-backend`<br>
Safety statement: **no production mutation, provider call, AWS call, network access, identity change, group change, grant change, or external data mutation was performed.** All test effects were deterministic in-memory/local fixtures.

## Deterministic artifacts

| Artifact | SHA-256 | Result |
| --- | --- | --- |
| `docs/security/route-authorization-inventory.json` | `f32226095cf3a0992b1cf94e28f6aefd713580fb839694a88c8c5dcbfaf5eaad` | 219 unique registered method/path rows, including executable typed-provider metadata on 20 body-target routes; generated twice, byte-identical, then `--check` passed |
| `docs/security/client-error-actions.json` | `4bdb9169ff44d6352492ac7956f8ea331c0b2e62862dc6ca66d07bc47ab36317` | D-29/D-31 deterministic check passed after two byte-identical generations; UI rendering/integration remains Phase 478 |
| local redacted reconciliation output | `dbd6c6109f9eab2d3fd26238a529ad6d90a31a2dca1088feeb1938035dce78f4` | dry-run only; 4 production-shaped fixtures, 11 tightening/isolation proposals, zero role or grant additions |

The OpenAPI `x-stoa-authorization` extension and checked JSON are generated from the same recursive `APIRoute.dependant` inspection. The inventory tests also mutate a newly registered router, a sensitive path, an event identifier, push-token body aliases, unrelated policy metadata, and endpoint-only metadata; each mutation fails closed.

## Final-review CR-01, CR-02, and WR-01 through WR-04 closure

The source-bound combined command was `.venv/bin/python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_auth_account_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_admin_authorization.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_route_authorization_inventory.py`: **PASS — 321 passed in 4.15s**, with no skip, xfail, source-text-only substitute, or network dependency.

| Finding | Adversarial reproduction and legitimate positive | Redacted representative outcome |
| --- | --- | --- |
| CR-01 existing-account adoption | Provider-only public, provider-only privileged, altered-role, and altered-subject registration attempts return the same safe action before command/profile/binding/group/relationship mutation; exact interrupted student and parent commands resume | `email_already_registered` tells the caller to sign in or reset; provider subject, account class, email, and provider canaries are absent |
| CR-02 duplicate grant IDs | Same-ID grants in two capability/scope lineages are revoked by full coordinate in either inventory order; audit-failure replay, account restore, stale action, and fresh manager-approved regrant controls pass | Two distinct redacted removal action/evidence identities persist; neither historical lineage becomes current after restore |
| WR-01 typed administrator targets | Scalar exact-scope allow/wrong-scope deny and registered collection all-of tests cover first-allowed/later-denied, reversed order, duplicate/mixed students, delimiter-shaped coordinates, resolver reads, and later audit failure before the first business effect | Each concrete target receives a distinct keyed fingerprint; raw parent, student, report, job, fixture, and delimiter-shaped values are absent |
| WR-02 password recovery enumeration | Forgot-password success/unknown/disabled/not-authorized cases expose exactly `{status: accepted}`; reset unknown/bad/expired/disabled/not-authorized proofs expose one structured recovery action; valid initiation and valid reset remain functional | No delivery destination, local role/state, provider diagnostic, legacy `detail`, token, or email canary is returned |
| WR-03 resend command bypass | Already-confirmed resend loads the immutable command, selects the command user profile, verifies the provider subject, and completes exact reconciliation; duplicate-email selection is rejected; legitimate convergence reaches active | The email index cannot select authority; public output contains only bounded verification/activation state and no raw subject |
| WR-04 weak audit keyring | Weak, short, repeated, placeholder, malformed, duplicate-ID, and duplicate-material active/retained keys fail before table/fingerprint effects; a unique strong active/retained rotation writes and recognizes replay | Errors expose only `authorization_audit_key_*` categories; submitted key material and key canaries are absent |

The corrected collection invariant is whole-command: canonical targets are sorted and deduplicated, all decisions are computed before evidence writes, every allow is durably evidenced before the endpoint executes, and a later denial or later audit failure releases no handler/service mutation. `69da803` and `f80e23f` additionally pin recovery preview ordering to target-read → authorization/evidence → business read/effect. Reference-only reason, note, release-evidence, break-glass, fixture-name, preview-token, and result-filter fields never create target authority.

## Historical G-01 through G-05 closure (Plans 11–16)

The combined reproduction command was `uv run python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py`: **PASS — 114 passed in 1.75s, with zero skips and zero xfails**.

| Gap | Local result and positive control | Redacted representative outcome |
| --- | --- | --- |
| G-01 stable public identity binding | PASS — student and parent register/confirm/login resolve the token subject to one fresh Actor; duplicate-email, subject mismatch, partial retry, binding conflict, and revoked-account negatives pass | Success projects only the bound local account; conflict returns a stable safe code and correlation reference, never provider subject, email, token, or profile canary |
| G-02 privileged grant quarantine | PASS — every non-exact privileged classification removes the current grant pointer; restore/replay cannot revive historical grants; an exact approved active identity remains authorized | Evidence uses generation/version state and redacted identity fingerprints; no raw grant, subject, group, or account identifier is projected |
| G-03 recursive route identifiers | PASS — dependency, Pydantic, `Annotated`, union/container mutations and all 11 real sensitive-route controls are classified; compatible legitimate executable policies remain green | Inventory records bounded field/resource classifications only; injected student/event/token/content canaries do not appear in checked metadata |
| G-04 durable authorization audit | PASS — deny, probe, relationship-sensitive allow, admin capability, and break-glass decisions persist; legitimate allows reach handlers only with working mandatory evidence; outage controls deny/fail closed before effects | Rows contain keyed actor/resource fingerprints, bounded result/action/purpose, server correlation, and no raw resource, student, owner, email, content, object key, or key material |
| G-05 public provider error boundary | PASS — unknown-provider canaries across all eight public operations return the closed safe contract; known actionable cases and successful controls remain valid | Public result is only stable `code`, actionable `message`, and server-owned `correlationId`; provider code/message/operation, email, token, and pool canaries are absent |

These tests do not modify or claim closure of the teacher takeover read/write race. Atomic question/session/notification convergence remains Phase 475/V9DATA-02.

## Exact automated commands and results

| UTC | Exact command | Result |
| --- | --- | --- |
| 2026-07-15T18:20:13Z | `.venv/bin/python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_auth_account_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_admin_authorization.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_route_authorization_inventory.py` | PASS — 321 passed in 4.15s; six findings plus legitimate positives, zero skips/xfails |
| 2026-07-15T18:20:24Z | `.venv/bin/python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 610 passed in 9.70s |
| 2026-07-15T18:20:42Z | Both generator `--check` commands, `scripts/check_teacher_terminology.py --root . --allowlist docs/security/tutor-term-allowlist.json`, then `pytest -q tests/test_teacher_terminology_gate.py` | PASS — artifact digests above; 13 exact negative/historical occurrences consumed; terminology module 10 passed |
| 2026-07-15T18:20:48Z | `.venv/bin/python -m pytest -p no:terminal --junitxml=/tmp/phase472-plan22-final.xml` | OBSERVED RED — 1106 tests in 34.529s: 1083 passed, 23 failed, zero errors/skips; exact Phase 474-owned delta below |
| 2026-07-15T14:15:19Z | `uv run python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py` | PASS — 114 passed in 1.75s; no skips/xfails |
| 2026-07-15T14:15:22Z | `uv run python -m pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_client_error_actions.py tests/test_teacher_onboarding.py tests/test_teacher_terminology_gate.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_public_identity_lifecycle.py tests/test_notifications.py tests/test_websocket_notifications.py tests/test_admin_authorization.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` | PASS — 546 passed in 10.22s |
| 2026-07-15T14:15:33Z | `uv run python scripts/generate_route_authorization_inventory.py --check` and `uv run python scripts/generate_client_error_actions.py --check` after the prior double-generation byte comparisons | PASS — both checked; SHA-256 values above |
| 2026-07-15T14:15:33Z | `uv run python scripts/check_teacher_terminology.py --allowlist docs/security/tutor-term-allowlist.json` | PASS — 13 exact negative/historical occurrences consumed; the mutation/contract module separately reports 10 passed |
| 2026-07-15T14:15:43Z | `uv run python -m pytest -q --tb=short` | OBSERVED RED — 1019 passed, 23 failed in 35.78s; zero delta from the accepted Phase 474-owned baseline |
| 2026-07-15T14:14:51Z | `uv run python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_auth_security.py tests/test_teacher_onboarding.py tests/test_identity_authorization.py -k 'client or binding or invitation or suspension or rotation'` | PASS — 18 passed, 65 deselected in 0.33s; deterministic local substitute only |
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

The pre-Plan-10 baseline was 903 passed and 33 failed. The accepted pre-Plan-16 gap-closure baseline was 1019 passed and 23 failed. The source-bound Plan 22 observation is **1083 passed and 23 failed** across 1106 tests; the increased pass count is the added Phase 472 closure coverage and the failure delta remains zero. All remaining failures are strict production-configuration fixtures in `test_external_activation_smoke.py` (2), `test_report_service.py` (3), and `test_subscription_operations.py` (18); they fail while constructing production `Settings` without the now-required Cognito issuer/access-client allowlists. They are assigned to Phase 474 and were not edited, weakened, reassigned, or represented as Phase 472 success.

Exact Phase 474-owned failure set:

- `tests/test_external_activation_smoke.py`: `test_payment_auth_smoke_blocks_missing_provider_and_cognito_config`; `test_production_readiness_smoke_lists_read_only_release_checks`.
- `tests/test_report_service.py`: `test_report_artifacts_bucket_rejects_production_placeholder`; `test_report_artifacts_bucket_rejects_blank_production_value`; `test_report_artifacts_bucket_returns_trimmed_cdk_value_in_production`.
- `tests/test_subscription_operations.py`: `test_production_checkout_requires_explicit_live_enablement`; `test_live_checkout_includes_twint_when_capability_is_confirmed`; `test_production_checkout_reports_missing_live_configuration`; `test_admin_provider_readiness_reports_missing_production_config`; `test_admin_provider_readiness_rejects_test_key_in_production`; `test_admin_provider_readiness_reports_twint_pending`; `test_admin_provider_readiness_redacts_provider_failures`; `test_admin_provider_readiness_reports_live_success`; `test_admin_can_execute_direct_refund_and_export_finance_handoff`; `test_admin_direct_refund_requires_eligible_billing`; `test_admin_direct_refund_replays_duplicate_idempotency_key`; `test_admin_direct_refund_provider_failure_does_not_mutate_billing`; `test_admin_direct_refund_blocks_expired_twint_window`; `test_admin_rollout_controls_default_from_static_config`; `test_admin_can_update_checkout_and_refund_rollout_controls`; `test_rollout_checkout_rollback_blocks_new_live_checkout`; `test_rollout_refund_rollback_blocks_new_refund_but_preserves_export`; `test_provider_readiness_reports_webhook_last_observed_event`.

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
