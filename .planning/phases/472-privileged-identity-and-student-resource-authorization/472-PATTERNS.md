# Phase 472: Codebase Pattern Map

**Mapped:** 2026-07-14  
**Purpose:** Concrete implementation patterns and integration points for Phase 472 planning  
**Inputs:** `472-CONTEXT.md`, `472-RESEARCH.md`, `472-VALIDATION.md`, current source and focused tests

## Non-Negotiable Pattern Contract

Every implementation plan must preserve these invariants as one security spine rather than independent route fixes:

1. `teacher` is the only accepted teacher-role term. Do not retain a `tutor` route, model, role, group, output value, helper, test contract, or normalization alias. Historical `tutor` data is a conflict until controlled migration.
2. Every account has exactly one canonical role. Zero or multiple recognized STOA groups, a mismatched local role, or a historical `tutor` value produces `identity_conflict`; no highest-role selection is allowed.
3. A verified access token resolves only through an explicit unique `(issuer, subject) -> user_id` binding. Email and Cognito username may inform offline reconciliation, never request-time identity resolution.
4. Effective privilege is the intersection of cryptographically verified Cognito identity/coarse group and fresh authoritative local state. Only `active` accounts and current versioned grants authorize protected work.
5. Authorization is one typed actor-resource-action-purpose decision. Student ownership, active bidirectional parent binding, task/assignment-scoped teacher access, or exact purpose capability are policy facts—not route-local role shortcuts.
6. Security failures use stable internal codes and safe client messages. Responses and events carry correlation IDs but never tokens, emails, content, object keys, capability/group internals, or raw provider errors.
7. Account, binding, assignment, and grant reads fail closed. Immediate revocation forbids cross-request allow caching; only bounded JWKS-key caching is permitted.
8. Phase 472 denies inconsistent parent/teacher facts. Phase 475 owns transactional relationship/takeover convergence; Phase 474 owns the global green-suite/CI baseline.

## Architectural Seams Already Present

### FastAPI dependency seam

The current protected-route seam is `src/stoa/deps.py`:

- `get_current_user()` is the common dependency used directly by routers.
- `require_role(*roles)` wraps `get_current_user()` and is widely attached to route parameters.
- `src/stoa/main.py` centrally registers every router.
- Tests construct small `FastAPI()` applications and use `app.dependency_overrides`, as shown by `_auth_client()` and `_admin_client()` in `tests/test_auth_account_lifecycle.py`, `_app_for_user()` in `tests/test_parent_children.py`, and `_client()` in `tests/test_questions.py`.

Reuse this dependency injection seam, but replace its security semantics:

- Keep AWS client factories and a temporary compatibility adapter in `deps.py`.
- Introduce thin `get_verified_token` and `get_actor` dependencies backed by `src/stoa/security/tokens.py` and `src/stoa/security/identity.py`.
- Make new policy dependency factories return the authorized `Actor` or resolved resource and attach an immutable `AuthorizationSpec` to the dependency callable.
- During bounded migration, `get_current_user()` may adapt an `Actor` to legacy handler shape; it must not decode a second time, resolve by email, infer a role, or mutate Cognito/profile state.
- Focused authorization tests must override `get_actor` or its injected repositories, not bypass the policy with a raw `{sub, role}` dictionary.

`require_role()` is useful only as a migration locator. It is not sufficient authorization for student-bearing routes or privileged operations and should not remain the final guard on those routes.

### DynamoDB repository seam

Repositories consistently use single-table `PK`/`SK` records through `stoa.db.dynamodb.get_table()`:

- `user_repo.put_user()` and `get_user()` use `PK=USER#{user_id}`, `SK=PROFILE`.
- `user_repo.put_parent_student_binding()` writes forward `USER#{parent_id}/CHILD#{student_id}` and reverse `USER#{student_id}/PARENT#{parent_id}` rows.
- `curriculum_ops_repo` uses entity prefixes plus immutable version/audit rows.
- `usage_ledger_repo.put_usage_event()` demonstrates conditional create with `attribute_not_exists(PK)` and maps `ConditionalCheckFailedException` to a duplicate result.
- `curriculum_ops_repo.set_published_pointer()` demonstrates expected-version conditional update and a domain-specific `StalePointerError`.
- `question_repo.update_status_conditionally()` plus `teacher_dispatch_service.dispatch_question()` demonstrates conditional claim conflict handling.

Reuse these conventions in focused repositories rather than expanding `user_repo.py` indefinitely:

| Repository | Recommended keys and responsibility | Reusable local pattern |
| --- | --- | --- |
| `identity_repo.py` | `IDENTITY#{issuer_hash}#{subject}/BINDING`, reverse `USER#{user_id}/IDENTITY#{issuer_hash}#{subject}` | conditional create; conflict is explicit, never overwrite |
| `capability_repo.py` | `USER#{user_id}/CAPABILITY#{name}#{scope_key}#{grant_id}` | append/version records; filter status/effective/expiry/latest version on every request |
| `teacher_application_repo.py` | immutable application-version rows, review rows, token-digest invitation rows, activation-command state | immutable version pattern plus conditional single-use transition |
| `security_audit_repo.py` | append-only security/lifecycle/denial evidence keyed by safe event/correlation IDs | curriculum audit shape plus usage metadata allowlisting/redaction |
| privileged identity/reconciliation repository | idempotent command/checkpoint/evidence records | deterministic idempotency key and conditional create/update |

The authoritative identity binding is the identity-keyed row. Reverse rows support inventory only. Invitation secrets are stored as digests. Capability revocation creates a new status/version visible on the next request. Do not put capabilities back into a mutable profile list.

### Idempotency and state-transition seam

The safest existing patterns are:

- `usage_ledger_service.build_*_idempotency_key()` creates deterministic keys and `usage_ledger_repo.put_usage_event()` makes duplicates observable but harmless.
- `curriculum_ops_repo.set_published_pointer()` performs compare-and-set updates and converts DynamoDB condition failures into a named conflict.
- `teacher_dispatch_service.dispatch_question()` carries expected status/deadline facts into `question_repo.update_status_conditionally()` and returns `claim_conflict` when it loses a race.
- `curriculum_ops_service` records `from_state`, `to_state`, `actor_id`, reason, version and timestamp in append-only audit events.

Apply the same service/repository split to teacher activation and routine administrator provisioning:

1. service validates actor/capability, immutable input version, email binding, expiry and requested transition;
2. repository performs conditional create/transition;
3. service executes provider steps idempotently;
4. local account stays non-active until Cognito group, local role and explicit binding reconcile;
5. service appends redacted lifecycle evidence;
6. retry resumes the same command rather than creating a second identity.

Cognito and DynamoDB are not transactional. The safe partial-failure pattern is deny-first local state plus resumable commands, never optimistic local activation.

### Capability and audit seam

`src/stoa/services/curriculum_ops_service.py` provides a useful least-privilege vocabulary:

- named constants such as `AUTHOR_CAPABILITY`, `REVIEWER_CAPABILITY`, and `PUBLISHER_CAPABILITY`;
- `_require_capability()` before each sensitive transition;
- `_require_state()` for explicit state-machine conflicts;
- `_audit()` for actor, operation, state transition, reason, version and timestamp;
- `_audit_response()` for bounded API projection.

Reuse named capabilities and per-operation checks, but replace `curriculum_capabilities()`: it currently unions capabilities from token claims, profile, metadata, permissions and scopes. Phase 472 capabilities must come only from current versioned local grants. The same authoritative source should adapt curriculum capabilities so the teacher role never implies curriculum authority.

For security events, combine the bounded projection approach with `usage_ledger_service.safe_usage_metadata()` and `usage_privacy_flags()`: use an allowlist, strip unexpected keys, record explicit privacy flags, and test canary values never appear. Do not copy the current curriculum audit field `actor_capabilities` wholesale into denial evidence; record only the policy-safe facts required by D-32.

