---
gsd_state_version: 1.0
milestone: v9.0
milestone_name: milestone
status: executing
stopped_at: Phase 475 planned (13 atomic plans; ready for execution)
last_updated: "2026-07-21T21:12:09.163Z"
last_activity: 2026-07-20 -- Closed V9QUAL-01 and V9QUAL-02 with two admitted Linux PASS runs
progress:
  total_phases: 10
  completed_phases: 2
  total_plans: 156
  completed_plans: 94
  percent: 20
---

# Project State

## Current Project

STOA backend.

See: .planning/PROJECT.md (updated 2026-07-14)

## Current Position

Phase: 474 (Deterministic Verification And Gated Delivery) — EXECUTING
Plan: 94 of 94
Status: Plan 94 complete; Phase 474 remains open for other requirement gaps
Last activity: 2026-07-20 -- Closed V9QUAL-01 and V9QUAL-02 with two admitted Linux PASS runs

## Accumulated Context

- The checked private-store and boundary inventories now seal all Plan 36-38 source changes with independent semantic mutation guards, 232 exact write rows, 66 strict read rows, five lower-bound finding selectors, and the unchanged ordered 17 deletion branches.
- Every reviewed private mutation now maps to a deterministic source-sealed inventory row, narrow retained-evidence class, or one of four reviewed non-student exclusions; exact current-generation results for all 17 ordered branches, two zero epochs, zero blocking debt, and one same-table CAS are required to permanently terminalize deletion.
- Private notification broadcasts, assistance summaries, preferences, push credentials, WebSocket endpoints, and outbound delivery intents now share the permanent account fence; provider mutation rechecks immediately before effect, accepted/unknown external copies are not overclaimed, and the branch requires two later clean scans.
- Practice receipts/progress, adaptive assignments/memories, AI drafts, learning usage, and curriculum signals now share the permanent account fence; opaque owner manifests replace deterministic hashes, exact aggregate reversal is retry-safe, and five branches require two later clean scans.
- Conversation headers, messages, teacher-help state, commands, chat usage metadata, and attachment associations now share one permanent-fence generation; stale AI returns cannot complete, associations release before scrub, and two later clean strong scans prove quiescence.
- Report generation, artifact edits, and recovery delivery now use owner-partitioned exact object/email intents behind the permanent account fence; exact VersionId absence and explicit legal-retention debt govern report purge quiescence.
- Moderation summaries and events now derive one authoritative student/generation from the strong question read, every writer loses to the permanent account fence, owner-bound notification handoff is mandatory, and strong paginated scrubbing requires two later zero epochs.
- Phase 473 staging assembly and immutable promotion now persist exact pre-mutation coordinates behind expiring operation fences; bounded takeovers change both fence and row version so stale workers cannot record success.
- Upload cleanup persists exact multipart, staging-version, and immutable-version progress independently and cannot reach `cleanup_complete` until every marker is durable.
- Recovery and cleanup select only exact never-reused keys and exact VersionIds; durable references and mismatching/newer versions block destructive cleanup.
- Phase 473 upload APIs now accept only authenticated opaque intents and exact bounded chunks; public responses contain no provider URL, key, multipart ID, ETag, VersionId, or provider name.
- Multipart part writes require a checksum/length-bound uploading claim and active fence before provider mutation; same-byte lost responses reconcile from matching server-listed parts while different bytes conflict first.
- Exact validated staging-version bytes are hashed and promoted from one bounded spool to a fresh server-only immutable version; OCR, extraction, association, release, purge, cleanup, and deletion use the full immutable tuple.
- Conversation sends now use an exact versioned fingerprint, atomic command/chat-quota claim, deterministic effects, and a fenced expiring AI lease; regular and SSE retries replay one original result.
- AI, title, conversation, replay, and OCR-fed question logs now use closed category/class/size/count/correlation telemetry with cross-service private-canary coverage.
- Final checked evidence is bound to immutable candidate `b43c71bdebf948e1ced024e309af1cfd5b4d5b50`: 14 deletion-claim, 10 delivery-recovery, 12 private-delivery, 109 combined final-gap, 939 deep Phase 473, 455 inherited Phase 473, 636 Phase 472, and 2,009 full-suite nodes pass with exact receipts, five-finding lower-node coverage, reproducible hashes, and zero privacy matches. External S3, deployed cleanup/IaC, and production log capture remain NOT RUN.

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
- Plans 473-18 through 473-40 have executed the source-backed provider, replay, retention, parser, practice, permanent-account-fence, inventory, deletion/delivery race, and immutable-evidence closure. The last independent Phase 473 report predates Plans 36-40 and must be rerun before phase or requirement completion is accepted.

### Pending Todos

