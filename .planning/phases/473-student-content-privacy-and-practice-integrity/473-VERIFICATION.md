---
phase: 473-student-content-privacy-and-practice-integrity
verified: 2026-07-16T18:29:15Z
status: gaps_found
score: 4/5 must-haves verified
requirements:
  passed: 2
  total: 3
decision_coverage:
  honored: 22
  total: 22
  not_honored: []
gaps:
  - id: CR-007
    severity: blocker
    requirement: V9PRIV-02
  - id: WR-007
    severity: warning
    requirement: V9PRIV-02
---

# Phase 473: Student Content Privacy And Practice Integrity Verification Report

**Phase Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.
**Verified:** 2026-07-16T18:29:15Z
**Status:** `gaps_found`

## Verdict

Phase 473 is not ready to close. The gap plans successfully close the prior CR-001 and WR-001 through WR-005 findings at their original sites, and the independent 301-test phase matrix plus 1,303-test full suite pass. However, actual-code tracing confirms the fresh review's CR-007: expired validated uploads can be marked `cleanup_complete` while their promoted immutable object is never deleted, and crash windows can leave completed staging or promoted objects without durable recovery coordinates. This violates D-09 and blocks V9PRIV-02.

WR-007 independently leaves some post-issuance repository outages as unstructured 500 responses rather than the required stable `upload_service_unavailable` response. WR-006 and WR-008 are real robustness defects but are not independently phase-goal blockers.

## Goal Achievement

### Observable Truths

The ROADMAP success criteria are the authoritative must-haves.

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | A student can upload a supported bounded file and use it once in their own question. | ✓ VERIFIED | Opaque intent/chunk/complete routes, owner resolution, immutable promotion, OCR version binding, and atomic question association are implemented; positive/negative controls pass in the 301-test matrix. |
| 2 | Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors and safely cleaned up. | ✗ FAILED | Denial and validation behavior is strong, but `cleanup_upload_intent` deletes only staging coordinates before marking completion; the immutable tuple is scanned but never deleted. Post-issuance repository outages also escape stable translation in several gateway paths. |
| 3 | Student preview/overview/path/lesson responses contain no correct answer or answer-derived explanation before submission. | ✓ VERIFIED | Typed allowlist projections and recursive route/OpenAPI tests pass; attempt results are constructed only after immutable attempt persistence. |
| 4 | Assigned teachers and admins retain a separate explicit answer-bearing read contract. | ✓ VERIFIED | Dedicated curriculum-answer resource/purpose and route enforce current teacher scope and narrow admin read while mutation remains denied. |
| 5 | Question responses hide storage coordinates and raw OCR text. | ✓ VERIFIED | Public request/response schemas use opaque attachment summaries; OCR receives an internal immutable version and public/log canary controls pass locally. |

**Score:** 4/5 truths verified.

### Required Artifacts

| Artifact | Status | Details |
|---|---|---|
| `src/stoa/models/attachment.py` and `src/stoa/security/attachment_errors.py` | ✓ SUBSTANTIVE + WIRED | Closed opaque upload/attachment schemas and exhaustive stable error/action registry are imported by routes/services. |
| `src/stoa/services/file_validation_service.py` | ✓ SUBSTANTIVE + WIRED | Bounded seekable validation enforces image/document type, size, magic/container and integrity constraints. |
| `src/stoa/db/repositories/attachment_repo.py` | ⚠ SUBSTANTIVE + WIRED, DEFECTIVE CLEANUP | Lifecycle, transaction and command primitives are wired, but cleanup eligibility omits `issuing`/`assembling`, and completion removes only staging fields. |
| `src/stoa/services/attachment_service.py` | ✗ BLOCKING DEFECT | Immutable validation/promotion and consumers are wired, but cleanup never deletes an unbound immutable version and provider-success/repository-write crash recovery is incomplete. |
| `src/stoa/jobs/upload_cleanup.py` | ⚠ WIRED TO INCOMPLETE SERVICE | Bounded and idempotent orchestration exists, but cannot recover or delete all bytes created by the new gateway. |
| `src/stoa/services/practice_projection_service.py`, practice models/repository/routes | ✓ SUBSTANTIVE + WIRED | Answer-free previews, durable attempts, result reads and scoped privileged answers are connected end to end. |
| Evidence, validation, manifest and route inventory | ⚠ EXISTS, STALE CLAIM | Digests and tested SHA are reproducible, but D-09/V9PRIV-02 PASS claims are contradicted by CR-007 and must be regenerated after repair. |

### Key Link Verification

