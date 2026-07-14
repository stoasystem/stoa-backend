# Phase 472: Privileged Identity And Student Resource Authorization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-14
**Phase:** 472-privileged-identity-and-student-resource-authorization
**Areas discussed:** Privileged onboarding, Student access rules, Identity conflicts, Denial and outage behavior

---

## Privileged Onboarding

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Public teacher application with zero teacher access until review | Admin invitation without application; public no-access application followed by approved activation invitation | Public application + approved invitation ✓ |
| Review authority | Any active admin; dual-admin approval; active admin with `teacher_identity_reviewer` | Explicit reviewer capability ✓ |
| Application records | Mutable pending record; one-shot application; immutable versions | Immutable versions ✓ |
| Teacher revocation | Token-refresh expiry; existing-session grace; immediate revocation | Immediate revocation ✓ |
| Admin provisioning | Script only; application only; bootstrap script plus authenticated routine workflow | Hybrid bootstrap/routine workflow ✓ |
| Root admin authority | Permanent superadmin; universal dual control; capability-bounded normal operation | Capability-bounded ✓ |
| Existing privileged accounts | Grandfather all; warn only; verify and suspend anomalies | Verify and suspend anomalies ✓ |
| Application visibility | All admins; reviewer plus broad compliance visibility; reviewer-only full content | Minimum visibility ✓ |

**User's choice:** Public teacher candidates may apply, but the application creates no teacher identity or access. An explicitly capable administrator approves an immutable version, after which an expiring single-use same-email activation invitation is issued; consuming it is required before teacher activation. Privileged identity remains least-privileged, immediately revocable, audited, and reconciled fail-closed.

**Notes:** The user initially requested in-product degree/qualification document review. The discussion separated the immediate access-control boundary from a full credential-document product. Offline qualification review remains in Phase 472; the document workflow is deferred intact.

---

## Student Access Rules

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Parent relationship truth | Formal or legacy link; limited pending access; active bidirectional formal binding only | Active bidirectional binding ✓ |
| Teacher scope | Full assigned-student access; broad queue access; purpose/resource scoped access | Purpose scoped ✓ |
| Admin student-content access | All admins; metadata only; capability/purpose scoped | Capability scoped ✓ |
| Relationship revocation | Grace period; retain old-resource access; immediate | Immediate ✓ |
| Break-glass | None; unrestricted emergency access; incident-only short-lived read access | Strict incident-only path ✓ |
| Support lookup | No lookup; full summary; exact metadata-only lookup | Safe metadata lookup ✓ |
| New route default | Broad role defaults; known routes only; undeclared routes denied | Deny by default ✓ |
| Student self identity | Client ID with checks; delegation; derive from verified token binding | Derive identity ✓ |

**User's choice:** Every student-resource decision must use active authoritative relationships, purpose-scoped capabilities, and an actor-resource-action-purpose policy. Revocation is immediate and unclassified routes fail closed.

**Notes:** Break-glass was clarified with concrete security/data-incident examples. The user selected a strict read-only incident path, not a routine support shortcut.

---

## Identity Conflicts

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Cognito/local disagreement | Cognito wins; profile wins; privilege intersection and conflict denial | Intersection ✓ |
| Canonical identity | Cognito sub everywhere; email fallback; internal ID plus explicit issuer/sub binding | Internal ID binding ✓ |
| Account roles | Multiple contexts; highest privilege; exactly one role | One role ✓ |
| Account state | Cognito state only; limited pending access; active only | Active only ✓ |
| Teacher terminology | Separate roles; legacy alias; `teacher` only | `teacher` only ✓ |
| Capability authority | Token claims; profile list; versioned local grant records | Versioned grants ✓ |
| Reconciliation | Fully automatic; report only; automatic restriction with human privilege grants | Auto-restrict/human-grant ✓ |
| Conflict recovery | Reject everything; degrade role; safe recovery surface only | Recovery surface ✓ |

**User's choice:** Each account has one role, local versioned capability grants are authoritative, and conflicts deny protected access. STOA must remove `tutor` completely and use only `teacher`.

**Notes:** The user strengthened the initial recommendation: `tutor` is not retained even as a compatibility alias. Incoming values are rejected and historical values require controlled migration.

---

## Denial And Outage Behavior

| Decision | Alternatives considered | Selected |
|----------|-------------------------|----------|
| Error taxonomy | All 403; detailed internals; structured 401/403/409/503 | Structured taxonomy ✓ |
| Resource existence | Always 403; always 404; 404 for unrelated and 403 for known-but-disallowed | Existence hiding ✓ |
| JWKS outage | Reject all; bypass verification; bounded known-key cache | Bounded known-key cache ✓ |
| API/UI detail | Generic UI; expose internals; structured API with safe actionable UI | Two-layer errors ✓ |
| Client retry | Retry all; never retry; error-specific bounded retry | Bounded by error ✓ |
| Denial evidence | Full request logs; server errors only; structured redacted events/alerts | Structured events ✓ |
| User-facing copy | Generic failure; internal permission explanation; safe scenario-specific action | Actionable safe copy ✓ |
| Authorization-store outage | Cached access; cached reads; fail closed with 503 | Fail closed ✓ |

**User's choice:** Applications receive structured actionable codes; users see friendly next steps; internal details remain private. Temporary dependency failures never bypass signature or current authorization checks.

**Notes:** The user requested clarification of vague copy. Final guidance separates incomplete parent binding, identity conflict, pending teacher review, expired login, permission denial, and temporary login-service outage into distinct safe user actions.

---

## the agent's Discretion

- Exact TTLs, retry counts, cache windows, reconciliation frequency, and storage schema details within the locked safety properties.
- Exact localized UI wording and capability names beyond the explicitly selected names.
- Migration batching and rollout mechanics, provided anomalies are quarantined and privilege is never silently broadened.

## Deferred Ideas

- Full in-product teacher credential/document submission, secure storage, qualification evidence review, requests for more information, resubmission, retention, and deletion.
- Multi-role accounts; Phase 472 enforces exactly one role per account.
