---
gsd_state_version: 1.0
milestone: v9.0
milestone_name: Product Reality, Authorization And Core Journey Completion
status: executing
last_updated: "2026-07-15T16:15:19.732Z"
last_activity: 2026-07-15 -- Plan 472-19 completed typed admin body-target authorization
progress:
  total_phases: 10
  completed_phases: 0
  total_plans: 22
  completed_plans: 19
  percent: 86
---

# Project State

## Current Project

STOA backend.

See: .planning/PROJECT.md (updated 2026-07-14)

## Current Position

Phase: 472 Privileged Identity And Student Resource Authorization — EXECUTING
Plan: 19 of 22 complete; executing Wave 10
Status: Executing second gap closure
Last activity: 2026-07-15 -- Plan 472-19 completed typed admin body-target authorization

## Accumulated Context

- v8.0-v8.4 are complete as local gated operations contracts; they do not prove integrated product or live rollout completion.
- The 2026-07-14 audit at `de3bf1e` records 31 findings: 2 P0, 9 P1, 18 P2, and 2 P3.
- `SEC-001` public privileged registration and `SEC-002` horizontal student-data access are the first mandatory closure boundary.
- The full Python suite currently reports 12 failed and 640 passed on both local Python 3.14 and a clean Python 3.12 environment.
- The mobile dependency manifest is currently unresolvable and most routes remain placeholder UI; v9.0 requires clean builds and real student/parent journeys.
- Curriculum mutation remains restricted to explicitly capability-authorized operators; teacher role alone is insufficient.
- External rollout, paid marketing, new markets, enterprise automation, broader AI autonomy, and uncontrolled provider writes remain out of scope.
- Phase 472 uses one closed canonical role enum: `student|parent|teacher|admin`; historical aliases are rejection/reconciliation inputs only.
- Security responses expose only stable `code`, safe `message`, and `correlationId`; temporary dependency retries are bounded and idempotent-read-only.
- Wave 0 client recovery behavior is generated and tested in Phase 472; Phase 478 owns web/mobile rendering and integration.
- Authentication accepts only RS256 access tokens bound to an explicitly configured issuer and client; JWKS caching is issuer-isolated and bounded through provider outages.
- Business identity resolves only through a unique issuer-subject binding to one fresh active local role and authoritative grants; request-time email fallback and Cognito privilege mutation are removed.
- Public self-service registration accepts only exact student/parent commands before provider access, and confirmation revalidates persisted non-privileged registration provenance.
- `teacher` is the sole active teacher-role/API term; the legacy route is removed and an exact semantic allowlist fails on active contracts or stale exemptions.
- Current versioned local grants alone authorize capabilities; revocation is visible on the next request and no role or claim source broadens authority.
- Teacher approval issues only a digest-bound expiring invitation; same-verified-email consumption resumes one deny-first activation command until group, profile, and binding reconcile.
- Routine admin lifecycle requires `admin_identity_manager`; bootstrap remains first-admin/disaster-only and grants no implicit request-path authority.
- One central policy now authorizes student resources from a load-once `ResourceRef` plus fresh owner, strict bidirectional parent, current teacher task/assignment, or exact purpose-capability facts; role, legacy links, queue visibility, stale grants, and incomplete break-glass evidence never broaden access.
- All student, question, conversation, message, stream, and teacher-help identifiers now enter through executable Actor policy dependencies; self identity is canonical, handlers receive the resolved object, and unrelated real IDs are hidden like random IDs before effects.
- Practice, adaptive-learning, and parent resources now use Actor policy with explicit safe-public catalog metadata, exact assignment/capability scope, load-once targets, and strict active bidirectional parent-child bindings.
- Every canonical teacher route now uses Actor plus executable self, current-task, assignment, or exact-capability policy; queue metadata is bounded, indirect help/draft IDs resolve before effects, and stale assignments never preserve access.
- All 219 registered FastAPI method/path operations now derive deterministic authorization inventory and OpenAPI metadata from the executable dependency graph; unknown routes and sensitive identifier mutations fail closed.
- Privileged identity reconciliation is redacted and dry-run-first, can only suspend/remove/sign-out/revoke automatically, and requires a separate active `admin_identity_manager` command for any elevation.
- The extended Phase 472 focused gate reports 546 passed; the full suite reports 1019 passed and the same 23 unrelated strict production-configuration fixture failures owned by Phase 474.
- Non-production Cognito sandbox evidence was not approved/configured and remains explicitly NOT RUN; no production/provider mutation was performed.
- Conflicted privileged identities now lose every current grant through a conditional current-pointer transition backed by immutable generation/version history.
- Account/provider restore cannot revive historical capability authority; only a new manager-approved command and grant identity can create the next generation.
- Route identifier discovery now traverses all FastAPI dependencies and nested annotation containers; exact scoped declarations and executable specs fail closed across runtime, checked JSON, and OpenAPI.
- All eight public authentication operations now use one closed provider-error taxonomy with exact actionable structured responses, server-owned correlation, bounded retries, and redacted internal telemetry.
- G-01 through G-05 pass together in 114 independent local reproductions; route/client contracts are byte-stable and evidence is bound to the tested source SHA without claiming unavailable live checks.
- Reconciliation grant actions now carry immutable capability, exact scope, generation, grant ID, and version coordinates; duplicate caller IDs across lineages cannot collapse into first-match revocation.
- Account restore remains capability-mutation-free, and a fresh Actor cannot regain quarantined authority without a new manager-approved command and new grant identity.
- Every registered administrator body target now enters through a typed route provider; bounded unique ResourceRefs require all-of capability decisions and durable per-target evidence before endpoint effects.