| From | To | Status | Details |
|---|---|---|---|
| Chunk gateway | private multipart ledger | ✓ WIRED | Conditional checksum/length claim precedes provider part writes; replay/fencing tests pass. |
| Completed staging version | bounded validation and immutable promotion | ✓ WIRED | One exact staging version is read into one spool and that same stream is promoted. |
| Immutable tuple | OCR/extraction/question/conversation | ✓ WIRED | Consumers require key + VersionId + checksum/length; prior CR-001 is closed. |
| Expired validated intent | provider deletion | ✗ NOT WIRED | Cleanup scans immutable references but deletes only staging key/version, then marks the row complete. |
| Gateway dependency failures | stable public error adapter | ⚠ PARTIAL | Issuance is translated, but initial lookup, replay polling, part listing and assembly claim can raise raw repository failures. |
| Student preview | answer-free projection | ✓ WIRED | All student route families use typed projections without answer switches. |
| Attempt persistence | answer-bearing result | ✓ WIRED | Result creation follows successful immutable attempt write; foreign/random reads are concealed. |
| Privileged answer route | current assignment policy | ✓ WIRED | Server-loaded challenge scope feeds central policy; teacher mutation remains separate. |

## Requirements Coverage

| Requirement | Status | Adjudication |
|---|---|---|
| V9PRIV-01 | ✓ SATISFIED LOCALLY | Actor-owned opaque resources, immutable OCR inputs and atomic question association are implemented with zero-effect negative tests. |
| V9PRIV-02 | ✗ BLOCKED | Validation/type/size/lifecycle/error primitives exist, but safe failure cleanup is false for promoted immutable bytes and stable gateway dependency errors are incomplete. |
| V9PRIV-03 | ✓ SATISFIED LOCALLY | Student previews are structurally answer-free; durable attempts gate results; scoped teacher/admin reads are separate. |

**Coverage:** 2/3 requirements satisfied.

## Decision Adjudication

| Decisions | Status | Evidence |
|---|---|---|
| D-01–D-06 | ✓ VERIFIED | Locked formats, MIME/magic/container checks, 10/50 MiB limits, 4096 edge and 1,800-second expiry are implemented and tested. |
| D-07 | ⚠ VERIFIED WITH WR-006 DEBT | Exact conversation replay and one effect set are tested, but deterministic fresh attachment IDs passed by the command executor are overwritten in the callee. |
| D-08 | ✓ VERIFIED | Terminal validation failures invalidate; retryable dependency states do not revive invalid uploads. |
| D-09 | ✗ FAILED | Unbound promoted immutable bytes are not deleted; `issuing`/`assembling` crash states are not cleanup candidates. |
| D-10–D-15 | ✓ VERIFIED | Durable history, 5/15 GiB quota, no auto-deletion, saved reuse, Actor ownership, concealment and owner-visible expiry are present. |
| D-16 | ✗ FAILED IN PART | Stable categories exist, but post-issuance repository outages can bypass them and produce unstructured 500 responses. |
| D-17 | ✓ VERIFIED LOCALLY | Opaque APIs, version-bound consumers and private telemetry pass local canary tests; deployed-log capture remains later-phase evidence. |
| D-18–D-20 | ✓ VERIFIED | Attempt-before-reveal, directional hints and structurally separate preview/result contracts are enforced. |
| D-21–D-22 | ✓ VERIFIED | Assigned `teacher` and narrow admin positives pass; all unauthorized roles/scopes remain concealed. |

### Decision Coverage

The GSD translation-coverage handler reports **22/22 decisions honored by shipped artifacts**. Semantic verification still finds D-09 failed and D-16 partially failed; translation coverage is a non-blocking presence heuristic, not proof of correctness.

## Fresh Finding Re-adjudication

| Finding | Verdict | Impact |
|---|---|---|
| CR-001 | ✓ CLOSED | Exact validated bytes are promoted from one bounded spool and every durable consumer is version/checksum-bound. |
| WR-001 | ✓ CLOSED | Public upload contracts expose no provider URL, fields, key, bucket, multipart ID, ETag or version. |
| WR-002 | ✓ CLOSED LOCALLY | Closed telemetry excludes content/provider diagnostics in exercised AI/question/conversation paths. |
| WR-003 | ✓ CLOSED | Semantic transaction indices map quota, concealed resource and retryable dependency outcomes without raw cancellation diagnostics. |
| WR-004 | ✓ CLOSED AT ISSUANCE | Issuance failure is terminal/cleanup-safe and returns stable 503. WR-007 is a later-stage gateway gap. |
| WR-005 | ✓ SUBSTANTIALLY CLOSED | Stage A replay, atomic command/quota claim, deterministic messages and fenced AI completion converge duplicates. |
| CR-007 | ✗ BLOCKER CONFIRMED | Promoted immutable versions can survive expiry while cleanup reports complete; provider/database split windows lack durable recovery coordinates. |
| WR-006 | ⚠ WARNING CONFIRMED | `bind_message_attachments` shadows the supplied deterministic attachment-ID list with an empty output list, so fresh IDs become random. |
| WR-007 | ⚠ WARNING, REQUIREMENT IMPACT | Several gateway repository calls occur outside translation boundaries; route catches only `AttachmentDecisionError`. |
| WR-008 | ⚠ WARNING CONFIRMED | Exact-version provider bodies are read but not closed on success or failure paths, risking connection-pool exhaustion. |

