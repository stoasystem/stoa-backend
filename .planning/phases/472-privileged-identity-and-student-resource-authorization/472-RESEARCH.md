# Phase 472 Research: Privileged Identity And Student Resource Authorization

**Researched:** 2026-07-14  
**Phase:** 472  
**Requirements:** V9AUTH-01, V9AUTH-02, V9AUTH-03, V9AUTH-04, V9AUTH-05, V9ACCESS-01, V9ACCESS-02, V9ACCESS-03  
**Audit findings:** SEC-001, SEC-002, SEC-004

## Executive Summary

Phase 472 is not a small authorization patch. The two P0 findings share one root cause: STOA currently treats loosely correlated Cognito claims, profile fields, email lookups, role strings, and route-local checks as if they were one authoritative identity and authorization system. Planning should therefore establish one narrow security spine and migrate existing entry points onto it rather than adding more conditionals to `auth.py`, `deps.py`, and individual routers.

The recommended implementation order is:

1. Define canonical security contracts: one role per account, `teacher` as the only teacher term, stable internal `user_id`, explicit `(issuer, sub) -> user_id` binding, active-only accounts, versioned local capability grants, safe errors, and redacted security events.
2. Split token verification, identity resolution, and authorization. Token validation proves issuer/signature/token use/client and coarse Cognito group only. Identity resolution loads the explicit binding and current local account. Authorization evaluates actor-resource-action-purpose with fresh local relationship/assignment/capability facts. None of these request paths may mutate identity state.
3. Close public privilege creation before adding new privileged workflows. Public registration accepts a strict exact allowlist of self-service roles only. A separate public teacher application creates no Cognito teacher user/group/profile privilege. Approval creates a short-lived, single-use, same-email activation invitation; consumption is an idempotent, fail-closed state machine.
4. Add authenticated routine administrator provisioning and preserve the existing script only as separately controlled bootstrap/disaster recovery. Both paths need evidence and conflict checks, but the routine path requires an active `admin_identity_manager` grant.
5. Introduce the central policy and migrate every identifier-bearing route. Parent authorization requires matching active forward and reverse bindings and active accounts; legacy `parent_id` is never authorization. Teacher access is question/session- or assignment-scoped. Admin reads require purpose capabilities; admin role alone is insufficient.
6. Generate a route authorization inventory from FastAPI's actual registered routes and policy dependencies. A checked test must fail if any sensitive path/query/body identifier lacks an executable policy declaration or documented stricter policy.
7. Reconcile historical Cognito groups, profile roles, identity bindings, account status, `tutor` values, capabilities, and relationships in dry-run-first batches. Automation may only remove/suspend; all privilege increases require explicit approval. Deploy deny-first code before applying any group/profile changes.

The most important implementation constraint is immediate revocation. AWS documents that a revoked Cognito JWT can still pass ordinary offline signature-and-expiry verification. Therefore every protected request must load current local account/relationship/assignment/grant state; global sign-out is defense in depth, not the mechanism that guarantees immediate denial. Do not introduce cross-request authorization-decision caching.

## Current-State Findings

### Public privileged registration is directly reachable

`src/stoa/routers/auth.py` currently:

- accepts an unrestricted string `role` in its local `RegisterRequest`;
- maps `tutor` to `teacher`;
- selects a role-specific Cognito app client;
- calls `sign_up`, writes `custom:role`, and calls `admin_add_user_to_group` during public registration;
- treats teacher `pending_review` as response metadata only;
- adds the role group again during email confirmation;
- infers login/refresh clients from caller-supplied or profile role.

The audit's SEC-001 reproduction obtained 201 for `role=admin` and observed assignment to `admins`. Closing only the registration endpoint is insufficient because email confirmation also changes privilege and login/refresh still accept legacy role aliases.

### Authentication currently mutates authorization state

`src/stoa/deps.py` has one process-global, unkeyed JWKS cache that is populated once. Unknown `kid` never refreshes. `get_current_user` verifies signature/issuer/token use but does not validate access-token `client_id`. It then chooses the first recognized group, falls back to `custom:role`, falls back again through Cognito username -> email -> DynamoDB profile, maps backend `teacher` back to `tutor`, and best-effort adds the user to a Cognito group during the request.

This behavior conflicts with all of the locked identity decisions:

- multiple STOA groups are silently reduced to whichever appears first;
- email is a security identity fallback;
- a missing group can be broadened during authentication;
- there is no local active-state check;
- there is no authoritative capability record lookup;
- token `sub` is often treated as the business `user_id` even though other code demonstrates they can differ.

### Internal identity is inconsistent

Registration currently sets `user_id` to Cognito `UserSub` when available, but the production-admin script generates a separate UUID. `auth._profile_from_current_user` and `parents._resolve_parent_profile` try direct `sub` lookup and then email fallback. Numerous routes use `user["sub"]` as a student, parent, or teacher business ID. Tests explicitly model a Cognito claim sub such as `parent-claims` resolving to local `parent-local` by email.

Planning must not attempt a global primary-key rewrite to Cognito `sub`. The locked direction is an explicit unique identity binding and stable internal `user_id`. Existing records can remain keyed by their current business ID while the binding becomes the sole token-to-business-identity resolver.

