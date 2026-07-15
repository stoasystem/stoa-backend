---
phase: 472-privileged-identity-and-student-resource-authorization
verified_at: 2026-07-15T15:20:00Z
status: gaps_found
verifier: gsd-verifier
requirements:
  total: 8
  passed: 3
  gaps: 5
  human_evidence_pending: 6
review_findings:
  reproduced: 6
  phase_owned_blockers: 6
  deferred_to_phase_475: 0
---

# Phase 472 Final Verification

## Goal Verdict

**Status: `gaps_found`.** Plans 01–16 materially close the original obvious public privileged-role selector, implement strict token/Actor resolution, centralize route authorization, and add durable decision evidence. The independent 114-test gap gate and 546-test Phase 472 gate both pass. Those green gates are not sufficient to declare the phase goal achieved: all six findings in the final code review are reproducible against current production code, and each crosses a Phase 472-owned locked identity, authorization, safe-error, or redacted-evidence boundary.

The two most severe defects are directly reachable. An unauthenticated registration request can adopt an existing Cognito account's subject after `UsernameExistsException` and create its first local public identity command/binding/group without proving account control. Separately, conflict reconciliation identifies removal actions only by `grant_id`, so two current grants sharing an ID resolve to the same first snapshot and one lineage can remain live for later account restoration. Body-only administrator targets, password-recovery enumeration, resend-by-email activation, and weak production audit secrets are also real rather than review-only concerns.

Teacher takeover/session/notification atomicity remains explicitly owned by Phase 475/V9DATA-02 and is not counted as a Phase 472 gap. The six findings below are distinct from that deferred transaction boundary.

## Independent Automated Evidence

| Verification | Result |
| --- | --- |
| `.venv/bin/python -m pytest -q tests/test_public_identity_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_route_authorization_inventory.py` | **114 passed in 1.70s**; no skips or xfails |
| Extended Phase 472 command from `472-VALIDATION.md` | **546 passed in 9.82s** |
| Duplicate-grant direct probe | Planner emitted two `remove_grant("same")` actions; apply resolved both to `admin_identity_manager/global`, never the second `student_content_review/student:s-2` grant |
| Existing-account registration direct HTTP probe | `POST /auth/register` returned **201** and invoked `start_or_resume_public_registration(subject="priv-sub", role="student")` after provider `UsernameExistsException`, without a pre-existing command or proof of control |
| Password-recovery equivalence probe | Forgot-password unknown returned `delivery: null`, while known returned a masked delivery destination; reset unknown returned legacy `{"detail": ...}`, while known/bad-code returned structured `{code,message,correlationId}` |
| Resend convergence probe | Provider `already confirmed` updated the email-GSI-selected user to verified and returned `already_verified`; command lookup/reconciliation calls were **zero** |
| Admin body-target probe | Policy declared `parent_id,student_id`, but `_target()` resolved `("global", "admin-1")` while the mutation body targeted a different parent/student pair |
| Production key probe | `Settings(environment="production", ..., authorization_audit_active_key="x")` was accepted |

The execution evidence records the final full suite as **1019 passed / 23 failed**. It is not green. The remaining exact failure set is the previously accepted Phase 474-owned strict production `Settings` fixture boundary: 2 external activation, 3 report, and 18 subscription tests. The zero Phase 472 regression delta is useful evidence but does not excuse the independently reproduced gaps above.

## Requirement Verification

| Requirement | Result | Actual-code evidence |
| --- | --- | --- |
| V9AUTH-01 | PASS | Public role validation remains limited to `student|parent`; privileged, historical, case, and unknown inputs are rejected before provider mutation. The existing-subject adoption defect is accounted under V9AUTH-04 because it bypasses identity ownership/convergence rather than accepting a privileged payload role. |
| V9AUTH-02 | PASS | Routine administrator lifecycle remains authenticated, capability-gated, versioned, and audited; the bootstrap path stays separately controlled. No reviewed finding creates a long-lived admin directly. |
| V9AUTH-03 | PASS | Teacher activation still requires exact-version approval and bound one-time invitation consumption; role alone does not grant curriculum authority. Live provider convergence remains an external NOT RUN item. |
| V9AUTH-04 | **GAP** | Existing-provider registration creates a first command/binding/group without proof (`auth.py:381-395,458-468`; `public_identity_service.py:121-180`); resend mutates an email-selected profile outside the immutable command (`auth.py:533-600`); duplicate grant IDs prevent exact all-lineage quarantine (`reconciliation.py:253-268,305-327`). These violate D-18, D-19, D-23, and D-24. |
| V9AUTH-05 | **GAP** | Issuer/client/use/signature/key-cache token validation passes, and raw Cognito diagnostics are redacted. However, password-recovery paths still expose account/state differences and one unstructured error (`auth.py:740-792`), violating the stable redacted authentication-error and existence-hiding contract in D-28/D-29 and Plan 15. |
| V9ACCESS-01 | **GAP** | A central policy and recording gateway exist, but a body-only admin mutation is evaluated against `global/admin-1` instead of its affected parent/student (`admin_authorization.py:177-232`; `admin.py:2015-2037`). The policy therefore does not decide the actual resource named by the request. |
| V9ACCESS-02 | **GAP** | Registered inventory is deterministic at 219/219, but `/admin/parent-bindings/repair` accepts resource identifiers in its body while the executable admin dependency ignores them. Calling central policy with a fabricated global target does not satisfy D-16's identifier-to-resource policy requirement. |
| V9ACCESS-03 | **GAP** | The existing matrix passes for covered resource shapes, but it lacks body-only exact-scope negative/positive controls and therefore cannot prove unrelated body targets are denied. The direct probe demonstrates the missing matrix case. |