- Independently re-verify the complete Phase 473 aggregate before marking Phase 473 or V9PRIV-02 complete.
- Preserve all 44 requirement mappings and all 31 finding assignments while phase plans are refined.
- Require approved sandbox or read-only evidence for external systems; do not fabricate live results or authorize production mutation through planning.

### Blockers/Concerns

- Phase 472's P0 authorization defects are locally closed; external rollout still requires the explicitly unavailable Cognito evidence and later v9 release gates.
- The direct main-to-Lambda workflow, red test baseline, and stale artifact/runtime state prevent a trustworthy release candidate today.
- Mobile native build/device verification cannot begin until Phase 477 repairs and locks the Expo dependency matrix.
- Authoritative IaC currently appears external to this repository and must be imported or cross-repository traced in Phase 479.
- Global `gsd progress` still scans 55 pre-v9 phase directories left in `.planning/phases/`; use `STATE.md` and `roadmap analyze` for v9 status until those historical records are safely archived rather than deleted.

## Operator Next Steps

- Run the independent aggregate Phase 473 verification against publication `5da6936095c2b5647a8f992c280d371837f35b0f` before changing phase status.
- Do not begin Phase 478 core mobile completion before Phases 473, 475, 476, and 477 satisfy their exit gates.

## Session

**Last Date:** 2026-07-21T20:47:21.934Z
**Stopped At:** Phase 475 planned (13 atomic plans; ready for execution)
**Resume File:** .planning/phases/475-transactional-usage-assignment-and-relationship-consistency/475-01-PLAN.md

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
| Phase 473 P09 | 8 min | 2 tasks | 5 files |
| Phase 473 P10 | 21 min | 2 tasks | 10 files |
| Phase 473 P11 | 11 min | 2 tasks | 3 evidence files plus summary/tracking |
| Phase 473 P12 | 14 min | 2 tasks | 3 files |
| Phase 473 P13 | 36 min | 2 tasks | 6 files |
| Phase 473 P14 | 10 min | 2 tasks | 3 files |
| Phase 473 P15 | 15 min | 2 tasks | 5 files |
| Phase 473 P16 | 12 min | 2 tasks | 5 files |
| Phase 473 P17 | 8 min | 2 tasks | 4 files |
| Phase 473 P18 | 13 min | 3 tasks | 3 files |
| Phase 473 P25 | 14 min | 3 tasks | 9 files |
| Phase 473 P19 | 16 min | 3 tasks | 5 files |
| Phase 473 P26 | 15 min | 3 tasks | 6 files |
| Phase 473 P20 | 38 min | 3 tasks | 6 files |
| Phase 473 P24 | 24 min | 3 tasks | 7 files |
| Phase 473 P21 | 22 min | 3 tasks | 10 files |
| Phase 473 P22 | 13 min | 3 tasks | 4 files |
| Phase 473 P23 | 15 min | 3 tasks | 7 files |
| Phase 473 P29 | 33 min | 3 tasks | 27 files |
| Phase 473 P30 | 13 min | 3 tasks | 6 files |
| Phase 473 P31 | 13 min | 3 tasks | 13 files |
| Phase 473 P32 | 10 min | 3 tasks | 6 files |
| Phase 473 P33 | 19 min | 3 tasks | 14 files |
| Phase 473 P34 | 14 min | 3 tasks | 7 files |
| Phase 473 P35 | 27 min | 3 tasks | 9 files |
| Phase 473 P27 | 13min | 3 tasks | 3 files |
| Phase 473 P28 | 26min | 3 tasks | 11 files |
| Phase 473 P36 | 16min | 3 tasks | 6 files |
| Phase 473 P37 | 13min | 3 tasks | 4 files |
| Phase 473 P38 | 21min | 3 tasks | 6 files |
| Phase 473 P39 | 32min | 3 tasks | 6 files |
| Phase 473 P40 | 21min | 3 tasks | 6 files |
| Phase 474 P01 | 9 min | 1 tasks | 3 files |
| Phase 474 P02 | 12 min | 2 tasks | 3 files |
| Phase 474 P04 | 6 min | 1 tasks | 2 files |
| Phase 474 P03 | 18min | 2 tasks | 10 files |
| Phase 474 P06 | 15 min | 2 tasks | 5 files |
| Phase 474 P05 | 30min | 2 tasks | 7 files |
| Phase 474 P07 | 7 min | 1 tasks | 2 files |
| Phase 474 P39 | 12 min | 1 tasks | 5 files |
| Phase 474 P23 | 6 min | 1 tasks | 1 files |
| Phase 474 P08 | 16 min | 1 tasks | 4 files |
| Phase 474 P09 | 16m | 1 tasks | 4 files |
| Phase 474 P10 | 9 min | 1 tasks | 3 files |
| Phase 474 P40 | 7 min | 1 tasks | 3 files |
| Phase 474 P41 | 10 min | 1 tasks | 1 files |
| Phase 474 P42 | 6 min | 1 tasks | 2 files |
| Phase 474 P73 | 14 min | 1 task | 4 frontend files |
| Phase 474 P81 | 4 min | 1 task | 2 frontend files |
| Phase 474 P82 | 12 min | 1 task | 3 frontend files |
| Phase 474 P83 | 3 min | 1 task | 2 frontend files |
| Phase 474 P84 | 2 min | 1 task | 2 frontend files |
| Phase 474 P86 | 75 min | 1 task | 3 contract files plus summary |
| Phase 474 P87 | 115 min | 1 task | 4 frontend files plus summary |
| Phase 474 P26 | multi-session | 1 task | 5 infra files plus summary |
| Phase 474 P88 | multi-cycle | 1 task | 3 contract files plus summary |