### Student authorization is duplicated and over-broad

Confirmed examples:

- `students.py` permits any parent/admin for summary and learning profile and any parent/teacher/admin for question history.
- `questions.py:get_question` restricts students only; every other authenticated role can retrieve an arbitrary known question.
- `practice.py:_resolve_curriculum_student_id` allows any teacher/admin with a supplied student ID.
- `adaptive_learning_service.py:_require_student_visible` allows any teacher/admin and accepts either legacy profile `parent_id` or a formal binding.
- `parents.py` has a better formal-binding helper but falls back to scanning student profiles by legacy `parent_id` in listing and ownership checks.
- `teachers.py` exposes a broad escalated queue and only some question mutations check the assigned/takeover teacher.
- the large `admin.py` surface has many student-, parent-, report-, and account-identifier routes protected only by `require_role("admin")`.
- `tutors.py` adds a parallel `/tutors` API surface with many question/student/help-request operations.

SEC-002 is therefore a route-family problem, not three isolated functions. Route inventory and enforcement must cover direct path IDs plus identifiers resolved through query parameters, request bodies, and loaded resources such as `question_id -> student_id`, `assignment_id -> student_id`, `conversation_id -> student_id`, and `report key -> parent_id/student_id`.

### Reusable code exists, but none is authoritative enough unchanged

- `user_repo` already has forward and reverse formal parent/student rows. These are useful truth inputs, but writes are two independent `put_item` operations and readers often trust one side. Phase 472 should require both sides to agree and fail closed; Phase 475 owns transactional relationship writes and historical symmetry repair.
- `parents._get_owned_child_profile` is a useful shape for relationship checks, but its legacy scan fallback must be removed from authorization.
- question `teacher_id`, `session_id`, dispatch owner/status, and session rows provide current task-scoped facts. They should become inputs to policy rather than remain route-local checks. Phase 475 owns atomic concurrent takeover/session writes.
- `curriculum_ops_service` demonstrates named capabilities and audit events, but it currently extracts capabilities from token/profile/metadata/scopes. Phase 472 must replace that source with versioned local grants. Preserve its core rule that teacher role does not imply curriculum mutation.
- `scripts/provision_production_admin.py` has explicit production confirmation, dry-run, conflict checks, redacted password output, and focused tests. Retain it for bootstrap/disaster recovery, add durable audit evidence, active status, identity binding and capability-bounded output, and do not use it for routine administrators.
- existing FastAPI dependency overrides and fake Cognito/table fixtures are useful test scaffolding, but most tests override `get_current_user` with bare `{sub, role}` dictionaries. Introduce an Actor fixture and migrate focused tests so they exercise identity and policy boundaries instead of bypassing them.

## Recommended Architecture

### 1. Separate authentication, identity resolution, and authorization

Create small security modules rather than further expanding `src/stoa/deps.py`:

- `src/stoa/security/errors.py`: stable safe error codes and response model.
- `src/stoa/security/jwks.py`: issuer-keyed bounded JWKS cache and refresh logic.
- `src/stoa/security/tokens.py`: cryptographic and claim validation only.
- `src/stoa/security/identity.py`: resolve verified `(iss, sub)` to current local account and construct an immutable Actor.
- `src/stoa/security/authorization.py`: actor-resource-action-purpose policy and decision/evidence types.
- `src/stoa/security/route_inventory.py`: executable policy metadata extraction and inventory validation.
- `src/stoa/security/events.py`: redacted denial/security events and aggregation keys.

`src/stoa/deps.py` should keep AWS client dependencies and expose thin `get_verified_token`, `get_actor`, and compatibility `get_current_user` adapters only as needed during migration. New protected routes should depend on `Actor`, not raw JWT claims.

A useful immutable Actor contract is:

```text
Actor
  user_id            stable internal business ID
  issuer / subject   verified identity binding coordinates
  role               exactly one canonical local role
  account_status     must equal active for protected access
  cognito_group      exactly one matching STOA group
  capability_grants  current active, scoped local grant records
  auth_context       client_id, token jti/origin_jti, correlation ID (not serialized to clients)
```

Do not put raw token, email, provider payload, or arbitrary claims into authorization events. The role is valid only when the single recognized Cognito group and local profile role agree. Non-STOA Cognito groups may be ignored, but zero recognized groups, multiple recognized groups, `tutor`, or disagreement with local role is `identity_conflict`. Capabilities come only from active local grant records; token/profile lists can never broaden them.

### 2. Explicit authoritative identity bindings

Add repository operations for a unique binding keyed by normalized issuer plus subject, for example:

```text
PK = IDENTITY#{sha256(issuer)}#{sub}
SK = BINDING
entity_type = identity_binding
issuer, subject, user_id, status, created_at, created_by, version
```

Also write a reverse reference under `USER#{user_id}` for inventory, but make the identity-keyed row authoritative. Creation must use a conditional put so one external identity cannot bind to two local users. Do not resolve by email when the binding is absent. A missing binding is a recovery/conflict state, not an invitation to create one during authentication.

Migration should derive candidate mappings from existing Cognito `sub`, profile `user_id`, username/email evidence, but only automatically commit unambiguous one-to-one candidates. Ambiguous or missing evidence becomes `suspended_pending_review`. The dry-run report must never print raw tokens and should minimize email exposure.