### Configuration seam

`src/stoa/config.py::Settings` and cached `get_settings()` are the established configuration boundary. Add explicit settings for:

- allowed Cognito issuer(s) and access-token client IDs;
- JWKS fetch timeout, TTL and bounded maximum stale window;
- teacher invitation expiry and policy version;
- break-glass maximum duration and event/notification configuration;
- reconciliation batch/checkpoint bounds.

Production readiness must reject missing, empty, duplicate or ambiguous issuer/client configuration. Tests already build minimal `Settings(...)` objects, so new required behavior should retain deterministic test defaults or update the focused builders explicitly.

## Exact Replacement Map

### Token and identity boundary

Replace the security behavior concentrated in `src/stoa/deps.py`:

| Current symbol/behavior | Required replacement |
| --- | --- |
| process-global `_jwks_cache` | issuer-keyed, `kid`-keyed bounded cache in `security/jwks.py`, injected clock/async transport, single refresh for unknown `kid` |
| `_fetch_jwks()` synchronous `httpx.get` | async bounded transport with connect/read timeouts and per-issuer single-flight refresh |
| `_get_public_key()` unknown-key 401 | one forced refresh; unknown key plus provider failure becomes safe 503; never accept without verified signature |
| `get_current_user()` signature/issuer/use-only validation | `tokens.py` verifies RS256, configured issuer, time claims, `token_use=access`, and allowed `client_id` |
| first recognized `cognito:groups` entry | require exactly one canonical STOA group matching one local role |
| `custom:role`, email/profile and username fallbacks | explicit `(issuer, sub)` binding only; missing/mismatch is recovery/conflict |
| request-time `admin_add_user_to_group()` | delete; authentication is read-only and never repairs privilege |
| raw claims dictionary as actor | immutable canonical `Actor(user_id, issuer, subject, role, account_status, cognito_group, current grants, auth context)` |

The JWKS cache is the only permitted cross-request security cache. Actor construction must freshly load account status and grants. Policy must freshly load relationship/assignment facts for sensitive requests.

### Public registration and privileged onboarding

`src/stoa/routers/auth.py` currently defines a second unrestricted local `RegisterRequest`, `_ROLE_ALIAS`, `_ROLE_DISPLAY`, `_normalise_role()`, `_display_role()`, `_client_id_for_role()`, `_role_for_password_flow()`, and `_profile_from_current_user()`.

Required mapping:

- Replace the local role string with an exact self-service role allowlist. Validate before `_get_cognito()`, `sign_up()`, DynamoDB writes, or group changes.
- Remove `_ROLE_ALIAS`/`_ROLE_DISPLAY`; never map `tutor` to or from `teacher`.
- Registration and email confirmation must never add teacher/admin privilege. Confirmation may complete only the role already allowed by the non-privileged registration command.
- Login, refresh, password and verification flows must not select a privileged client from caller-provided role or email profile inference.
- Keep the existing `src/stoa/models/user.py::UserRole` enum as the canonical role vocabulary, but add exact one-role/account-status models and use them consistently rather than redefining permissive router models.
- Add `routers/teacher_applications.py` for public no-privilege application submission and separately guarded review/invitation actions.
- Full credential-document upload/storage/review remains out of scope; store only bounded declarations and safe offline evidence references.

The current `_bind_parent_student_if_possible()` and `_bind_existing_child_if_possible()` may remain migration inputs, but their email correlation and pending rows do not authorize Phase 472 access.

### Canonical teacher migration

The current active surface includes `src/stoa/routers/tutors.py`, `/tutors` registration in `src/stoa/main.py`, `user_repo.update_tutor_availability()`, teacher routes accepting `require_role("teacher", "tutor")`, and `tutor` occurrences across active services/tests/mobile contracts.

Implementation should:

- move any still-required `/tutors` functionality into canonical `/teachers` handlers/models, then delete `routers/tutors.py` and the router registration—no compatibility route;
- rename `TutorAvailability`, `TutorStats`, help-request outputs, nested `tutor` response keys and `update_tutor_availability()` to teacher equivalents;
- reject `tutor` in auth inputs, persisted role/group interpretation and runtime contracts;
- rename `tests/test_tutor_availability.py` and update all active test/mobile contract expectations;
- add a repository scan gate over `src`, `tests`, scripts and active mobile/API contracts. Historical planning/audit quotations may remain, but runtime source, contracts and persisted enums may not.

The initial scan found active `tutor` references in 22 source files and 13 test files. The gate must use the repository at execution time rather than freezing this count.

### Parent authorization

Useful existing records live in `src/stoa/db/repositories/user_repo.py`, while the current authorization helpers are in `src/stoa/routers/parents.py`:

- `_resolve_parent_profile()` demonstrates why email/Cognito fallback must be removed.
- `_list_children_for_parent()` merges formal binding rows with `_scan_children_for_parent()` legacy `parent_id` rows; the legacy merge must stop authorizing access.
- `_get_owned_child_profile()` starts from a formal forward binding but must be strengthened to read and compare the reverse binding, both profiles and current states.

Create one policy fact loader that requires:

- forward and reverse rows both exist;
- identical parent/student IDs, relationship and version;
- both binding rows are `active`;
- parent and student accounts are both `active`;
- repository absence is a denial and repository failure is safe 503.

`list_children_by_parent_scan()`, `_scan_children_for_parent()`, legacy profile `parent_id`, parent/child email matching, pending states and one-sided rows remain reconciliation/reporting inputs only. Phase 472 must not make binding writes transactional or broadly repair historical asymmetry; that is Phase 475.

### Teacher task scope

The existing task facts are concrete and reusable:

- `question.teacher_id`, `question.student_id`, `question.session_id`;
- `dispatched_teacher_id`, `dispatch_status`, `dispatch_deadline_at`, `previous_dispatch_teacher_ids`;
- `SESSION#{session_id}/META` rows written by `routers/teachers.py::takeover()`;
- conditional dispatch in `teacher_dispatch_service.dispatch_question()`;
- route-local owner checks in `teachers.py::reply()` and `resolve()`.

Move these facts into policy resolvers. A current dispatch/takeover authorizes only the question, linked conversation/session and minimum support context. Queue visibility alone never authorizes a student's profile, history, adaptive state, reports or unrelated questions. Broader access needs a separate active scoped student-teacher assignment.

Keep Phase 472 reads fail-closed and scoped. Do not absorb Phase 475's atomic takeover/session/notification rewrite.

### Admin and break-glass scope

`src/stoa/routers/admin.py` is the largest risk surface: it contains roughly one hundred `require_role("admin")` dependency sites and many student, parent, user, report, subscription, usage, account and recovery identifiers. Do not treat the `/admin` prefix as an authorization classification.

Map each operation to a purpose-specific capability and resource scope. At minimum distinguish:

- `admin_identity_manager` for routine administrator identity lifecycle and explicit privilege-grant approval;
- `teacher_identity_reviewer` for full teacher application/review visibility;
- `student_support_lookup` for bounded metadata only;
- content-bearing support/safety capabilities for specific read purposes;
- a separate short-lived `student_data_break_glass` read-only incident grant.

Break-glass requires active admin, incident ID, reason, expiry, immediate notification and independent review. It cannot mutate, export, send externally, change privilege or change curriculum. The bootstrap script remains outside request-path authority.

### Bootstrap script

`scripts/provision_production_admin.py` already provides useful guardrails:

- `--confirm-production`, `--dry-run`, named password environment variable and password checks;
- Cognito/local role conflict rejection;
- idempotent-ish existing-user/profile paths;
- `password=redacted` output;
- isolated test loading in `tests/test_provision_production_admin.py`.

