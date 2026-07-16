---
gsd_state_version: 1.0
milestone: v9.0
milestone_name: Product Reality, Authorization And Core Journey Completion
status: executing
stopped_at: Completed 473-08-PLAN.md; next 473-09
last_updated: "2026-07-16T15:37:55.000Z"
last_activity: 2026-07-16 -- Plan 473-08 completed; opaque chunks and immutable-byte promotion are green
progress:
  total_phases: 10
  completed_phases: 1
  total_plans: 33
  completed_plans: 30
  percent: 10
---

# Project State

## Current Project

STOA backend.

See: .planning/PROJECT.md (updated 2026-07-14)

## Current Position

Phase: 473 (student-content-privacy-and-practice-integrity) — EXECUTING
Plan: 8 of 11 complete; next Plan 09
Status: Phase 473 gap closure in progress
Last activity: 2026-07-16 -- Plan 473-08 completed; opaque chunks and immutable-byte promotion are green

## Accumulated Context

- Phase 473 upload APIs now accept only authenticated opaque intents and exact bounded chunks; public responses contain no provider URL, key, multipart ID, ETag, VersionId, or provider name.
- Multipart part writes require a checksum/length-bound uploading claim and active fence before provider mutation; same-byte lost responses reconcile from matching server-listed parts while different bytes conflict first.
- Exact validated staging-version bytes are hashed and promoted from one bounded spool to a fresh server-only immutable version; OCR, extraction, association, release, purge, cleanup, and deletion use the full immutable tuple.

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
- Authorization audit HMAC keys now share one canonical decoded-byte contract across Settings, cache identity, and direct sink construction; production rejects weak, placeholder, malformed, colliding, or duplicate active/retained material without echoing secrets.
- Password recovery now always crosses the public provider boundary and exposes only one metadata-free initiation success or one structured invalid-proof recovery action, independent of account existence, role, or lifecycle state.
- All six final review findings pass together in 321 source-bound adversarial/positive controls; the extended Phase 472 gate passes 610 tests, while the full suite retains exactly 23 Phase 474-owned Settings fixture failures.
- Phase 473 implemented student upload ownership, durable attachment history/reuse, question OCR isolation, answer-free previews, attempt-gated results, and scoped privileged answer reads, but independent verification scored 68/100 (2/3 requirements and 15/22 decisions fully verified).
- Expired, invalid, and abandoned unconsumed upload cleanup now uses bounded versioned claims, consistent rechecks, resumable durable-reference scans, non-consumable retry tombstones, and coordinate-free summaries.
- The full suite reports 1232 passing tests, but verification found one critical mutable-object TOCTOU gap and five stable-error/redaction/replay gaps; real S3 POST behavior and deployed cleanup schedule/IaC remain explicitly NOT RUN.
- Plans 473-08 through 473-11 close those gaps through an authenticated chunk gateway, server-only immutable promotion, category-stable transaction outcomes, replayable conversation commands, private-safe telemetry, and one final source-bound evidence gate.

### Pending Todos

- Execute Phase 473 Plans 08-11 with `--gaps-only` before advancing to Phase 474.
- Preserve all 44 requirement mappings and all 31 finding assignments while phase plans are refined.
- Require approved sandbox or read-only evidence for external systems; do not fabricate live results or authorize production mutation through planning.

### Blockers/Concerns

- Phase 472's P0 authorization defects are locally closed; external rollout still requires the explicitly unavailable Cognito evidence and later v9 release gates.
- The direct main-to-Lambda workflow, red test baseline, and stale artifact/runtime state prevent a trustworthy release candidate today.
- Mobile native build/device verification cannot begin until Phase 477 repairs and locks the Expo dependency matrix.
- Authoritative IaC currently appears external to this repository and must be imported or cross-repository traced in Phase 479.
- Global `gsd progress` still scans 55 pre-v9 phase directories left in `.planning/phases/`; use `STATE.md` and `roadmap analyze` for v9 status until those historical records are safely archived rather than deleted.

## Operator Next Steps

- Run `$gsd-execute-phase 473 --gaps-only`; do not mark Phase 473 complete or approve external rollout until verification reruns as passed.
- Do not begin Phase 478 core mobile completion before Phases 473, 475, 476, and 477 satisfy their exit gates.