### 3. Versioned local capability grants

Define independent grant records rather than a list on PROFILE:

```text
PK = USER#{user_id}
SK = CAPABILITY#{capability_name}#{scope_key}#{grant_id}
capability, scope_type, scope_id_or_wildcard, status
effective_at, expires_at, version
granted_by, reason, created_at, revoked_at, revoked_by
```

Recommended locked capabilities include at least:

- `teacher_identity_reviewer`
- `admin_identity_manager`
- `student_support_lookup`
- `student_support_read`
- `safety_review_read`
- `student_data_break_glass`

Curriculum capabilities should be migrated into this same authoritative store or adapted through it; do not accidentally grant them to all teachers. Grant selection requires current time, active status, matching scope, and latest non-revoked version. Revocation writes a new version/status and is visible on the next request. Request-scoped memoization is acceptable; cross-request decision caching is not.

### 4. Teacher application, approval, invitation, and activation

Keep the public application flow completely separate from `/auth/register`.

Recommended lifecycle:

```text
application version submitted (no Cognito teacher identity, no role)
  -> exact immutable version approved/rejected by active reviewer capability
  -> approval creates invitation record with random high-entropy token digest,
     normalized approved email, application/version, expiry and unconsumed state
  -> applicant verifies/uses same email and consumes invite once
  -> local identity/profile created as non-active activation_pending
  -> Cognito user/attributes/group established idempotently
  -> explicit identity binding written
  -> reconciliation confirms Cognito/local intersection
  -> local account becomes active
```

Store only a cryptographic digest of the invitation secret. Use conditional writes on invitation status/version/expiry to prevent replay and concurrent consumption. Bind invitation to normalized email and require Cognito's verified email to match exactly. Approval alone must not add a group or activate a profile.

Cognito and DynamoDB cannot participate in one transaction. Use a durable local activation state machine with idempotent steps. The safe failure posture is local non-active until both sides match. If Cognito group addition succeeds but the local final update fails, the local non-active state denies access and reconciliation can complete or remove the excess group. If the local invitation is consumed but Cognito fails, a retry with the same activation command resumes rather than creating another identity.

Application versions should be append-only. Review records reference exact application/version and record actor, timestamp, internal reason, safe evidence reference, and decision version. Full applications are readable only with `teacher_identity_reviewer`; generic admin lists expose bounded metadata only.

The full qualification-document workflow remains deferred. Application fields in this phase should be limited to ordinary contact/profile declarations and safe offline evidence references; do not add uploads, document blobs, malware scanning, retention workflows, or reviewer document UI.

### 5. Routine administrator provisioning

Add an authenticated admin identity command/service and route guarded by active actor plus `admin_identity_manager`. Treat it as a durable idempotent provisioning workflow similar to teacher activation:

1. create an immutable command with actor, target, reason and idempotency key;
2. reject any existing conflicting Cognito/profile/binding/role state;
3. create/confirm the Cognito identity and admin group;
4. create explicit identity binding and non-active local admin profile;
5. record resulting group and redacted evidence;
6. activate only after reconciliation succeeds.

Do not give the creating admin an implicit ability to grant arbitrary capabilities. Capability grants remain separate explicit actions and require policy/audit. The bootstrap script remains for first-admin and disaster recovery only; harden it with purpose/incident input, active account fields, explicit identity binding, durable audit record, idempotency, and safe output. The script must not create a permanent request-path superuser.

### 6. Central actor-resource-action-purpose authorization

Represent policy inputs as typed values, not free-form route checks:

```text
ResourceRef(type, id, student_id, parent_id?, owner_id?)
Action(read | create | update | delete | claim | reply | resolve | lookup | export ...)
Purpose(self_service | parent_learning_view | assigned_support | safety_review |
        account_support | incident_break_glass | curriculum_operation ...)
```

Policy evaluation order should be deterministic:

1. verified Actor exists;
2. actor account is currently `active` and Cognito/local role intersection is valid;
3. target resource and target student's account are current and valid where required;
4. owner student may act only on their own canonical internal `user_id`;
5. parent requires both forward and reverse formal binding rows, identical relationship/version, both `active`, and both accounts active;
6. teacher requires a current question/session authorization for that question/conversation/minimum context or a separate active scoped student-teacher assignment for broader data;
7. operator/admin requires an active purpose capability matching action/resource scope;
8. incident break-glass additionally requires an incident ID, reason, short unexpired read-only grant, notification, and independent review record;
9. otherwise deny, selecting existence-hiding `404` or known-resource `403` based on whether the actor is authorized to know the resource exists.

Policy reads must fail closed. Repository/provider inability to determine current account, binding, assignment, or grant state is `503 authorization_temporarily_unavailable`, never a cached allow. Distinguish a genuinely absent resource from an unavailable repository internally, but do not leak it to an unrelated actor.

Student self-service endpoints should derive `student_id` from Actor. If a legacy explicit path/query ID remains, compare it to `actor.user_id` and reject mismatch. Never use `sub` directly as a business resource ID after the binding layer.