Retain these patterns but narrow the script to bootstrap/disaster recovery and add purpose/incident reason, explicit identity binding, active-state fields, durable audit evidence, group/profile/binding reconciliation and safe idempotency. It must not create a permanently omnipotent request-path admin. Routine admin creation belongs to an authenticated service/route guarded by current `admin_identity_manager`.

## Central Authorization Dependency Pattern

Implement a typed dependency rather than repeating handler checks:

```text
authorize(
  AuthorizationSpec(
    resource_type="question",
    action="read",
    purpose="self_service|parent_learning_view|assigned_support",
    resolver=question_resource_from_path("question_id"),
  )
)
```

The resolver loads the resource and canonical owner IDs; the evaluator loads current policy facts and returns a decision/evidence object. The route uses the already-authorized resource so it cannot load a different ID after policy evaluation.

Decision order must be deterministic:

1. authenticated immutable Actor;
2. exact one-role intersection and current `active` account;
3. current target/resource facts;
4. self-owner, bidirectional parent, task/assignment teacher, or exact capability path;
5. break-glass extra constraints where selected;
6. existence-aware safe denial or dependency-unavailable 503.

Student self-service routes derive the canonical internal `user_id` from Actor. If a legacy explicit ID remains, it must match `actor.user_id` or go through central related-actor policy. Never use `user["sub"]` as a business resource ID after identity resolution.

## Executable Route Inventory Pattern

The current phase-relevant routers register 184 route decorators across conversations, students, questions, practice, adaptive, parents, teachers, tutors and admin. Because decorators span multiple lines and resources can be indirect, source-text lists are not an adequate completeness gate.

Build `src/stoa/security/route_inventory.py` from FastAPI's actual `APIRoute.dependant` trees:

- recursively discover attached executable `AuthorizationSpec` metadata;
- inspect path/query parameters, Pydantic body fields and aliases;
- recognize direct and indirect IDs including student, question, conversation, assignment, report, request, parent, teacher and user identifiers;
- classify public auth/health/global catalog routes explicitly rather than omitting them;
- fail on missing/unknown specs, duplicate ambiguity, or metadata without the actual dependency;
- project the same metadata into `x-stoa-authorization` OpenAPI and a deterministic checked JSON/Markdown inventory.

Initial route-family migration order should be:

1. `students.py` and `questions.py` (the reproduced cross-student paths);
2. `practice.py`, `adaptive.py`, `parents.py`;
3. `teachers.py` plus canonical functionality moved from `tutors.py`;
4. `conversations.py`, report/account-bearing admin routes and remaining indirect identifiers;
5. generated inventory and a synthetic unprotected-route mutation test.

Every family must include an authorized positive control, otherwise blanket denial can satisfy negative tests.

## Safe Error and Evidence Pattern

Current code sometimes returns structured `detail={"code": ...}` (auth verification and curriculum flows), but the outer shape and messages vary and provider details can leak. Centralize this in `src/stoa/security/errors.py` and install correlation/error handling from `src/stoa/main.py`.

Required response body:

```json
{"code":"action_not_allowed","message":"You cannot perform this action.","correlationId":"..."}
```

Use the locked status taxonomy:

- 401: missing, invalid or expired authentication;
- 403: authenticated actor may know the resource but cannot perform the action;
- indistinguishable 404 `resource_not_found`: unrelated actor must not learn existence;
- 409: recoverable identity/binding/invitation conflict;
- 503: identity provider or authorization store cannot safely decide.

The UI maps these codes to reauthentication, formal relationship completion, review waiting, recovery, support-with-correlation-ID or bounded retry. API messages must not expose issuer/client mismatch, key/signature detail, groups, grants, provider payloads, or existence.

`src/stoa/routers/admin.py::_request_id()` already recognizes request/correlation headers, and report services carry correlation IDs in audit records. Reuse the correlation concept, but generate/normalize it centrally and expose camel-case `correlationId` at the API boundary.

## Testing Patterns to Reuse

### Focused application construction