## Decisions

- [Phase 473]: Command-derived fresh attachment IDs are immutable inputs with exact pre-effect cardinality checks; bound IDs use a separate output accumulator. — Lost and synchronized regular/SSE retries rebuild one identical durable attachment and association key set without consuming IDs for saved reuse.
- [Phase 473]: Typed conditional conflicts remain concealed while dependency, malformed response, and unknown provider-success persistence outcomes use one retryable upload_service_unavailable contract. — The public gateway preserves resource concealment without exposing repository/provider diagnostics through raw 500 responses.
- [Phase 473]: Validation and extraction bind one exact-version provider Body and close that same object in finally; close failure never replaces the stable primary outcome. — Deterministic connection release prevents pool exhaustion while preserving validation, parser, checksum, and dependency semantics.

- [Phase 473]: Conversation send identity is a domain-separated length-prefixed SHA-256 over exact UTF-8 content and ordered typed opaque attachment identities. — Exact replay survives consumed uploads while changed content, type, or order conflicts before attachment lookup.
- [Phase 473]: Message command creation, one quota-operation row, and the daily chat counter share one conditional transaction; deterministic messages and a fenced AI lease converge later effects. — Lost responses and synchronized regular/SSE duplicates cannot double-charge or create duplicate durable results.
- [Phase 473]: Private AI/content telemetry is limited to closed categories, exception class names, numeric sizes/counts, and server-owned correlation IDs. — Student, OCR, extracted, model, title, exception, coordinate, and provider values never become diagnostics.