Teacher queue and assistance views need special care. Before claim/assignment, expose only the minimum queue metadata necessary to choose work, with no unrestricted student profile/content. A dispatched or taken-over question authorizes that question, linked conversation/session and minimal support context only. A teacher's role or mere visibility in the queue never authorizes the student's history, adaptive profile, reports, or other questions.

### 7. Executable route inventory

Do not maintain a hand-written spreadsheet that can drift from FastAPI. Make policy declaration an executable dependency object with attached metadata, for example a factory that produces a FastAPI dependency and exposes an `AuthorizationSpec(resource_type, action, purpose, resolver)` attribute. Specific resolvers can map:

- `student_id` path/query/body -> student;
- `question_id` -> question plus owner student;
- `conversation_id` -> conversation plus owner student;
- `assignment_id` -> assignment plus owner student;
- report composite key -> report plus parent/student;
- teacher/parent/user IDs -> identity/account resource.

At application startup/test time, recursively inspect every `APIRoute.dependant` tree. A route is compliant only if its dependency tree contains an executable authorization spec or an explicit stricter-policy declaration. Project that same source into an OpenAPI vendor extension such as `x-stoa-authorization` and generate a deterministic JSON/Markdown inventory containing method, path, operation ID, resource, action, purpose, resolver and stricter-policy reason.

The checker must identify sensitive IDs in:

- path parameter names;
- query parameters and aliases (`studentId`, etc.);
- Pydantic request body fields;
- known indirect resource types (`question_id`, `conversation_id`, `assignment_id`, `report_id`, `request_id`, `parent_id`, `teacher_id`, `user_id`).

It must fail on missing declaration, unknown resource/action/purpose, duplicate route ambiguity, or metadata without the executable dependency. The inventory should cover `students`, `questions`, `practice`, `adaptive`, `parents`, `teachers`, the renamed teacher-only surface replacing `tutors`, reports, and student/account-bearing admin routes. Public auth routes and true global catalog/health routes can be explicitly classified as public/non-student rather than silently omitted.

### 8. Canonical safe failures and evidence

Use one response shape for security failures:

```json
{"code": "action_not_allowed", "message": "You cannot perform this action.", "correlationId": "..."}
```

Recommended mapping:

- 401: `token_missing`, `token_expired`, `invalid_token`
- 403: `account_not_active`, `action_not_allowed`
- 404: `resource_not_found` for unrelated actors and true not-found where indistinguishable
- 409: `identity_conflict`, `binding_conflict`, invitation already consumed where safe/actionable
- 503: `identity_provider_unavailable`, `authorization_temporarily_unavailable`

Wrong pool, wrong app client, ID token, malformed signature, unknown key, group names, missing capability names, provider response, and stack details stay in redacted internal telemetry. Add a minimal correlation-ID middleware or dependency now because D-28/D-32 require it; Phase 480 can broaden tracing/observability later.

Denial events should include internal actor ID, canonical role, resource type, action, purpose, policy version, safe result code and correlation ID. Do not log token, email, student content, S3/object key, raw resource body or provider error. Enumeration aggregation can use a keyed/hash fingerprint of target identifiers without emitting raw identifiers. Alert-worthy patterns include cross-student target spread, repeated hidden-resource probes and privileged-registration attempts.

## Cognito Access-Token And JWKS Design

AWS's current Cognito documentation states that access tokens carry `client_id` while ID tokens use `aud`; APIs accepting access tokens must validate `token_use=access`, issuer, signature, expiry and the access token's `client_id`. AWS also recommends caching keys by `kid`, refreshing periodically, and refreshing when a correct-issuer token presents an unknown `kid` because Cognito may have rotated signing keys:

- https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-tokens-verifying-a-jwt.html
- https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-access-token.html

Implement the verifier with these properties:

- derive exact allowed issuer(s) from explicit configuration, never from unverified token input;
- validate header algorithm is RS256 and `kid` is present before lookup;
- key cache entries by issuer and then `kid`, with monotonic fetched/expiry timestamps;
- validate `iss`, signature, expiry/not-before if present, `token_use=access`, and `client_id` against the configured allowed set;
- preferably require the client to be the configured client for the resolved coarse role, after group validation, so a token from an unintended app client cannot cross role surfaces;
- reject empty/duplicate production client configuration at readiness/startup rather than weakening checks;
- fetch JWKS asynchronously with explicit connect/read timeouts; the current synchronous `httpx.get` in an async dependency can block the event loop;
- on unknown `kid`, perform at most one forced refresh per request and use a lock/single-flight mechanism to prevent a rotation stampede;
- if refresh fails, a matching known key may be used only inside the configured bounded maximum cache window; an unknown key is always denied with 503 rather than 401;
- isolate issuers in cache and tests even though the current product config names one pool;
- never accept a token by decoding claims without successful signature verification.

Use dependency injection for the clock and JWKS transport so expiry/rotation/outage tests are deterministic and make no network calls.

Immediate revocation cannot rely on Cognito sign-out alone. AWS documents that revoked tokens can still verify successfully in an ordinary JWT library that checks only signature and expiration:

- https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html

Therefore suspension/revocation must update local state first (or in a deny-first state), remove the Cognito group, call `AdminUserGlobalSignOut`/equivalent, and ensure every protected request checks current local `active` status. If Cognito cleanup fails, local denial remains authoritative and reconciliation retries cleanup.