## Behavioral Verification

| Check | Result | Detail |
|---|---|---|
| Phase 473 matrix | ✓ 301 passed | Independent run: 301 passed in 4.29s. |
| Full repository suite | ✓ 1,303 passed | Independent run: 1,303 passed in 34.70s. |
| Phase 472 regression | ✓ 636 passed | Fresh source-bound Plan 11 observation; command and digest recorded in evidence. |
| Schema drift | ✓ none | Orchestrator gate reports no schema drift. |
| Codebase drift | ✓ non-actionable | Orchestrator gate reports no actionable drift. |
| Test adequacy for cleanup | ✗ insufficient | Cleanup fixture contains staging coordinates only and asserts only staging deletion, so it cannot detect CR-007. |

Passing suites do not override the blocking source-proven lifecycle defect.

## Test Quality Audit

| Test area | Active | Skipped | Circular | Assertion level | Verdict |
|---|---:|---:|---:|---|---|
| Upload/gateway/attachment security | active | 0 | 0 | Behavioral/state/effect | Strong except cleanup fixture omits immutable tuple and crash boundaries. |
| Question OCR and association | active | 0 | 0 | Behavioral/zero-effect | Sufficient for V9PRIV-01. |
| Conversation replay/telemetry | active | 0 | 0 | Behavioral/concurrency/canary | Strong, but lacks exact deterministic fresh attachment-ID assertion. |
| Practice privacy and privileged answer | active | 0 | 0 | Recursive schema + behavioral authorization | Sufficient for V9PRIV-03. |

No disabled requirement tests or circular expected-value generators were found. The critical quality problem is a missing negative fixture, not a skipped or circular test.

## Anti-Patterns

No task TODO/FIXME/HACK or empty implementation was found in the requirement-linked production files. `conversations.py` retains an explicit “AI system is being set up” fallback; complete product-journey behavior is Phase 478-owned and it does not change this phase's privacy verdict.

## Human Verification

N/A for Phase 473 closure — this is a backend contract/foundation phase and the blocking defects are programmatically demonstrable.

External real-provider observations remain deferred evidence, not human acceptance gates for this phase:

| Deferred item | Owning phase | Reason |
|---|---|---|
| Real versioned S3 chunk/promotion/overwrite behavior | Phase 479 | Infrastructure defines/imports authoritative S3 policies, lifecycle and deployed resources. |
| Deployed cleanup scheduler/EventBridge/Lambda/IaC | Phase 479 | Deployment and scheduling are infrastructure acceptance. |
| Production/deployed log-redaction capture | Phase 480 | Observability and deployed-log evidence are explicitly Phase 480 scope. |

## Gaps Summary

### Critical gap: crash-safe immutable upload cleanup

- Persist fenced staging and immutable-promotion operation coordinates before provider mutations.
- Make expired or lease-stale `issuing`, `assembling`, and promotion states cleanup-eligible.
- Abort recorded multipart uploads and delete every exact unreferenced staging and immutable VersionId before `cleanup_complete`.
- Add restart tests at each provider-success/repository-write boundary and a validated-unbound fixture containing both tuples.

### Required robustness follow-ups

- Preserve deterministic fresh attachment IDs and assert exact durable keys after lost-response retry.
- Normalize repository/provider dependency failures across every gateway stage to the stable redacted 503 contract.
- Close exact-version object bodies in `finally` and test success/error closure.
- Regenerate evidence, validation and manifest after the source fixes; remove the current overclaim that D-09/V9PRIV-02 pass.

## Recommended Fix Plans

### 473-12-PLAN.md: Crash-safe immutable cleanup and recovery

1. Persist fenced provider-operation coordinates and cleanup leases before staging completion and immutable promotion.
2. Extend candidate/claim/finalize cleanup to all stale states and both exact object tuples.
3. Add restart/split-failure/validated-unbound/durable-reference tests and rerun the full lifecycle matrix.

### 473-13-PLAN.md: Gateway and replay robustness

1. Repair deterministic attachment-ID plumbing and add exact-key replay assertions.
2. Add exhaustive gateway dependency translation and provider-body closure.
3. Run route-level error injection, resource-closure tests, full regression, then regenerate source-bound evidence.

## Verification Metadata

**Verification approach:** Goal-backward against ROADMAP success criteria, with actual-code lifecycle tracing.
**Must-haves source:** ROADMAP success criteria (authoritative over PLAN frontmatter).
**Automated checks:** 301 focused and 1,303 full tests passed; one blocking source-proven lifecycle check failed.
**Human checks required:** 0.
**Report path:** `.planning/phases/473-student-content-privacy-and-practice-integrity/473-VERIFICATION.md`.

---
*Verified: 2026-07-16T18:29:15Z*
*Verifier: Codex GSD verifier subagent*
