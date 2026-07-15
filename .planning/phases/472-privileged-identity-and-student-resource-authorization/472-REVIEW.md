---
phase: 472-privileged-identity-and-student-resource-authorization
reviewed: 2026-07-15T14:25:52Z
status: issues_found
depth: standard
files_reviewed: 91
findings:
  critical: 2
  warning: 4
  info: 0
  total: 6
---

# Phase 472 Final Code Review

## Summary

The final review re-adjudicated the 91 deduplicated `key-files` entries named by Plans 01–16 (88 non-planning implementation/test/contract files plus the three planning-linked evidence entries) and traced the new gap-closure paths across their production call chains. The focused gap suite passes (`114 passed`), and the prior findings for stable token-bound login, conflicted-identity grant quarantine, recursive dependency identifiers, durable authorization decisions, provider-code redaction, and email-profile fallback are materially implemented.

Phase 472 still has two release-blocking edge cases. First, an unauthenticated caller can adopt an already-existing Cognito email into a new public identity command without proving control of that account. Second, reconciliation cannot reliably revoke two current grants that reuse the same `grant_id`, so one grant can survive conflict quarantine and revive after the separately supported account restore path. Four warnings remain around body-only admin targets, public recovery enumeration, bypassing the resumable confirmation command from the resend endpoint, and insufficient audit-key strength validation.

The teacher takeover/session/notification race remains a real issue, but Plans 16 and the evidence correctly leave it to Phase 475/V9DATA-02. It is not counted as a Phase 472 finding and must not be represented as closed here.

## Critical Findings

### CR-01: `UsernameExistsException` lets an unauthenticated caller create the first local command and binding for an existing Cognito account

**Files:** `src/stoa/routers/auth.py:381-395`, `src/stoa/routers/auth.py:428-468`, `src/stoa/services/public_identity_service.py:135-180`

When public registration receives `UsernameExistsException`, the route performs an administrator lookup by the caller-supplied email, accepts the returned subject, and continues exactly as if this request had created the Cognito account. There is no requirement that a matching public identity command already exist and no password, confirmation-code, or authenticated-subject proof before `start_or_resume_public_registration()` creates the command, pending profile, canonical binding, and public Cognito group.

An attacker who knows an existing Cognito email can therefore choose its local public role/profile data and attach relationship inputs to its provider subject. Against a pre-existing teacher/admin Cognito user without a local binding, this can also bind the privileged provider subject to an attacker-selected student/parent profile and add a second group, causing identity quarantine/denial. The attacker does not receive the victim's token, but they can corrupt identity ownership and availability before the account owner authenticates.

**Required fix:** Treat `UsernameExistsException` as resumable only when an immutable command already exists and its subject/role fingerprint matches. Otherwise return the enumeration-safe existing-account action and require proof of account control (login or confirmation/recovery ceremony) before creating any profile, binding, group, or relationship input. Add endpoint tests for an existing provider-only public account and an existing privileged provider account, asserting zero local/provider mutation.

### CR-02: Conflict quarantine identifies grants only by `grant_id`, so duplicate IDs across scopes leave authority behind

**Files:** `src/stoa/security/reconciliation.py:253-268`, `src/stoa/security/reconciliation.py:305-327`, `src/stoa/db/repositories/capability_repo.py:62-75`, `src/stoa/db/repositories/capability_repo.py:129-172`

Capability history keys include capability, scope hash, generation, `grant_id`, and version, so the repository permits the same caller-supplied `grant_id` in multiple capability/scope lineages. Reconciliation, however, emits `remove_grant` actions whose only target is `grant.grant_id`, then resolves each action with `next(... if grant.grant_id == action.target)`. For two active grants sharing an ID, both actions select the first snapshot. The first revocation succeeds; the second attempts to revoke the already-revoked pointer with a different action ID and aborts, leaving the other current grant active.

The account/group tightening performed earlier prevents immediate use, but `privileged_identity_service._restore_admin()` can later restore the account and provider group without checking for residual current grants. The surviving grant then becomes effective again, recreating the exact non-revival defect this gap plan intended to close.

**Required fix:** Carry an immutable full grant coordinate in every action (`capability`, `scope`, `generation`, `version`, and `grant_id`) and resolve by that coordinate, never by grant ID alone. Add a reproduction with two active current grants sharing one ID across different scopes/capabilities, apply the plan, restore the account, and prove that neither old lineage authorizes.

## Warnings

### WR-01: Body-only admin targets are authorized and audited as `global` instead of the affected resource

**Files:** `src/stoa/security/admin_authorization.py:177-232`, `src/stoa/routers/admin.py:2015-2035`

`_target()` reads only `request.query_params` and `request.path_params`. Several sensitive admin mutations carry their target solely in a Pydantic body; for example, parent-binding repair mutates `body.parent_id` and `body.student_id` while the declared admin policy names both target keys. The authorization gateway therefore constructs `resource_id="global"` and `student_id=actor.user_id`, evaluates scope against the wrong target, and persists a fingerprint that cannot distinguish the affected parent/student pair.