## Locked Decision Accounting

All 33 decisions in `472-CONTEXT.md` were traced to plans, implementation, tests, or a finding. Twenty-four are satisfied by current automated evidence. Nine remain violated by the reproduced findings: **D-12, D-16, D-18, D-19, D-23, D-24, D-28, D-29, and D-32**. Exactly-one-role behavior (D-20), canonical `teacher` terminology (D-22), hidden unrelated resources (D-27), bounded JWKS behavior (D-30), client retry bounds (D-31), and fail-closed dependency behavior (D-33) remain green in the focused gates.

## Final Review Finding Adjudication

### CR-01 — Existing Cognito account can be adopted by unauthenticated registration

**Confirmed; Phase 472 blocker.** `register()` catches `UsernameExistsException`, performs administrator subject lookup, and continues into profile construction and `start_or_resume_public_registration()` (`src/stoa/routers/auth.py:381-395,428-468`). The service creates a command before checking for an existing matching command, then creates the pending profile, binding, and public group (`src/stoa/services/public_identity_service.py:135-180`). The direct HTTP probe returned 201 and handed the existing `priv-sub` to a new student command. This violates D-18/D-19 and Plan 11's explicit “resume only an existing identical command” control. It is not Phase 475 transaction work.

**Required closure:** On `UsernameExistsException`, load and require an existing immutable command whose issuer/subject/user/role fingerprint matches before any local or provider mutation. If none exists, return one enumeration-safe existing-account action and require login/confirmation/recovery proof. Add zero-mutation tests for existing provider-only public and privileged accounts, plus legitimate interrupted-command resume tests.

### CR-02 — Duplicate grant IDs do not revoke every current lineage

**Confirmed; Phase 472 blocker.** Capability storage keys grant history by capability, scope hash, generation, grant ID, and version (`src/stoa/db/repositories/capability_repo.py:62-75`), so the same ID is legal across lineages. Reconciliation discards that coordinate and stores only `grant.grant_id` in an action (`src/stoa/security/reconciliation.py:260-261`), then resolves with the first matching ID (`:321-323`). The direct probe produced two actions but passed the same first global grant to the adapter twice. The concrete second revocation will encounter a stale/already-revoked pointer while the other current pointer survives; `_restore_admin()` restores account/group without proving all prior lineages revoked (`src/stoa/services/privileged_identity_service.py:205-225`). This directly violates Plan 12's “every current grant” must-have and D-23/D-24 non-revival rule.

**Required closure:** Put the full immutable coordinate on every action (`capability`, exact scope or safe coordinate, generation, grant ID, version) and resolve exact equality. Add two same-ID/different-scope or capability current grants, apply/replay/audit-failure controls, restore the account, and prove neither lineage authorizes.

### WR-01 — Body-only admin targets authorize and audit as global

**Confirmed; Phase 472 blocker despite warning severity.** The parent-binding policy declares both target keys (`src/stoa/security/admin_authorization.py:119-123`), but `_target()` reads only query/path values and defaults to `global` plus the actor ID (`:177-232`). The mutation consumes `body.parent_id` and `body.student_id` (`src/stoa/routers/admin.py:2015-2037`). The direct probe reproduced `("global", "admin-1")`. This breaks V9ACCESS-01/02/03, D-12/D-16, and D-32 because authorization scope and durable resource fingerprint do not identify the affected resource.

**Required closure:** Pass validated typed body targets explicitly into the admin authorization dependency/gateway; do not infer arbitrary raw JSON. Use the same canonical target for capability scope and audit HMAC material. Add exact-scope allow, wrong-scope deny-before-effect, two-body-target distinct-fingerprint, and outage tests for every body-only identifier-bearing admin route.

