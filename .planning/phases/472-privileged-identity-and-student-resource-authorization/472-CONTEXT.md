# Phase 472: Privileged Identity And Student Resource Authorization - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the reachable privileged-registration and cross-student authorization defects before further product integration. This phase establishes authoritative privileged onboarding, one canonical identity and capability model, purpose-scoped student-resource authorization, complete route coverage, immediate revocation, and fail-closed authentication/authorization behavior.

The phase does not build the full teacher credential-document product. It may accept a public teacher application with no privileges and support offline qualification review, but document upload, credential storage, evidence review, resubmission, retention, and deletion are deferred.

</domain>

<decisions>
## Implementation Decisions

### Privileged Onboarding

- **D-01:** Public self-service account creation may create only approved non-privileged roles. A teacher candidate uses a separate public application flow that creates no `teacher` role, Cognito teacher-group membership, student-data access, or teacher API access. Approval issues an expiring, single-use activation invitation bound to the approved application version and verified email; only verified consumption of that invitation may create/activate the teacher identity.
- **D-02:** Teacher qualifications are reviewed offline in this phase. Approval may be performed only by an `active` administrator holding the explicit `teacher_identity_reviewer` capability.
- **D-03:** Each teacher application submission is an immutable version. Reviewers approve or reject that exact version and record an internal reason. A rejected candidate may submit a new version; old versions remain unchanged.
- **D-04:** Approval alone does not directly elevate the applicant. It authorizes issuance of the bound activation invitation required by V9AUTH-03. Only successful one-time invitation consumption after same-email verification may activate the `teacher` role and Cognito group. Approval, invitation issuance/consumption, rejection, activation, suspension, revocation, and migration events must identify actor, target, application version, timestamp, reason, and safe evidence reference.
- **D-05:** Teacher suspension/revocation takes effect immediately. The account is marked non-active, removed from the teacher group, globally signed out, and denied on the next sensitive request even if an old access token has not expired.
- **D-06:** The controlled provisioning script remains only for bootstrap and disaster recovery. Routine administrator creation uses an authenticated application workflow and requires `admin_identity_manager` capability.
- **D-07:** No administrator, including the bootstrap/root administrator, has permanent unrestricted request-path authority. Normal operations remain capability-bounded; emergency recovery stays in the separately controlled and audited bootstrap path.
- **D-08:** Existing privileged accounts must be inventoried and reconciled. Migrate only accounts backed by approved identity and active profile evidence. Unknown, inconsistent, multi-role, or unapproved privileged accounts enter `suspended_pending_review` and cannot access sensitive resources.
- **D-09:** Full teacher applications are visible only to `teacher_identity_reviewer` administrators. Other administrators may see bounded metadata only. Audit records store summaries and evidence references rather than copied sensitive application content.

### Student Resource Authorization

- **D-10:** Parent access requires a formal, bidirectional, `active` parent-student binding and active accounts on both sides. Legacy `parent_id`, email matching, pending relationships, one-sided rows, and revoked bindings never authorize access.
- **D-11:** Teacher access is purpose- and resource-scoped. A single dispatch/takeover authorizes only the relevant question, conversation, and minimum context. Broader learning-resource access requires a separate active, scoped student-teacher assignment.
- **D-12:** The `admin` role does not grant blanket student-content access. Sensitive reads require purpose-specific capabilities such as support or safety-review access and produce audit evidence.
- **D-13:** Revoked parent bindings and teacher assignments stop authorizing on the next request. Tokens, open screens, cached identifiers, and unfinished sessions do not preserve access; unfinished work is handed to a newly authorized actor.
- **D-14:** Keep a strict incident-only break-glass path. It is available only to an active administrator with an explicit break-glass capability, requires an incident ID and reason, is short-lived and read-only, triggers immediate notification, and requires independent post-event review. It cannot grant mutation, bulk export, external sending, privilege changes, or curriculum changes.
- **D-15:** `student_support_lookup` permits exact, bounded metadata lookup only: safe account state, binding state, denial reason code, and correlation/support identifiers. It never exposes learning content, messages, answers, reports, files, object keys, or provider payloads.
- **D-16:** Every route accepting or resolving a student/question/conversation/practice/adaptive/report/teacher/parent identifier must declare resource type, action, and purpose and call the central authorization policy. Unclassified or omitted routes deny by default and fail route-inventory/release verification.
- **D-17:** Student self-service routes derive the canonical business user from the verified token binding. Client-supplied `student_id` is not authoritative. Legacy explicit identifiers must match the resolved identity or be rejected; related actors may supply target IDs only through central policy evaluation.