This makes exact target-scoped grants unusable and lets all body targets under a global grant collapse to indistinguishable audit identities. Parse the validated body target through an explicit dependency/typed handoff (without arbitrary raw-body inference), and include it in both capability scope evaluation and the HMAC resource identity. Add body-only positive/negative scope tests and two-target audit-fingerprint controls.

### WR-02: Password-recovery responses remain public account and state enumeration oracles

**Files:** `src/stoa/routers/auth.py:740-764`, `src/stoa/routers/auth.py:767-792`, `src/stoa/security/public_auth_errors.py:52-91`

`forgot_password()` returns `{"status":"accepted","delivery":null}` for an unknown local email but returns Cognito delivery details for a known public account. A known disabled account maps to `account_disabled` while an unknown account stays accepted, and `_approved_public_registration_role()` produces a distinct conflict for non-public profiles. `reset_password()` similarly returns a plain local "Invalid password reset request" before contacting Cognito for unknown emails but structured provider-derived outcomes for known ones.

These differences disclose whether an email exists and whether it belongs to a disabled or non-public account even though the route explicitly claims not to expose account existence. Return one indistinguishable accepted projection for forgot-password initiation and one operation-safe reset failure independent of the local lookup result; do not return delivery destination metadata. Add known/unknown/disabled/privileged equivalence tests.

### WR-03: Verification resend can activate an arbitrary email-GSI profile outside the resumable identity command

**Files:** `src/stoa/routers/auth.py:533-600`, `src/stoa/services/public_identity_service.py:190-256`, `src/stoa/services/public_identity_service.py:78-118`

When Cognito says a user is already confirmed, the resend route directly applies `verified_fields()` to the profile selected by `get_user_by_email()` and returns `already_verified`. It does not load the immutable public identity command, verify its subject, complete missing binding/group steps, or mark command activation. Login/refresh later require an active profile and stable binding but do not consult `activation_complete`, so a matching binding/group can produce an Actor even while the durable command is incomplete; a duplicate-email GSI row can also be activated incorrectly.

Route all already-confirmed recovery through `provider_identity()` plus `confirm_and_reconcile_public_identity()`, and preserve non-active state until the command's exact subject, binding, group, verification, and activation steps converge. Replace the existing test that blesses direct local repair with command-aware partial-failure and duplicate-email tests.

### WR-04: Production accepts arbitrarily weak HMAC audit secrets

**Files:** `src/stoa/config.py:53-60`, `src/stoa/config.py:106-121`, `src/stoa/db/repositories/security_audit_repo.py:174-196`

Production validation rejects an empty or exact development placeholder secret, but accepts a one-character replacement secret and equally weak previous keys. Because resource and actor privacy relies on keyed fingerprints, a low-entropy configured secret makes offline guessing feasible to anyone who can read audit rows and knows likely resource identifiers.

Require high-entropy secret material (for example, decoded 256-bit random keys), validate active and retained keys uniformly, reject duplicate key material/IDs, and test short/predictable production secrets. Avoid measuring strength only by string inequality with the development default.

## Re-adjudication of Previous Findings

- **Stable public binding and subject-bound login:** Implemented for normal register/confirm/login/refresh flow. CR-01 and WR-03 cover the remaining recovery edge cases.
- **Conflicted identity grant non-revival:** The normal full-coordinate case is implemented with current pointers and immutable revisions; CR-02 is a remaining collision case that can still revive authority.
- **Recursive dependency identifiers:** Implemented with cycle-safe dependency and annotation traversal; no actionable bypass found in the reviewed registered graph.
- **Durable authorization decision/probe persistence:** Central, direct, operator, and admin decision paths now use the gateway; mandatory allows fail closed and denial outages preserve denial as explicitly planned. WR-01 concerns incorrect admin target identity, not missing gateway wiring.
- **Safe Cognito errors:** All reviewed Cognito `ClientError` fallbacks use the closed provider mapping and no raw provider code/message reaches clients. WR-02 covers semantic enumeration rather than provider-string leakage.
- **Email profile fallback removal from login/refresh:** Implemented. Token-returning responses resolve through verified issuer/subject and `Actor.user_id`.
- **Teacher takeover race:** Still open and correctly owned by Phase 475; Phase 472 evidence does not claim otherwise.

## Verification Observation

`pytest -q tests/test_public_identity_lifecycle.py tests/test_privileged_identity_reconciliation.py tests/test_authorization_audit.py tests/test_public_auth_error_boundary.py tests/test_route_authorization_inventory.py` completed with **114 passed**. This confirms the documented focused evidence but does not exercise the adversarial cases above. The recorded full-suite result remains **1019 passed / 23 Phase-474-owned strict Settings fixture failures**, with external Cognito sandbox checks not run and no AWS/network/production writes.

---

_Reviewer: gsd-code-reviewer_  
_Depth: standard_