## `teacher`-Only Migration

The locked decision is stronger than alias normalization: `tutor` must disappear and new occurrences must be rejected. Current occurrences span at least `deps.py`, `auth.py`, `main.py`, `routers/tutors.py`, `teachers.py`, `adaptive.py`, `practice.py`, `admin.py`, multiple teacher/AI/curriculum/notification/websocket services, and many tests including `test_tutor_availability.py`.

Plan this as an explicit migration slice:

1. Add canonical role validation that accepts exactly lower-case `student`, `parent`, `teacher`, `admin` where those roles are appropriate; public registration accepts only the separately approved self-service subset. `tutor`, case variants and unknown values are rejected before any provider call.
2. Rename/remove `/tutors`, `routers/tutors.py`, Tutor request/response models, helper names such as `update_tutor_availability`, output values such as `roleView: tutor`, policy states such as `tutor_approved_batch`, notification recipient roles, tests and filenames. Do not leave a route alias.
3. Inventory Cognito `tutors` group if it exists, local profile values, stored events/settings/policy enums and deployed/mobile consumers. Historical `tutor` identities are conflicted/suspended until a controlled migration changes them to `teacher`; they are not interpreted as teachers at request time.
4. Generate a repository scan gate over runtime source, API/OpenAPI contracts, tests and mobile contracts. Human-language historical planning/audit documents can retain quotations, but active product contracts and persisted enumerations must not.
5. Deploy readers that reject/suspend historical `tutor` before writing migrations. Apply a dry-run migration with counts and conflicts, then remove old Cognito group membership only after target teacher state is confirmed.

The rename has compatibility impact. Because the user explicitly rejected a compatibility alias, clients calling `/tutors` or sending `tutor` should fail and must be updated in the same release candidate. Phase 477 will later repair the installable mobile foundation, but any current backend/mobile API contract fixtures that encode `tutor` need to be updated now so Phase 472 evidence is honest.

## Rollout And Reconciliation Sequence

Use a deny-first, dry-run-first sequence:

1. **Inventory only:** enumerate Cognito users/groups/clients, local profiles/statuses, identity candidates, capabilities, formal/legacy parent links, teacher assignments/sessions, `tutor` values, and sensitive routes. Produce counts and safe conflict IDs; no production mutation.
2. **Ship security primitives dark:** token verifier, Actor, repositories, policy, error/event contracts, and route inventory tests behind local/sandbox configuration. Add explicit identity bindings for test/sandbox fixtures.
3. **Close new privilege creation:** strict public allowlist and confirmation safeguards; add teacher application and authenticated admin workflows. Ensure rejected public roles cause zero Cognito/Dynamo calls.
4. **Deploy fail-closed identity resolution:** require explicit binding, exact one-role intersection and active local state. Existing unbound/conflicting privileged accounts will be denied, so bindings/reconciliation candidates must be prepared and operational owners warned before enabling in an environment.
5. **Migrate sensitive routes in bounded families:** students/questions first (the reproduced P0 paths), then practice/adaptive/parents/teachers/conversations/reports/admin. Keep the route inventory gate red until every family is classified.
6. **Dry-run privileged reconciliation:** classify safe exact matches versus unknown, multi-role, `tutor`, inactive, missing-approval and mismatched accounts. Automatic apply may remove excess groups or suspend anomalies only. Role addition, restoration or capability grants require `admin_identity_manager` approval.
7. **Apply in small checkpointed batches:** local deny/suspend first, Cognito group removals/global sign-out second, safe canonical migrations third. Every item has an idempotency key, before/after state, actor, reason and redacted evidence.
8. **Run focused regression and sandbox evidence:** old SEC-001 payloads denied with zero mutations; old SEC-002 requests hidden/denied; wrong-client/ID-token/rotation/outage cases fail closed; approved actors retain intended access.
9. **Observe before broader rollout:** aggregate denial/conflict rates, reconcile stuck activation/admin commands, and preserve rollback as code/config rollback plus continued local suspension. Never roll back by broadly restoring groups.

Production writes are not authorized by planning. Reconciliation tooling must default to dry-run and require separate explicit production approval.

## Phase Boundary Coordination

### Phase 475: transactional relationship and teacher-claim work

Phase 472 must define what relationship/assignment facts authorize and must fail closed on inconsistency. It should not absorb Phase 475's broader transaction work.

- For parent bindings, Phase 472 readers require matching active forward and reverse rows. Existing asymmetric rows deny. Phase 475 later makes writes transactional and performs full historical relationship repair.
- For teacher claims, Phase 472 policy checks the current question/session/dispatch owner and limits access accordingly. Phase 475 later makes takeover/session/notification writes atomic and concurrency-safe.
- If Phase 472 needs new scoped teacher-assignment records, define their authorization schema and safe conditional lifecycle, but leave multi-record transaction/failure-injection generalization to Phase 475.

Do not preserve unsafe access merely because a historical write can be asymmetric. Denial is the Phase 472 security contract; transactional convergence is Phase 475's correctness contract.

### Phase 474: global test and CI baseline