## Session

**Last Date:** 2026-07-16T15:37:55.000Z
**Stopped At:** Completed 473-08-PLAN.md; next 473-09
**Resume File:** .planning/phases/473-student-content-privacy-and-practice-integrity/473-09-PLAN.md

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
| Phase 472 P21 | 7 min | 2 tasks | 5 files |
| Phase 472 P20 | 2 min | 2 tasks | 7 files |
| Phase 472 P22 | 13 min | 3 tasks | 3 files |
| Phase 473 P01 | 9 min | 2 tasks | 7 files |
| Phase 473 P02 | 12 min | 3 tasks | 13 files |
| Phase 473 P05 | 17 min | 2 tasks | 12 files |
| Phase 473 P03 | 18 min | 2 tasks | 11 files |
| Phase 473 P04 | 14 min | 2 tasks | 9 files |
| Phase 473 P06 | 20 min | 2 tasks | 11 files |
| Phase 473 P07 | 16 min | 2 tasks | 7 files |
| Phase 473 P08 | 22 min | 2 tasks | 12 files |

## Decisions

- [Phase 473]: Client upload contracts expose only opaque intent/chunk state while staging keys, multipart IDs, ETags, versions, and provider identity remain server-only. — Direct storage capability disclosure is removed rather than reclassified.
- [Phase 473]: A checksum/length-bound uploading claim and fenced lease precede every provider part write; matching replays may adopt only server-listed matching evidence. — Lost responses converge without blind overwrite, and different bytes fail before mutation.
- [Phase 473]: Validation, SHA-256, and promotion share one bounded spool, and durable consumers use the promoted immutable key, VersionId, ETag, length, and checksum tuple. — Same-key replacement or newer versions cannot change OCR, extraction, association, or deletion targets.

- [Phase 473]: Cleanup claims only terminal or past-expiry unconsumed upload states, then consistently rechecks the claimed version before any provider delete. — Active, consuming, consumed, raced, and restored resources cannot enter deletion.
- [Phase 473]: Durable-reference discovery is bounded and resumable, and provider failure retains a non-consumable cleanup tombstone. — Cleanup retries are idempotent without deleting durable/reused history or reviving validated uploads.
- [Phase 473]: Local evidence binds commands and deterministic artifacts while real S3 and schedule/IaC checks remain NOT RUN; independent verification found that the evidence overclaims immutable-byte and redaction guarantees. — Gap closure must regenerate evidence from the remediated source.

- [Phase 473]: Curriculum answers use a dedicated READ purpose; admins receive only that narrow automatic read and teachers require one fresh current assignment matched against server-loaded challenge scope. — Answer access cannot broaden support or curriculum mutation authority.
- [Phase 473]: Missing, stale, disabled, unrelated, and wrong-scope teacher answer requests remain indistinguishable and only the explicit privileged route serializes pre-attempt answers. — Student previews and legacy includeAnswers input remain structurally answer-free.

- [Phase 473]: Conversation message persistence, fresh upload consumption, durable attachment creation, associations, and one aggregate new-byte charge share one conditional transaction. — Missing, foreign, invalid, duplicated, or over-quota member lists cannot leave partial history or storage effects.
- [Phase 473]: Saved attachment reuse increments only the durable reference count and adds a logical association. — Reuse preserves immutable bytes and leaves 5 GiB/15 GiB storage usage unchanged.
- [Phase 473]: Last-reference release creates a non-reusable deletion-pending tombstone before object deletion and quota finalization. — Provider or transaction retries cannot double-decrement usage or delete bytes still referenced elsewhere.
- [Phase 473]: Passive document extraction is bounded and public history retains safe attachment summaries; independent verification found broader AI/conversation logging paths that still expose content or provider exceptions. — Gap closure must enforce and test category-only logging end to end.