### Pending Todos

- Execute Plans 472-17 through 472-22, then independently re-verify all six final review findings while retaining explicit external-evidence limitations.
- Preserve all 44 requirement mappings and all 31 finding assignments while phase plans are refined.
- Require approved sandbox or read-only evidence for external systems; do not fabricate live results or authorize production mutation through planning.

### Blockers/Concerns

- P0 authorization defects block external beta and any broader user rollout until fixed and independently regression-tested.
- The direct main-to-Lambda workflow, red test baseline, and stale artifact/runtime state prevent a trustworthy release candidate today.
- Mobile native build/device verification cannot begin until Phase 477 repairs and locks the Expo dependency matrix.
- Authoritative IaC currently appears external to this repository and must be imported or cross-repository traced in Phase 479.
- Global `gsd progress` still scans 55 pre-v9 phase directories left in `.planning/phases/`; use `STATE.md` and `roadmap analyze` for v9 status until those historical records are safely archived rather than deleted.

## Operator Next Steps

- Run `$gsd-execute-phase 472`; do not mark the phase complete until Plans 472-17 through 472-22 execute and independent verification passes.
- Do not begin Phase 478 core mobile completion before Phases 473, 475, 476, and 477 satisfy their exit gates.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 472 P01 | 7 min | 4 tasks | 18 files |
| Phase 472 P02 | 45 min | 3 tasks | 9 files |
| Phase 472 P03 | 83 min | 3 tasks | 41 files |
| Phase 472 P04 | 26 min | 3 tasks | 19 files |
| Phase 472 P05 | 15 min | 3 tasks | 6 files |
| Phase 472 P06 | 19 min | 3 tasks | 15 files |
| Phase 472 P07 | 17 min | 3 tasks | 15 files |
| Phase 472 P08 | 20 min | 3 tasks | 15 files |
| Phase 472 P09 | 8 min | 4 tasks | 20 files |
| Phase 472 P10 | 18 min | 4 tasks | 18 files |
| Phase 472 P11 | 30 min | 3 tasks | 7 files |
| Phase 472 P12 | 13 min | 2 tasks | 7 files |
| Phase 472 P14 | 45 min | 3 tasks | 20 files |
| Phase 472 P13 | 10 min | 2 tasks | 5 files |
| Phase 472 P15 | 8 min | 3 tasks | 8 files |
| Phase 472 P16 | 6 min | 3 tasks | 3 files |
| Phase 472 P17 | 8 min | 3 tasks | 5 files |
| Phase 472 P18 | 4 min | 2 tasks | 3 files |
| Phase 472 P19 | 5 min | 3 tasks | 7 files |

## Decisions

- [Phase 472]: Canonical authorization correlation IDs are generated server-side and never reuse an inbound header. — Prevents client-selected audit correlation and replay confusion.
- [Phase 472]: Audit rows and partition keys use keyed actor/resource fingerprints. — Raw student, owner, target, email, and key material must never persist.
- [Phase 472]: Relationship-sensitive and privileged allows are evidence-before-effect. — An audit outage cannot broaden access or permit sensitive effects.
- [Phase 472]: Public/global identifier-bearing commands require exact scoped declarations, while safe-public and protected identifiers require compatible executable specs. — One recursive projection now drives validation, checked JSON, and OpenAPI.
- [Phase 472]: Existing-account public registration resumes only after immutable command, issuer, subject, user ID, and role all match exactly. — Unproved provider accounts receive one safe recovery action before any authority mutation.
- [Phase 472]: Verification resend selects the local profile only by the immutable command user ID. — Email-index collisions cannot select or activate identity, and already-confirmed recovery must complete command-aware reconciliation.
- [Phase 472]: Reconciliation action identity is bound to the complete immutable grant coordinate. — Duplicate grant IDs across capabilities or scopes must produce distinct deterministic revoke/checkpoint operations.
- [Phase 472]: Account restoration never restores capability history. — Only a new manager-approved command and new grant identity may create a later active generation.
- [Phase 472]: Validated route-specific providers are the only source of administrator body-target authority. — Arbitrary JSON and evidence-only dictionaries never create scope; every concrete member is authorized and evidenced before effects.