Phase 472 owns focused security regressions and must not wait for the global baseline because the P0s block all rollout. The current full suite is already red (12 failures in the audit), tests can instantiate real AWS clients, and Python 3.12/CI gating are Phase 474 concerns.

Therefore:

- Phase 472 focused tests must inject all AWS/network dependencies and pass without credentials/network.
- Do not claim the full suite is green as Phase 472 evidence unless it actually becomes green independently.
- Record focused commands and results now; Phase 474 will incorporate them into the deterministic full-suite and required CI gates.
- Avoid broad test-fixture/global network changes in Phase 472 unless necessary for these security tests; coordinate shared `conftest.py` changes with Phase 474.

## Concrete File Plan

### Reuse and modify

- `src/stoa/config.py` — allowed issuers/clients, JWKS TTL/max-stale/timeouts, invitation expiry, policy version; production config validation.
- `src/stoa/deps.py` — remove mutable role/email fallback behavior; delegate to new token/identity modules; keep thin dependencies.
- `src/stoa/models/user.py` — canonical one-role/account-status models; do not accept `tutor`.
- `src/stoa/routers/auth.py` — strict public registration, no privileged group writes, no `tutor` alias/display mapping, safe confirmation/login/refresh behavior.
- `src/stoa/db/repositories/user_repo.py` — identity bindings, profile active states, capability grants, bidirectional binding read validation, applications/invitations/admin commands or delegate to focused repositories.
- `src/stoa/routers/students.py`, `questions.py`, `practice.py`, `adaptive.py`, `parents.py`, `teachers.py`, `conversations.py`, `admin.py` — use Actor and executable central policy dependencies.
- `src/stoa/main.py` — remove `tutors` router; install safe error/correlation handling and OpenAPI authorization projection.
- `src/stoa/services/curriculum_ops_service.py` — source capabilities from authoritative local grants while preserving separate author/reviewer/publisher semantics.
- `src/stoa/services/teacher_dispatch_service.py`, `teacher_assistance_service.py`, `ai_teacher_tools_service.py`, `adaptive_learning_service.py`, `notification_service.py`, `websocket_service.py` — remove `tutor` terms and route any student visibility checks through policy.
- `scripts/provision_production_admin.py` — bootstrap/disaster-only audit, identity binding, active status, idempotency, purpose/incident reason and conflict-safe behavior.

### Add

- `src/stoa/security/{errors,jwks,tokens,identity,authorization,route_inventory,events}.py`
- focused repositories such as `identity_repo.py`, `capability_repo.py`, `teacher_application_repo.py`, and `security_audit_repo.py` if keeping `user_repo.py` bounded is preferable.
- `src/stoa/routers/teacher_applications.py` for public application plus reviewer/admin actions, with separate visibility contracts.
- an authenticated privileged-identity service/router for routine admin provisioning, suspension/revocation, capability management and reconciliation approval.
- `scripts/reconcile_privileged_identities.py` and a deterministic route-inventory generator; both default to dry-run/read-only.
- checked generated evidence path such as `docs/security/route-authorization-inventory.json` (or a test artifact path documented by the plan).

### Remove or rename

- `src/stoa/routers/tutors.py` and `/tutors` registration in `main.py`.
- `tests/test_tutor_availability.py` and other Tutor-named contracts, renamed to teacher equivalents.
- active runtime/test/mobile occurrences of `tutor` and plural role/group aliases.

## Risks And Planning Traps

1. **Treating Cognito global sign-out as immediate API revocation.** Offline JWT verification still accepts a revoked, unexpired token; local active-state checks on every request are mandatory.
2. **Making DynamoDB profile role the sole authority.** The locked policy is Cognito coarse group plus local role/status intersection. Neither side alone may broaden privilege.
3. **Continuing email fallback during migration.** Email can be used as evidence in an offline migration report, never as a request-time identity resolver.
4. **Leaving `tutor` as a hidden compatibility alias.** This directly violates the locked decision and masks historical conflicts.
5. **Approving a teacher by immediately adding the group.** Approval only permits issuing the bound invitation; activation follows verified one-time consumption.
6. **Caching allow decisions.** Any cross-request account/binding/assignment/grant cache undermines immediate revocation. Cache only immutable JWKS keys within strict bounds and request-local policy reads.
7. **Trusting only one side of a parent binding.** Phase 472 must deny asymmetric data even before Phase 475 repairs writes.
8. **Hand-maintaining route coverage.** Inventory must come from registered FastAPI routes and executable policy dependencies, including body/query identifiers.
9. **Giving admin role blanket read access to simplify migration.** Admin content reads require purpose capabilities; support lookup is metadata-only.
10. **Mixing P0 authorization with Phase 475 concurrency refactors or Phase 474 global CI repair.** Preserve the boundaries while providing focused deterministic tests.
11. **Returning provider/debug detail to clients.** Error messages and UI actions are safe abstractions; raw Cognito/JWKS/policy details are internal and redacted.
12. **Large-bang production migration.** Unknown and inconsistent accounts must suspend; privilege restoration is separately approved and auditable.

## Validation Architecture

### Test infrastructure