- [Phase 473]: Upload ownership is established only by the verified student Actor and a private intent record. — Client fields never establish owner or storage coordinates.
- [Phase 473]: Finalize validates HEAD metadata and bounded bytes, but later OCR/extraction reads are not bound to the recorded ETag or an immutable version. — Gap closure must pin every use to immutable validated bytes.
- [Phase 473]: First durable attachment transactions charge exact content length once; reuse has no storage mutation. — Quota remains authoritative without double-charging logical associations.
- [Phase 473]: Durable public attachment summaries expose opaque IDs and safe metadata, but presigned POST fields still reveal the generated storage key. — Gap closure must either remove that coordinate or explicitly narrow the contract/evidence.
- [Phase 473]: The attachment error registry is closed, but presign failures and transaction cancellations do not yet preserve the required stable dependency/quota semantics. — Gap closure must map every failure path to the structured contract.
- [Phase 473]: Answer-bearing practice results require a non-empty durable attempt receipt, while previews and hints use separate `extra="forbid"` allowlists. — Makes successful persistence the structural gate for answer reveal and prevents preview schema drift.

- [Phase 472]: Canonical authorization correlation IDs are generated server-side and never reuse an inbound header. — Prevents client-selected audit correlation and replay confusion.
- [Phase 472]: Audit rows and partition keys use keyed actor/resource fingerprints. — Raw student, owner, target, email, and key material must never persist.
- [Phase 472]: Relationship-sensitive and privileged allows are evidence-before-effect. — An audit outage cannot broaden access or permit sensitive effects.
- [Phase 472]: Public/global identifier-bearing commands require exact scoped declarations, while safe-public and protected identifiers require compatible executable specs. — One recursive projection now drives validation, checked JSON, and OpenAPI.
- [Phase 472]: Existing-account public registration resumes only after immutable command, issuer, subject, user ID, and role all match exactly. — Unproved provider accounts receive one safe recovery action before any authority mutation.
- [Phase 472]: Verification resend selects the local profile only by the immutable command user ID. — Email-index collisions cannot select or activate identity, and already-confirmed recovery must complete command-aware reconciliation.
- [Phase 472]: Reconciliation action identity is bound to the complete immutable grant coordinate. — Duplicate grant IDs across capabilities or scopes must produce distinct deterministic revoke/checkpoint operations.
- [Phase 472]: Account restoration never restores capability history. — Only a new manager-approved command and new grant identity may create a later active generation.
- [Phase 472]: Validated route-specific providers are the only source of administrator body-target authority. — Arbitrary JSON and evidence-only dictionaries never create scope; every concrete member is authorized and evidenced before effects.
- [Phase 472]: Authorization audit key identity is the normalized key ID plus canonically decoded bytes. — Settings, dependency caching, and direct sink construction must reject weak, ambiguous, or duplicate active/retained material before evidence effects.
- [Phase 472]: Public password recovery never consults the local email profile before provider normalization. — Account existence, role, lifecycle, and delivery metadata cannot select or alter the public initiation/reset projection.
- [Phase 472]: Final closure evidence is bound to tested source SHA, exact deterministic artifact digests, and the unmodified full-suite delta. — Local success must not absorb Phase 474/475 ownership or unavailable external checks.
- [Phase 472]: Multi-target bulk, recovery, handoff, and governance commands share one whole-command release invariant. — Every target must allow and persist redacted evidence before the first business effect, independent of input order.
- [Phase 473]: Student practice and curriculum previews use shared answer-free allowlists; includeAnswers never selects a student answer contract. — Prevents legacy and nested answer-derived response leaks.
- [Phase 473]: Every correct or incorrect practice answer persists an immutable owner attempt before result serialization. — A failed write cannot reveal the standard answer or explanation.
- [Phase 473]: Pre-submit hints require explicit approval and normalized answer/explanation guards. — Unsafe legacy or generated hints remain unavailable before submission.
- [Phase 473]: Question idempotency binds the original opaque upload or saved-attachment identity, never a bucket or object key. — A different attachment under the same key is rejected before quota, OCR, or attachment mutation.
- [Phase 473]: Fresh question image reservation precedes OCR and commits consumption, attachment, association, byte charge, and question in one transaction. — Foreign, missing, invalid, reused, raced, or failed attachment commands cannot leave partial attachment/question state.
- [Phase 473]: OCR accepts only a resolved internal active JPEG/PNG attachment and public questions retain safe summary metadata, but the provider read is not version/ETag-bound. — Ownership is enforced while immutable-byte integrity remains a verification gap.