Continue the established pattern of one-router FastAPI applications with dependency overrides. Wave 0 should add:

- immutable Actor factories;
- fake identity/account/grant/binding/assignment repositories;
- fake Cognito call recorder;
- injected frozen clock;
- injected async JWKS transport and two RSA/JWKS keysets;
- correlation-ID helper and canary redaction assertions.

Existing `FakeCognito.calls` in `tests/test_auth_account_lifecycle.py` is a strong base for zero-mutation assertions. Rejected `teacher`, `admin`, `tutor`, unknown and case/Unicode variants must produce no Cognito or DynamoDB calls.

### Repository conflict tests

Reuse `botocore.exceptions.ClientError` fakes and explicit `ConditionalCheckFailedException` assertions from current repository/service tests. Required concurrency cases include:

- two consumers of one activation invitation: exactly one transition succeeds;
- duplicate identity binding: no overwrite;
- stale capability/command version: conflict;
- idempotent replay: same result, no duplicate privilege or evidence event;
- provider partial failure: local account remains non-active and retry resumes.

### Authorization matrix

Generate cases over actor, resource family, action, purpose, relationship/assignment/grant state, existence and dependency availability. Assert status, stable code, safe message, correlation ID and redacted event. Include current-route positive controls and execute through registered dependency trees rather than testing a policy function alone.

Focused commands and Wave 0 files are locked in `472-VALIDATION.md`. Full-suite failures unrelated to this phase must be recorded honestly; Phase 474 owns global isolation/green CI.

## Anti-Patterns the Planner Must Forbid

- Adding conditionals to individual routers without the central policy and route-inventory declaration.
- Accepting or normalizing `tutor` for backward compatibility.
- Selecting the first/highest recognized Cognito group.
- Treating token claims, profile lists, metadata or scopes as authoritative capability grants.
- Resolving business identity through email, username, direct `sub` lookup fallback, or request-time binding creation.
- Calling Cognito group mutation from authentication or authorization dependencies.
- Using admin/teacher role alone for student data access.
- Trusting legacy `parent_id`, email matching, pending or one-sided parent rows.
- Using a queue item as authorization for broader student content.
- Returning different real-vs-random resource errors to unrelated actors.
- Returning raw `HTTPException.detail`, Cognito/JWKS exceptions or capability/group names to clients.
- Caching account, relationship, assignment, grant or allow decisions across requests.
- Activating a teacher on review approval instead of verified single-use invitation consumption.
- Automatically adding/restoring roles or grants during reconciliation.
- Expanding Phase 472 into document credential management, Phase 475 transaction repair, Phase 474 global CI repair, or production mutation.

## Planning Dependency Order

The concrete codebase dependencies support this sequence:

1. Wave 0 security fixtures/tests plus canonical errors, Actor, roles/status and event contracts.
2. Token/JWKS validation and explicit identity binding, then thin `deps.py` adapters.
3. Strict public role barrier and complete `teacher`-only contract migration.
4. Versioned grants, teacher application/invitation activation, routine admin lifecycle and bootstrap hardening.
5. Central policy and resource fact loaders.
6. Route-family migration plus executable inventory/OpenAPI projection.
7. Dry-run privileged reconciliation and focused P0/sandbox evidence.

Plans may split route migration because of the 184-route surface, but no plan may claim V9ACCESS-02 or V9ACCESS-03 complete until every registered sensitive direct/indirect identifier is inventory-classified and exercised with negative and positive evidence.

## Pattern Mapping Completion Criteria

This map is complete for planning when each resulting `PLAN.md`:

- names the exact source/test files and symbols it will reuse, replace or delete;
- carries the relevant locked decisions and requirement IDs;
- includes a threat model and safe failure behavior;
- separates service validation/state-machine work from repository conditional writes;
- includes executable verification from `472-VALIDATION.md`;
- preserves the Phase 474/475 boundaries and makes no production mutation assumption.

## PATTERN MAPPING COMPLETE