### Identity And Capability Consistency

- **D-18:** Effective privilege is the intersection of verified Cognito identity/coarse group and authoritative local account status/capability records. Any disagreement creates `identity_conflict` and denies protected access. Authentication must never repair or broaden identity state as a request side effect.
- **D-19:** Business data uses a stable internal `user_id`. An explicit unique `(issuer, Cognito sub) -> user_id` binding resolves tokens to business identities. Email is never a security identity fallback.
- **D-20:** Every account has exactly one primary role. Multiple STOA role groups are an identity conflict; the system never selects a highest-privilege role.
- **D-21:** `active` is the only account state that authorizes protected access. `pending_verification`, `pending_review`, `suspended`, `revoked`, `disabled`, and `deleted` deny access. Suspended accounts may be restored through policy; revoked accounts require reapproval; deleted accounts remain non-reactivatable audit tombstones.
- **D-22:** `teacher` is the only teacher-role term anywhere in STOA. Remove `tutor` from accepted inputs, APIs, persisted values, Cognito groups, client contracts, tests, and authorization logic. New `tutor` values are rejected rather than normalized. Historical `tutor` values remain conflicted until controlled migration.
- **D-23:** Independent, versioned local capability grants are authoritative. Each grant records grantor, reason, scope, effective/expiry time, status, and version. Token claims and profile lists cannot broaden a grant; local revocation takes effect on the next request.
- **D-24:** Reconciliation may automatically remove excess groups, suspend anomalies, flag conflicts, and propose repairs. Adding a role, restoring an account, or granting a capability always requires explicit approval from an active `admin_identity_manager` administrator.
- **D-25:** An identity-conflicted user receives only a safe recovery surface: identity status, email re-verification where applicable, logout, and recovery-request submission. Student, teacher, parent, and admin product resources remain denied. Responses expose safe reason and correlation IDs, not groups, capabilities, or internal records.

### Denial, Failure, Recovery, And Evidence

- **D-26:** Use a stable structured error taxonomy: `401` for missing/invalid/expired authentication, `403` for an authenticated actor denied an action they may know exists, `409` for a recoverable identity/binding conflict, and `503` when an identity or authorization dependency cannot safely decide.
- **D-27:** If an actor has no authorized relationship and must not know whether a resource exists, return indistinguishable `404 resource_not_found`. Return `403 action_not_allowed` only when the actor may know the resource exists but lacks the requested action.
- **D-28:** API responses contain a stable safe `code`, safe message, and `correlationId`. Sensitive validation details—wrong pool/client, signature internals, group/capability values, keys, tokens, and provider payloads—remain in redacted internal telemetry only.
- **D-29:** Web/mobile map structured API codes to simple, friendly, actionable messages: reauthenticate, complete formal parent binding, wait for teacher review, start account recovery, contact support with a correlation ID, or retry after a temporary login-service outage. UI copy must not reveal internal authorization structure or resource existence.
- **D-30:** JWKS handling may continue to verify a known cached key only within a strict bounded cache window. An unknown `kid` triggers one refresh; refresh failure returns `503 identity_provider_unavailable`. Never accept an unknown key or skip signature verification.
- **D-31:** Client retry behavior is error-specific and bounded: refresh once for `token_expired`; do not retry `403/404`; route `409` into recovery; retry `503` only for idempotent reads with jittered backoff and `Retry-After`; retry writes only with an idempotency key.
- **D-32:** Security-denial events contain internal actor ID, canonical role, resource type, action, purpose, policy version, result code, and correlation ID. They never contain tokens, student content, object keys, or raw provider responses. Aggregate repeated probes and alert on resource enumeration, cross-student attempts, and privileged-registration attempts.
- **D-33:** If the local authorization store cannot provide current account, binding, assignment, or capability state, return `503 authorization_temporarily_unavailable` for protected student, teacher, parent, and admin access. Do not use stale authorization caches that could revive revoked privileges.

### the agent's Discretion

- Exact teacher-application fields that do not introduce credential-document storage.
- Expiry durations, retry counts, JWKS TTL/stale-if-error limits, capability record schema details, and reconciliation batch size, provided they preserve the locked fail-closed and immediate-revocation behavior.
- Exact capability names beyond those explicitly locked above, provided every sensitive action remains purpose-scoped and least-privileged.
- Exact safe UI wording and localization, provided messages remain friendly, actionable, and do not expose internal authorization details.
- Migration mechanics and batching for historical IDs, roles, groups, and relationships, provided anomalies are never silently grandfathered or privilege-broadened.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone And Phase Contract