### WR-02 — Password recovery enumerates account and lifecycle state

**Confirmed; Phase 472 blocker.** Unknown forgot-password returns accepted with no delivery while a known public account returns provider delivery metadata (`src/stoa/routers/auth.py:748-764`). Unknown reset exits locally with a legacy detail body, while a known account reaches provider normalization (`:775-792`). Disabled/non-public local profiles can also produce distinct outcomes through `_approved_public_registration_role()`. The direct probe reproduced both differences. Plan 15 explicitly requires preserving account-existence hiding across forgot/reset flows, and D-28/D-29 require one stable safe actionable projection.

**Required closure:** Make forgot-password initiation indistinguishable for unknown, known, disabled, and privileged emails and omit delivery destination metadata. Normalize reset failure shape/action without local-existence divergence. Add equivalence matrices for status, body keys/message class, headers, provider-call observability, and no local/provider diagnostic leakage.

### WR-03 — Resend bypasses the immutable public identity command

**Confirmed; Phase 472 blocker.** Resend chooses a profile via email GSI (`src/stoa/routers/auth.py:533`), and an “already confirmed” provider response applies `verified_fields()` directly to that user (`:565-580`). It never calls `require_public_identity_command()` or `confirm_and_reconcile_public_identity()`. The direct probe activated `email-gsi-selected` with zero command calls. This violates D-18/D-19 and Plan 11's immutable subject-bound convergence guarantee even if protected Actor resolution later fails closed.

**Required closure:** Route already-confirmed resend through provider identity plus exact command-aware reconciliation. Do not mark any profile verified/active before exact subject, binding, canonical group, provenance, and command activation converge. Add duplicate-email, missing-command, subject-mismatch, partial-step retry, and legitimate already-confirmed tests.

### WR-04 — Production accepts weak audit HMAC secrets

**Confirmed; Phase 472 blocker despite warning severity.** Production validation rejects only empty material or the exact development placeholder (`src/stoa/config.py:106-115`); it accepted the one-character key `x`. Because Phase 472 claims durable *redacted* actor/resource evidence, trivially guessable keyed fingerprints do not meet the D-32 privacy boundary or Plan 14's dedicated production keyring guarantee.

**Required closure:** Require uniformly strong active and previous keys (for example decoded 32-byte random material), reject malformed/predictable/duplicate secrets and duplicate normalized key IDs, and keep key contents out of errors/logs. Add production Settings tests for one-character, repeated, placeholder-like, duplicate active/previous, valid rotation, and development-only fixture behavior.

## External And Cross-Phase Limitations

- Six Cognito sandbox checks remain **NOT RUN — approval/configuration unavailable**: client/group inventory, real allowed-vs-wrong client tokens, teacher invitation activation/replay, old-token suspension, live JWKS rotation, and provider-shaped reconciliation. Deterministic local substitutes passed, but beta/production rollout cannot treat these rows as evidence.
- No AWS, network, Cognito sandbox, provider, or production mutation was performed during verification.
- The full suite remains red at 1019/23 with the exact Phase 474-owned strict Settings fixture set. Phase 474 ownership is preserved; this report does not call the suite green.
- Teacher takeover/session/notification atomicity remains Phase 475/V9DATA-02. None of the six phase-owned findings above depends on absorbing that work into Phase 472.

## Plan-Ready Gap Closure

1. **Identity ownership (V9AUTH-04):** close CR-01 and WR-03 together around immutable command/proof-of-control convergence; tests belong primarily in `tests/test_public_identity_lifecycle.py` and endpoint controls in `tests/test_auth_account_lifecycle.py`.
2. **Grant coordinate isolation (V9AUTH-04):** close CR-02 in reconciliation/action schema and exact repository transition; add duplicate-ID restore/non-revival tests to `tests/test_privileged_identity_reconciliation.py`.
3. **Exact admin body resource (V9ACCESS-01..03):** close WR-01 through typed target handoff, exact scope evaluation, and audit fingerprint tests in `tests/test_admin_authorization.py` and `tests/test_authorization_audit.py`.
4. **Recovery anti-enumeration (V9AUTH-05/D-28/D-29):** close WR-02 with known/unknown/disabled/privileged response equivalence in `tests/test_public_auth_error_boundary.py` and lifecycle tests.
5. **Audit key strength (D-32):** close WR-04 in production Settings/keyring validation with rotation-safe tests in `tests/test_authorization_audit.py`.
6. Rerun the 114-test gap gate, 546-test Phase 472 gate, generated-contract checks, direct adversarial probes above, and the full suite. Preserve external NOT RUN and Phase 474/475 boundaries honestly.

Phase 472 must not be marked complete until these closures pass independent verification.

## Verification Complete