- [Phase 473]: Client upload contracts expose only opaque intent/chunk state while staging keys, multipart IDs, ETags, versions, and provider identity remain server-only. — Direct storage capability disclosure is removed rather than reclassified.
- [Phase 473]: A checksum/length-bound uploading claim and fenced lease precede every provider part write; matching replays may adopt only server-listed matching evidence. — Lost responses converge without blind overwrite, and different bytes fail before mutation.
- [Phase 473]: Validation, SHA-256, and promotion share one bounded spool, and durable consumers use the promoted immutable key, VersionId, ETag, length, and checksum tuple. — Same-key replacement or newer versions cannot change OCR, extraction, association, or deletion targets.
- [Phase 473]: Only the named storage-quota transaction condition is externally distinguishable; every resource condition remains concealed and every conflict, throttle, malformed cancellation, or dependency failure becomes one redacted retryable outcome. — Stable recovery guidance cannot become an ownership, status, key, or provider diagnostic oracle.

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
- [Phase 473]: Evidence commits follow one immutable tested source candidate with exactly three narrative/manifest paths. — This keeps test observations source-bound, reproducible, and non-circular.
- [Phase 473]: Provider success coordinates must be nonblank strings before any lifecycle transition can remove a recovery fence; malformed success retains exact recovery identity. — Coercing malformed provider output could create false durable success and erase the only bounded restart-recovery fence.
- [Phase 473]: Unexpected candidate-local cleanup failures become coordinate-free retryable outcomes, while failure to list the global candidate page still propagates. — Per-item isolation preserves bounded progress without disguising a global scan failure or exposing private storage coordinates and diagnostics.
- [Phase 473]: Provider Body ownership begins immediately after a non-None Body is returned; read and close properties are each inspected inside best-effort boundaries so cleanup cannot replace the primary outcome. — Preserves stable validation and extraction semantics while deterministically releasing provider resources.
- [Phase 473]: Every conversation command repository call crosses one classifier; known semantic outcomes remain distinct while generic transport becomes a redacted bounded retry and ambiguous commits reread the original fingerprinted command. — Preserves concealment and exact replay while preventing raw repository transport failures and duplicate effects.
- [Phase 473]: The clean Plan 473-16 closeout SHA bc61107b920b158201ce4927485986d43aac59c8 is the immutable Phase 473 evidence candidate. — Source, tests, and the checked authorization inventory already reproduced without change, so an artificial empty candidate commit was unnecessary.
- [Phase 473]: External S3, deployed scheduler/IaC, and production/deployed log observations remain NOT RUN under Phases 479/480. — Local fakes and captured local logs cannot establish provider, deployed infrastructure, or production observability proof.
- [Phase 473]: Provider acknowledgements use exact non-coercive ETag, integer, canonical SHA-256, and pagination-marker parsers before conditional persistence. — Malformed provider success remains retryable and redacted instead of becoming durable ledger state.
- [Phase 473]: Immutable promotion is create-only and records success only after exact versioned byte and metadata verification; staging coordinates clear only after absence proof. — Crash recovery converges without overwriting, guessing, or erasing the last durable cleanup coordinate.
- [Phase 473]: Opaque challenge IDs resolve through one answer-free pointer to one exact content-addressed canonical row. — Malformed, missing, duplicated, or stale identity fails closed.
- [Phase 473]: Post-submit answer content is copied into one create-only owner receipt. — Every later result or mistake projection reads the receipt without consulting mutable curriculum content.
- [Phase 473]: Pre-submit hints emit only constant bytes from a closed parameter-free catalog. — Exact whole-content non-derivability decisions make reviewer provenance necessary but insufficient.
- [Phase 473]: Provider cleanup advances only after exact listed absence — Abort and delete acknowledgements are ambiguous; complete validated pagination must exclude the retained UploadId or VersionId.
- [Phase 473]: Operation lease expiry never shortens upload intent lifetime — Only terminal state or the original intent expiry authorizes destructive cleanup; short leases remain takeover fences.
- [Phase 473]: PART cleanup requires TTL plus explicit generation-fenced absence — PART rows inherit parent expiry, are scrubbed conditionally, and cleanup completes only after an empty page.
- [Phase 473]: Teacher curriculum-answer reads require both exact current course and exact current class; lesson, subject, and grade can only narrow that already-authorized scope. — Subject or grade overlap must never create pre-attempt answer authority.
- [Phase 473]: The current curriculum assignment is accepted only from its deterministic teacher key with canonical entity type, positive version, strict read-contract collections, and a fresh active teacher account. — Malformed, stale, or coerced facts must fail closed without broadening the one-role Actor contract.
- [Phase 473]: The privileged answer dependency validates one direct-resolver identity/version/hash/scope value and passes that same loaded value to the answer projection; admins retain only the narrow READ purpose. — One loaded object prevents authorization/projection TOCTOU and preserves read-only admin access.
- [Phase 473]: Message command claims persist exact quota, usage, request, attachment, message, and history identities so every retry reuses the same facts across midnight. — Retry-time reconstruction can drift or duplicate durable effects; persisted first-claim facts make replay deterministic.
- [Phase 473]: Message and attachment effects share one transaction with the usage-ledger event; deterministic pre-bind rejection compensates only that command's quota operation. — Usage cannot become a fallible post-effect, and compensation must never reverse another command's charge.
- [Phase 473]: Regular and SSE transports project the same validated typed command state, and only a live command may return message_in_progress. — One closed projection prevents transport-specific masking of rejected, terminal, expired, missing, or retryable durable states.
- [Phase 473]: OOXML admission and extraction share one canonical OPC graph and XML event parser. — Content types, exact main relationships, canonical members, and entity/external refusal establish semantic passive type before use.
- [Phase 473]: Document text crosses a spawn-isolated closed-result worker after exact immutable tuple revalidation. — CPU, memory, wall, input, output, and IPC fences prevent parser resource and diagnostic leakage into AI context.
- [Phase 473]: Conversation replay persists exact ordered history IDs and a canonical fingerprint. — Later messages are ignored, while missing or changed anchored rows remain retryable instead of drifting prompt context.
- [Phase 473]: Attachment replay accepts only one complete ordered owner-bound active immutable row set. — Exact entity/schema, key, version, ETag, checksum, length, and source validation prevents partial or foreign private context from reaching AI.
- [Phase 473]: AI work uses a 90-second deadline and lease-generation conditional completion. — Response cleanup, post-invocation renewal, and owner/attempt/expiry conditions prevent stale workers from freezing results after takeover.
- [Phase 473]: Strong base-table reads alone establish retention reference absence. — DynamoDB GSIs cannot provide strongly consistent absence proof.
- [Phase 473]: Every association transaction checks exact resource and account deletion fences. — Concurrent association creation cannot race exhaustive release or account purge.
- [Phase 473]: Exact VersionId absence precedes one atomic attachment and quota finalization. — Delete and finalize lost responses converge without double quota decrement.
- [Phase 473]: Immutable promotion persists staging cleanup debt before deletion. — Server-only staging coordinates remain durable until exact absence proof.
- [Phase 473]: Owner attachment routes authorize one authoritative loaded resource and conceal missing or foreign identifiers identically. — This prevents duplicate reads and identifier-existence leaks.
- [Phase 473]: Downloads verify the exact immutable object version before streaming and close the provider body on every path. — Clients never receive unverified bytes and provider connections remain bounded.
- [Phase 473]: Attachment purge reports typed independent progress under the existing account fence and cannot finalize that fence. — The later account purge orchestrator retains exclusive ownership of account-level completion.
- [Phase 473]: The permanent account fence is the only account-write truth; pending deletion never restores Actor authority and Plan 35 alone may terminalize it. — One permanent lifecycle row prevents mutable profiles or stale workers from reviving authority.
- [Phase 473]: Deletion replay resolves only an immutable issuer/subject command fingerprint and returns the same opaque receipt after identity rows are terminalized. — Post-fence retries must recover the committed command without recreating general application authority.
- [Phase 473]: Primary branch readiness requires two full clean strong-scan epochs; malformed, repeated, partial, or dirty progress remains retryable debt. — Filtered pages and eventually consistent indexes cannot prove private-row absence.
- [Phase 473]: Authoritative moderation ownership comes from the strongly read question; reporter, actor, and assignee identities never substitute for the student owner. — Every summary, event, writer fence, purge selector, and notification handoff uses one student lineage.
- [Phase 473]: Moderation summary and event rows use one strong base-table discovery pass with separately persisted family continuation coordinates. — This avoids GSI absence fiction while malformed or divergent restart state fails closed.
- [Phase 473]: Moderation tombstones retain only opaque row identities, lifecycle facts, timestamps, and privacy generation. — No content hashes, notes, contexts, changes, reporter identities, or actor pseudonyms survive account deletion.
- [Phase 473]: Report provider effects use owner-partitioned durable intents. — Each intent binds the exact permanent-fence generation, object key, body SHA-256, and length before mutation.
- [Phase 473]: Provider ambiguity never authorizes a blind retry. — Lost S3 responses require complete version-page metadata reconciliation; SES ambiguity becomes provider_acceptance_unknown.
- [Phase 473]: Legal-held report material remains blocking policy debt. — legal_retention_blocked rows have zero purge count and prevent branch quiescence without restoring access.
- [Phase 473]: Conversation rows, messages, notes, commands, chat operations, usage metadata, and attachment associations form one owner/generation deletion family. — One permanent owner/generation lineage makes private copies exhaustively drainable.
- [Phase 473]: Initial-message, regular, and SSE sends share the same command implementation and permanent-fence checkpoints. — Transport and creation variants cannot bypass command fencing.
- [Phase 473]: Bedrock request/response retention is outside backend deletion control; only backend durable copies are claimed scrubbed. — Deletion evidence must not overclaim provider-side erasure.
- [Phase 473]: Conversation quiescence requires association release, inactive commands, zero debt, and two later clean strong base-table scans. — A first empty or filtered page cannot prove durable absence.
- [Phase 473]: Student curriculum signals are globally anonymous and resolve to an account only through a same-transaction owner manifest under that account deletion partition.
- [Phase 473]: Signal deletion, aggregate decrement, owner-manifest removal, and an owner-free reconciliation receipt form one exact conditional transaction.
- [Phase 473]: Practice, assignments, memories, drafts, and curriculum signals each prove quiescence independently through item debt and two later clean scans.
- [Phase 473]: Notification ownership is an internal owner envelope; recipient role, actor identity, and recipient absence never establish or waive student ownership. — Private role broadcasts must resolve the same closing account as their authoritative target.
- [Phase 473]: Digest, push, and WebSocket effects claim one durable operation and recheck the exact active generation twice, including immediately before provider mutation. — A pre-deletion claim cannot authorize an outbound effect after the permanent fence changes.
- [Phase 473]: Provider accepted and acceptance-unknown outcomes retain only operation, channel, time, and status policy facts and are never reported as purged external copies. — Backend deletion cannot prove erasure from recipient or provider systems.
- [Phase 473]: Notification, assistance, preference, token, delivery-intent, and connection discovery uses strong base-table pagination and two later clean epochs. — A first empty or filtered page cannot prove quiescence.
- [Phase 473]: A checked JSON refresh cannot approve a mutation; every mutating source file is independently sealed by a reviewed source digest. — Digest regeneration must not bless an unreviewed private sink.
- [Phase 473]: The account deletion runtime registry is exactly 17 ordered branch IDs bound to handler, root, subfamily, generation, and inventory digest. — Missing, duplicated, stale, or smaller branch sets must fail closed.
- [Phase 473]: Only a same-table conditional command-and-fence transition can terminalize deletion, and replay preserves the permanent fence. — Prevents partial completion, resurrection, and duplicate terminal effects.
- [Phase 473]: Accepted, delivered, and acceptance-unknown external receipts remain minimized facts outside backend purge authority; pending work and legal holds block. — Backend completion must not overclaim provider/client erasure or lawful-retention absence.
- [Phase 473]: Plan 27 owns only the untrusted-read registry; Plan 35 remains the sole owner of private-write rows and is invoked semantically on every composed check. — Preserves single ownership while making the combined gate fail on write drift.
- [Phase 473]: Read authorization is per consumed field/body operation and always re-runs taint semantics. — Refreshing a source-symbol digest cannot bless raw response use.
- [Phase 473]: Runtime evidence is joined by exact pytest node and lower-fake target across regular, SSE, and all 17 deletion branches. — Collected high-level tests alone do not prove the declared lower boundary executed.
- [Phase 473]: A gate counts only when its exact argv, raw log, JUnit, node manifest, candidate state, hashes, counts, and privacy facts independently reproduce.
- [Phase 473]: Any Phase 473 capture or publication failure invalidates the observation set and requires a new immutable candidate plus a complete registry rerun.
- [Phase 473]: Real S3, deployed scheduler/IaC, and production logs remain exact NOT RUN obligations owned by Phases 479 and 480.
- [Phase 473]: Every deletion mutation carries one opaque owner/generation/version/digest claim; renewal happens before branch work and claim loss stops the worker immediately. — Stale workers must lose before any later provider or repository mutation.
- [Phase 473]: Each durable branch result advances its result version and command proof digest; terminalization reloads the exact current 17-branch set. — In-memory completion cannot substitute for the current durable proof.
- [Phase 473]: Legacy parent profiles receive a narrow version normalization and rescan; versioned profiles scrub under both account fences plus row-version CAS. — Concurrent active-parent fields must never be overwritten by a stale deletion scan.
- [Phase 473]: Only expired claimed_pre_effect delivery work may be taken over; effect_inflight is terminalized as provider_acceptance_unknown and never becomes claimable. — This separates safely recoverable worker crashes from ambiguous external effects.
- [Phase 473]: The final provider gate binds scope, payload, opaque lease owner, intent version, and the private account fence or sealed-global classification in one durable CAS. — Stale workers and classification drift cannot begin or finish an effect.
- [Phase 473]: Delivery replay exposes only provider-neutral closed statuses and never provider payloads or exceptions. — Ambiguity remains safe under D-16 and D-17.
- [Phase 473]: Provider delivery trusts only the strongly loaded persisted event — Caller owner, generation, recipient, actor, role, metadata, and booleans never broaden delivery scope.
- [Phase 473]: Ownerless delivery requires an immutable repository-sealed global row — The exact contract, payload allowlist, event version, and classification digest are rechecked in the begin transaction.
- [Phase 473]: WebSocket fanout uses one stable intent per canonical event and redacted connection identity — Every provider post has an independent crash-safe ambiguity boundary.
- [Phase 473]: Whole-file digest review and independent function-level semantic guards jointly prevent regenerated inventory from blessing weakened privacy races. — A checked JSON or digest refresh alone is not semantic approval.
- [Phase 473]: All five findings map to exact source fields, lower fakes, runtime nodes, and observed assertions over the unchanged 17-branch registry. — Final evidence must execute the declared lower boundary rather than a high-level mock.
- [Phase 473]: Final-gap evidence counts only exact observed runtime nodes joined to both checked finding registries and declared lower fakes. — Collection, source strings, or broad high-level tests cannot substitute for the reviewed boundary.
- [Phase 473]: V9PRIV-02 and D-10/D-16/D-17 retain checked inventory coverage and additionally require exact deletion, crash-recovery, and delivery-denial nodes. — Earlier coverage cannot mask a missing current concurrency or provider-effect observation.
- [Phase 473]: Candidate snapshots are recomputed from immutable candidate Git blobs. — A direct-child publication cannot change tested-source hashes or byte counts during post-commit capture verification.
- [Phase 474]: Remaining v9.0 work is Web-first across backend and /Users/zhdeng/stoa-frontend; every retained production route and student, parent, teacher, admin/operator journey must work or be intentionally disabled; native clients are deferred until Web testing is stable. — Owner product correction on 2026-07-18; Phase 474 CONTEXT and the 51-requirement roadmap are canonical.
- [Phase 474]: The owner's approval applies only to /Users/zhdeng/stoa-infra/.DS_Store; every other tracked or untracked path remains release-blocking. — A top-literal pathspec preserves fail-closed checking elsewhere.
- [Phase 474]: Candidate identity binds to the post-contract backend execution state feeda5524d65dfe1c624aaedc0bcc6353dcb9746 and the live frontend and infra states. — The receipt creation path is excluded from source porcelain to avoid circular dirt.
- [Phase 474]: The release CLI accepts only checked-in typed gate IDs; callers cannot supply an alternate argv graph. — One authoritative checked-in registry prevents local and CI command-graph drift.
- [Phase 474]: Canonical receipt SHA-256 binds every stable receipt field except the digest field itself. — Excluding only the digest avoids circular identity while preserving tamper evidence.
- [Phase 474]: Only complete PASS exits 0; policy rejection and exact NOT RUN exit 2, while unexpected execution failure exits 3. — Callers can distinguish policy denial from broken execution without treating unavailable work as passing.
- [Phase 474]: Phase 473 reverification accepts only explicit full lowercase candidate and publication commit SHAs; refs, abbreviations, branch names, and dirty drafts are rejected.
- [Phase 474]: The publication must have exactly one parent equal to the candidate, and current HEAD must descend from it with identical artifact blob OIDs and bytes.
- [Phase 474]: Publication artifact truth comes only from immutable Git objects; the mutable worktree is used solely for the fail-closed cleanliness check.
- [Phase 474]: Dependency acquisition precedes formal isolation; pytest receives no proxy or AWS credential paths and requires a proved OS network-none boundary. — This permits reviewed package acquisition without allowing the release test process or its children to escape hermetic execution.
- [Phase 474]: Hosts without a proved Linux network namespace emit exact NOT RUN with zero run counts and never fall back to plugin-only isolation. — A Python plugin cannot constrain arbitrary child processes, so unavailable OS isolation cannot count as PASS.
- [Phase 474]: Phase 473 AST source seals reproduce the existing reviewed Python 3.14 canonical bytes on Python 3.12 without regenerating evidence. — Interpreter-version defaults must not change mutation identity for identical source.
- [Phase 474]: Release ID binds only execution-receipted source, lock, and runtime identities; final manifest SHA-256 binds gates, artifacts, configs, and production NOT RUN. — This avoids circular pre-build identity while making final byte substitution detectable.
- [Phase 474]: Lambda promotion must consume the one normalized frozen-lock ZIP digest; staging or production may never rebuild it. — Build-once promotion is required by D-14.
- [Phase 474]: Untrusted identity and JWKS provider records remain object-valued mappings until authority-bearing fields are explicitly narrowed. — This keeps malformed provider input untrusted without Any, casts, or authorization broadening.
- [Phase 474]: Cached RS256 keys use python-jose's stable Key base while optional RSA construction fails closed when unavailable. — The maintained stub models RSAKey as an optional runtime-selected factory rather than a valid annotation.
- [Phase 474]: Dynamic FastAPI authorization metadata is attached through one typed helper while inventory consumers continue to validate the runtime metadata fail closed.
- [Phase 474]: Administrator provider values remain object-typed until explicit mapping, positive-integer, string-sequence, and authorization-context narrowing succeeds.
- [Phase 474]: Reconciliation collaborators expose only the mutation methods and exact grant coordinates required by the tightening workflow.
- [Phase 474]: All measured Web-root advisories were repaired with supported versions inside existing dependency ranges; no D-11 exception was created. — D-11 forbids exceptions while supported fixes exist.
- [Phase 474]: The frontend manifest remains unchanged while the authoritative lock records the repaired dependency graph. — Existing semver ranges already admit each patched version, so lock-only remediation preserves the public dependency contract.
- [Phase 474]: DynamoDB repository records remain object-valued until exact text, boolean, integer, mapping, and fingerprint checks establish safe use.
- [Phase 474]: Capability transaction variants use a closed TypedDict union and narrow runtime-checkable provider protocols without casts or broad Any.
- [Phase 474]: Malformed durable identity and capability state fails closed with stable coordinate-free repository errors instead of coercion.
- [Phase 474]: Keep DynamoDB records object-valued until exact runtime narrowing establishes safe use. — Prevents provider-originated values from becoming trusted through annotation alone.
- [Phase 474]: Use per-operation runtime Protocols for DynamoDB table capabilities. — Preserves minimal test fakes while validating only the method each path invokes.
- [Phase 474]: Validate and separate high-level attachment transaction descriptions from raw DynamoDB items. — Closes nested provider mappings without casts, ignores, or behavior changes.
- [Phase 474]: Curriculum and AI draft provider records remain object-valued until exact mapping, string, integer, list, and cursor checks establish safe use. — This preserves provider input as untrusted without restoring Any.
- [Phase 474]: Each DynamoDB path validates only the get, put, query, scan, update, or tombstone capability it invokes. — Operation-specific Protocols preserve minimal focused fakes while checking the actual capability used.
- [Phase 474]: Malformed curriculum and AI provider data fails through stable redacted repository errors. — Fail-closed validation preserves account fences, transaction identity, privacy, and pagination semantics.
- [Phase 474]: Privileged lifecycle repositories validate only the DynamoDB operation each path invokes and keep provider responses object-valued until string-keyed mapping checks pass.
- [Phase 474]: Malformed privileged and audit provider responses fail through stable repository exceptions without exposing coordinates or restoring broad typing.
- [Phase 474]: The unavailable authorization-audit sink retains its no-argument fail-closed diagnostic probe while accepting object-valued keyword inputs.
- [Phase 474]: Report persistence keeps the central table object-valued and narrows only the operation used by each path. — Operation-specific Protocols preserve central diagnostics and least-capability test fakes.
- [Phase 474]: Provider mappings and collections are validated before report lifecycle decisions. — Malformed pagination, recovery, retention, and deletion inputs fail through stable redacted conflicts.
- [Phase 474]: Opaque report pagination tokens retain the exact Invalid pagination token contract. — Decoded JSON is narrowed to string-keyed records without changing the public recovery behavior.
- [Phase 474]: DynamoDB notification and connection responses remain object-valued until runtime narrowing establishes safe use. — String-keyed mapping, item-list, cursor, text, and integer checks prevent provider values from becoming trusted through annotation alone.
- [Phase 474]: Notification and WebSocket paths validate only the table capability each operation invokes. — Operation-specific Protocols preserve least-capability test fakes and validate the actual provider boundary.
- [Phase 474]: Malformed notification and WebSocket provider responses use stable redacted conflicts. — Delivery identity, account fences, pagination behavior, and coordinate privacy remain unchanged.
- [Phase 474]: The served-release descriptor binds stable runtime-config.json and index.html service keys to exact S3 VersionIds and SHA-256 values, while caller-owned expected origin remains the trust root. — This preserves Plan 72's exact runtime-config path, avoids descriptor self-identity cycles, and rejects descriptor-controlled origin substitution.
- [Phase 474]: Existing Web environment exports project only the installed validated runtime registry; staging-pilot remains API-mode-compatible with staging and every mock, demo, MSW, debug, preview, and fallback surface is fixed false. — This removes compile-time release truth without breaking current consumers or taking ownership of startup and service policy.
- [Phase 474]: The browser statically imports only its startup barrier, then installs descriptor-bound runtime config before dynamically importing i18n, React, App, routes, API, or auth code. — Timeout, failure, and duplicate attempts render one fixed actionable message and cannot begin another App/root sequence.
- [Phase 474]: The backend workflow revision owns the gate implementation SHA and invokes only candidate then fixed formal after exact three-repository identity and Linux namespace proof. — A new caller cannot execute an older gate, select an alternate graph, or retain direct deployment authority.
- [Phase 474]: Frontend automation is a generic exact-ref verifier, not a release authority; Plan 93 must machine-bind one external three-repository tuple before Plan 94 may admit any receipt. — This keeps historical exact verification useful without letting a self-selected backend gate approve itself.
- [Phase 474]: Infra automation is the same generic exact-ref verifier with infra_sha bound to its workflow revision and no OIDC/CDK/provider authority. — Repository automation now verifies source only; external tuple admission remains separate and mandatory.
- [Phase 474]: The owner-approved handoff records only implementation B/F/I; the direct metadata publication remains an external trust input and Plan 94 candidates must use P/F/I. — This avoids self-reference while preventing any generic caller from selecting release evidence.
- [Phase 474]: A source handoff is not admissible after a failed real formal attempt; the failed publication is superseded only after fixing the exact materialized-snapshot path and issuing a new direct metadata child. — V9QUAL completion counts only the replacement source's later PASS receipts.
- [Phase 474]: Both historical handoff publications are rejected because their Python children exposed distinct snapshot-root assumptions; only the post-2344-pass implementation may be republished and counted. — Real Linux failures remain evidence, never PASS credit.
- [Phase 474]: Final publication fe467c5e4bdcce55863f62a0e7ffe26ca2c88ca0 produced two sequential complete Linux formal PASS receipts with distinct raw identities and one identical retained semantic digest. — V9QUAL-01 and V9QUAL-02 are now closed without claiming production execution.