- `.planning/PROJECT.md` — v9.0 product-reality boundary, current milestone constraints, and explicit restriction on broadening teacher curriculum authority.
- `.planning/REQUIREMENTS.md` — V9AUTH-01..05 and V9ACCESS-01..03 acceptance requirements and milestone definition of done.
- `.planning/ROADMAP.md` — Phase 472 goal, success criteria, evidence requirements, and mandatory P0 exit gate.

### Audit Baseline

- `docs/audit/full-project-audit.md` — authoritative analysis of SEC-001, SEC-002, and SEC-004, route-level evidence, recommended fixes, and release blockers.
- `docs/audit/findings.json` — machine-readable finding locations, triggers, dependencies, test expectations, and severities.

### Existing Privileged Operations

- `scripts/provision_production_admin.py` — existing bootstrap/production-admin provisioning path to retain only for controlled bootstrap and disaster recovery.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/stoa/services/curriculum_ops_service.py`: existing explicit capability extraction and enforcement pattern; reuse the least-privilege concept while moving identity capabilities to an authoritative versioned grant model.
- `src/stoa/db/repositories/user_repo.py`: existing formal forward/reverse parent-student binding records and lookup functions; use as migration input, but require active bidirectional truth and later transactional consistency work.
- `scripts/provision_production_admin.py`: existing guarded bootstrap CLI and conflict checks; harden auditing/idempotency and keep it outside routine admin creation.
- `tests/test_auth_account_lifecycle.py`, `tests/test_parent_children.py`, and `tests/test_provision_production_admin.py`: existing fixtures and lifecycle coverage that can seed the new negative authorization and reconciliation matrices.

### Established Patterns

- FastAPI dependencies in `src/stoa/deps.py` establish request authentication and role enforcement, but currently mix token validation, role fallback, Cognito lookup, and best-effort privilege mutation. Separate authentication, identity resolution, and authorization policy boundaries.
- Cognito provides identity and coarse group claims; DynamoDB stores profiles, relationships, and application capabilities. Preserve both systems but require intersecting evidence instead of fallback privilege inference.
- The repository already uses stable structured error bodies in several account-verification paths; converge security failures on one safe schema and correlation ID.
- Teacher dispatch and takeover records already provide question, teacher, student, and session identifiers that can become purpose-scoped authorization facts.

### Integration Points

- `src/stoa/models/user.py` and `src/stoa/routers/auth.py`: split public non-privileged registration from no-access teacher application; remove privileged public role creation and all `tutor` compatibility.
- `src/stoa/deps.py`: validate issuer, token use, allowed client, JWKS rotation/cache isolation, canonical identity binding, active state, and conflict behavior without request-time mutation.
- `src/stoa/routers/students.py`, `questions.py`, `practice.py`, `adaptive.py`, `parents.py`, `teachers.py`, `tutors.py`, and report/admin routes: inventory every identifier-bearing route and migrate it to actor-resource-action-purpose authorization. The `tutors.py` naming/API surface must be removed or migrated to `teacher` terminology.
- `src/stoa/db/repositories/user_repo.py`: add explicit identity bindings, authoritative capability grants, immutable teacher applications, lifecycle/audit records, and safe reconciliation support; relationship transaction repair itself remains coordinated with Phase 475.
- Cognito group/profile migration: collapse all teacher identity terminology to `teacher`, reject new `tutor` values, and quarantine conflicts until controlled reconciliation.

</code_context>

<specifics>
## Specific Ideas

- The user explicitly requires that STOA use only the word and role `teacher`; `tutor` must disappear rather than remain as a compatibility alias.
- UI errors must be simple and actionable while applications consume structured codes. Examples should tell a user to re-login, finish a formal relationship confirmation, wait for teacher review, contact support with a correlation ID, or retry a temporarily unavailable login service.
- Break-glass means a rare security/data incident such as suspected cross-account exposure or compromised identity—not ordinary support, analytics, teaching review, or debugging.

</specifics>

<deferred>
## Deferred Ideas

- Build the complete teacher qualification product in a future phase: credential/document upload, secure storage, malware/content validation, reviewer workbench, requests for more information, resubmission, retention/deletion, and applicant-visible decision history.
- Explicit multi-role accounts are deferred. Phase 472 enforces exactly one role per account.

</deferred>

---

*Phase: 472-privileged-identity-and-student-resource-authorization*
*Context gathered: 2026-07-14*