| Property | Recommendation |
| --- | --- |
| Framework | Existing `pytest>=8.2`, FastAPI `TestClient`, `pytest-asyncio`, botocore `ClientError`; moto only where repository behavior benefits from DynamoDB semantics |
| Quick command | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py` |
| Route/matrix command | `pytest -q tests/test_route_authorization_inventory.py tests/test_student_authorization_matrix.py` |
| Migration command | `pytest -q tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py` |
| Phase focused gate | `pytest -q tests/test_auth_security.py tests/test_identity_authorization.py tests/test_teacher_onboarding.py tests/test_student_authorization_matrix.py tests/test_route_authorization_inventory.py tests/test_privileged_identity_reconciliation.py tests/test_provision_production_admin.py tests/test_auth_account_lifecycle.py tests/test_parent_children.py tests/test_questions.py tests/test_teacher_dispatch.py tests/test_adaptive_learning.py tests/test_curriculum_ops.py` |
| Full suite | `pytest -q` (record existing unrelated red baseline; Phase 474 owns global green/isolation) |
| Network/AWS policy | All new tests inject clock, JWKS transport, Cognito client and repositories. No credentials or real network are allowed in focused tests. |
| Feedback target | Unit/security tests under 10 seconds; route matrix/inventory under 30 seconds; focused phase gate under 90 seconds. Measure rather than assume. |

### Wave 0 test files and fixtures

Create these before implementation so each subsequent task has an executable red test:

- `tests/security/conftest.py` or local fixtures: canonical Actor factory, identity/profile/grant/binding/assignment builders, frozen clock, fake JWKS transport, RSA test keys, fake Cognito call recorder, in-memory security repositories, correlation ID helper.
- `tests/test_auth_security.py`: public role mutation barrier and token/JWKS claim validation.
- `tests/test_identity_authorization.py`: identity binding, one-role intersection, active state, local grant authority, revocation and safe errors.
- `tests/test_teacher_onboarding.py`: immutable application/review/invitation/activation state machine.
- `tests/test_student_authorization_matrix.py`: actor-resource-action-purpose matrix across route families.
- `tests/test_route_authorization_inventory.py`: registered route coverage and deterministic OpenAPI inventory.
- `tests/test_privileged_identity_reconciliation.py`: dry-run/apply, auto-tighten-only, idempotency/checkpoint and evidence redaction.

Existing tests to extend/migrate:

- `tests/test_auth_account_lifecycle.py`
- `tests/test_parent_children.py`
- `tests/test_questions.py`
- `tests/test_teacher_dispatch.py`
- `tests/test_adaptive_learning.py`
- `tests/test_ai_teacher_tools.py`
- `tests/test_curriculum_ops.py`
- `tests/test_provision_production_admin.py`

Rename Tutor tests/contracts to Teacher and update fixtures to override `get_actor` or the new identity repositories, not just raw `get_current_user`, when the test claims to verify authorization.

### Requirement-to-test map

| Requirement | Primary automated evidence | Critical cases |
| --- | --- | --- |
| V9AUTH-01 | `test_auth_security.py` + extended account lifecycle | exact self-service allowlist; reject admin/teacher/tutor/unknown/case variants before all Cognito/Dynamo calls; confirmation cannot add privilege; login/refresh reject tutor |
| V9AUTH-02 | teacher/admin provisioning and reconciliation tests + bootstrap script tests | active `admin_identity_manager`; actor/target/time/group/redacted evidence; idempotent retry; conflicts; root not omnipotent; bootstrap/disaster-only guard |
| V9AUTH-03 | `test_teacher_onboarding.py` | public application creates zero privilege; immutable versions; exact reviewer capability; approval does not elevate; expiry; replay/concurrency; same verified email; resumable provider failure; teacher lacks curriculum capability |
| V9AUTH-04 | `test_identity_authorization.py` + reconciliation tests | explicit `(issuer,sub)` binding; no email fallback; zero/multiple/mismatched groups; local role/status mismatch; only active; local grants authoritative; request path makes zero Cognito mutations; auto-tighten/manual-elevate |
| V9AUTH-05 | `test_auth_security.py` | valid access token; wrong issuer/pool; wrong client; ID token; expired/malformed token; per-issuer cache isolation; known-key bounded outage; unknown-kid single refresh; rotated key success; refresh outage -> 503; redacted errors; no sync network |
| V9ACCESS-01 | `test_identity_authorization.py` | owner; active bidirectional parent; assigned/task-scoped teacher; scoped operator/admin; support metadata lookup; break-glass limits; immediate revocation; store outage fail closed |
| V9ACCESS-02 | `test_route_authorization_inventory.py` | every registered sensitive path/query/body ID has executable spec or stricter policy; OpenAPI projection matches dependency; removed `/tutors`; unknown declaration fails |
| V9ACCESS-03 | `test_student_authorization_matrix.py` | unrelated parent, legacy-only parent_id, pending/revoked/asymmetric binding, inactive actor/target, unassigned/stale/other teacher, admin without capability, known-vs-hidden resource, authorized positive controls across every family |

### Security matrix dimensions

Generate cases, do not hand-copy one test per route. At minimum cross these dimensions:

- actors: unauthenticated, owner student, other student, active bound parent, unrelated parent, pending/revoked/asymmetric parent, assigned teacher, dispatched teacher, unassigned/other/suspended teacher, admin/operator with and without exact capability, break-glass holder, identity-conflicted actor;
- resources: student profile/summary/questions, question, conversation/session, practice/progress/mistakes, adaptive memory/assignment, parent-child/report, teacher queue/assistance, admin usage/account/report actions;
- actions: read, list, create, mutate, claim, reply, resolve, export;
- states: exists/missing, actor active/inactive, target active/inactive, relationship active/stale/revoked/asymmetric, assignment current/stale/revoked, capability current/expired/revoked/wrong scope, authorization store available/unavailable;
- expected result: allow, 401, 403, existence-hiding 404, recoverable 409, dependency 503, plus safe structured body and security-event assertion.

Every route-family case must include a positive control so blanket-deny cannot make the suite pass.

### Threat-focused tests

- Privileged role strings with whitespace, Unicode/case variants, plural names, `tutor`, nested/extra fields, confirmation replay and provider partial failures.
- Two concurrent invitation consumers: exactly one succeeds; loser receives stable conflict; no duplicate identity/group/binding.
- Tokens with valid signature but wrong client, wrong issuer, wrong token use, unknown `kid`, rotated keys, duplicate/multiple STOA groups and `tutor` group.
- Authorization repository throws/timeouts: protected access returns 503 and no handler mutation occurs.
- Revoked account/binding/assignment/grant with still-valid old token: next request denies.
- Resource enumeration: unrelated real ID and random missing ID are indistinguishable; no content/existence in body/log.
- Security-event redaction: seed token, email, content, object key and provider text as canaries and assert none appears in response/log/audit record.
- Route inventory mutation test: add a synthetic sensitive route without policy and prove the checker fails.

### Manual/sandbox evidence

Automated local tests are primary. The following require separately approved, non-production Cognito sandbox/read-only evidence:

1. inventory actual configured user-pool app clients and groups without printing secrets;
2. show an access token from an allowed sandbox client succeeds and a different same-pool client fails;
3. demonstrate approved teacher invitation activation creates exactly one canonical teacher group/profile/binding and replay fails;
4. demonstrate suspension removes group/global session and the backend immediately denies an old token due to local state;
5. exercise JWKS rotation if the sandbox can safely support it, otherwise retain deterministic local two-key rotation tests and record the limitation;
6. run privileged reconciliation in dry-run only unless explicit production mutation approval is separately granted.

### Nyquist sampling and sign-off

- After each task commit: run the smallest new/changed test file plus direct existing regression file.
- After each plan wave: run the phase focused gate.
- Before Phase 472 verification: run all focused commands, generate/compare the route inventory, run the repository `tutor` contract scan, and record full-suite status without hiding unrelated failures.
- No three consecutive implementation tasks should lack an automated verification command.
- The phase cannot pass on source-string checks alone. The old SEC-001 payloads must execute through TestClient/fake provider call recorders, and SEC-002 must execute through real registered route dependencies/policy with resource fixtures.
- Required exit evidence: focused pytest output, deterministic generated OpenAPI authorization inventory, old P0 reproductions now denied, redacted sandbox/read-only Cognito evidence, reconciliation dry-run summary, and explicit statement that no production mutation occurred.

## Suggested Plan Slices

1. **Security contracts and Wave 0 tests:** safe errors/correlation, canonical Actor/roles/status, repository schemas, focused fixtures and red tests.
2. **Token and identity boundary:** issuer/client/token-use/JWKS verifier, explicit identity bindings, one-role intersection, active-only behavior, no request-time mutation.
3. **Canonical teacher terminology and public role barrier:** remove `/tutors`/aliases/runtime values; strict zero-mutation public allowlist and safe confirmation/login/refresh.
4. **Versioned grants and privileged lifecycle:** capability repository, teacher application/review/invitation/activation, routine admin provisioning, bootstrap hardening, immediate suspension/revocation.
5. **Central resource policy:** owner/bidirectional parent/task-scoped teacher/purpose-capability/break-glass decisions, 403/404/409/503 behavior and redacted events.
6. **Route migration and inventory:** migrate all route families, generate OpenAPI inventory, ensure no sensitive identifier route lacks executable policy.
7. **Reconciliation and P0 evidence:** dry-run-first inventory/migration, auto-tighten-only apply semantics, negative matrix, sandbox/read-only evidence and rollback notes.

The planner may split route migration into multiple executable plans because it spans the largest surface. Do not mark the phase complete after only the three audit sample routes are fixed; V9ACCESS-02 and V9ACCESS-03 require complete inventory-backed coverage.

## Planning Conclusion

Plan Phase 472 around an authoritative security spine, not local patches. The decisive acceptance boundary is that every protected request starts with a cryptographically valid, client-bound access token; resolves through one explicit identity binding to one active local account and one matching coarse Cognito role; loads current local grants and relationship/assignment facts; and passes one typed actor-resource-action-purpose policy. Public teacher applications and privileged provisioning must remain non-privileged until their durable workflows reach reconciled activation. Any conflict or dependency ambiguity denies safely and observably.

This architecture closes SEC-001, SEC-002 and SEC-004 while preserving the Phase 475 transaction boundary and Phase 474 global verification boundary. It also gives later mobile/product phases a stable API error and identity contract instead of propagating today's role aliases and identifier fallbacks.
