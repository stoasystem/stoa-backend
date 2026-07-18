---
phase: 473-student-content-privacy-and-practice-integrity
verified: 2026-07-18T17:03:21Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
requirements:
  passed: 3
  total: 3
  blocked: []
decision_coverage:
  honored: 22
  total: 22
  not_honored: []
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "Only one current deletion-command lease may mutate or finalize the durable 17-branch account-deletion proof"
    - "Every private notification, push, and realtime provider effect is owner/fence/lease bound or explicitly sealed global non-private data"
  gaps_remaining: []
  regressions: []
warnings:
  - id: profile-version-cas
    reason: "The deletion scrub checks a profile version, but ordinary profile-field mutations neither check nor advance that version; this can lose an unrelated concurrent profile update. It is a data-consistency defect, not a foreign-content or pre-submission-answer disclosure path."
  - id: delivery-begin-dependency-classification
    reason: "A nonconditional delivery-begin dependency failure is collapsed into AccountDeletionConflict and may be terminalized as canceled_account_deletion. This can suppress a valid delivery, but fails closed and does not expose private content."
  - id: completed-deletion-replay
    reason: "The minimized terminal command omits branch_ids/branch_contracts required by begin_or_replay_deletion, so a lost final DELETE response cannot replay its receipt. Deletion remains complete and fenced; the defect is idempotent receipt availability."
  - id: final-head-publication-reverification
    reason: "verify-publication still requires HEAD to be the publication commit's direct child. It fails at the final metadata HEAD, although the historical publication is the candidate's exact four-file child and all four artifacts remain byte-identical and hash-valid."
deferred:
  - truth: "Real S3 multipart, version, promotion, overwrite, and restart-recovery behavior is observed in an approved non-production environment"
    addressed_in: "Phase 479"
    evidence: "The checked evidence records P479-REAL-S3-MULTIPART-VERSIONING as NOT RUN."
  - truth: "The cleanup scheduler, retries, alarms, and IaC are deployed and observed"
    addressed_in: "Phase 480"
    evidence: "The checked evidence records P480-DEPLOYED-CLEANUP-SCHEDULER-IAC as NOT RUN."
  - truth: "Production/deployed log redaction is captured from the promoted artifact"
    addressed_in: "Phase 480"
    evidence: "The checked evidence records P480-PRODUCTION-LOGS as NOT RUN."
---

# Phase 473: Student Content Privacy And Practice Integrity Verification Report

**Phase Goal:** Ensure student uploads and exercise previews cannot expose another user's content or answers.
**Verified:** 2026-07-18T17:03:21Z
**Status:** `passed`
**Re-verification:** Yes — after Plans 473-36 through 473-40 and the final post-gap review
**Checked HEAD:** `87da123c92316b699756aa80a0cb29eb6addb6c9`

## Verdict

Phase 473 achieves its roadmap goal and satisfies V9PRIV-01, V9PRIV-02, and V9PRIV-03 in the local codebase. The two prior blockers are closed in production call chains: deletion work is fenced by explicit current time plus an opaque owner/version/digest claim, and private digest/push/WebSocket effects require a strongly loaded authoritative owner or an exact persisted sealed-global contract before the intent/fence begin transition.

The latest four review warnings are genuine and should be repaired, but none falsifies a Phase 473 success criterion or the three assigned requirements. They cause possible unrelated-profile lost updates, fail-closed notification suppression, inability to replay an already-completed deletion receipt, and inability to invoke the publication verifier from later metadata HEADs. None permits a foreign upload, bypasses file validation, leaks object/OCR/provider data, or returns an answer before a durable attempt.

Independent verification passed the focused 449-test privacy/lifecycle matrix and the complete 2,009-test repository suite. Both checked source inventories, targeted Ruff, and diff hygiene pass. No override was used.

## Goal Achievement

### Observable Truths

| # | ROADMAP observable truth | Status | Codebase evidence |
|---|---|---|---|
| 1 | A student can upload a supported bounded file and use it once in their own question. | ✓ VERIFIED | `UploadIntentResponse` exposes opaque gateway instructions only; `validate_uploaded_file` enforces extension/MIME/magic/container/size/image bounds; `reserve_question_attachment` requires an owner-resolved validated immutable JPEG/PNG; `commit_question_with_attachment` atomically writes question, association, consumption, and byte charge. Focused question/attachment tests pass. |
| 2 | Foreign, malformed, missing, expired, oversized, mismatched, and reused uploads are denied with stable redacted errors. | ✓ VERIFIED | Owner resolution and conditional states conceal foreign/missing/reused resources; `safe_attachment_error_body` emits only `code`, safe `message`, and server correlation ID; validation emits closed type/size/mismatch/invalid codes; cleanup keeps unusable state and exact provider debt until reconciled. Negative route and lower-bound tests pass. |
| 3 | No student preview/overview/path/lesson response contains answers or answer-derived explanation before submission. | ✓ VERIFIED | Student models are extra-forbid allowlists without answer fields; all preview builders copy only allowlisted data; hints are reviewed constant templates; recursive route/OpenAPI canaries pass. |
| 4 | Authorized teacher/admin tooling retains an explicit answer-bearing contract separate from the student contract. | ✓ VERIFIED | `PrivilegedPracticeAnswer` is a distinct response model behind `_curriculum_answer_read`; current assigned-teacher scope and narrow admin READ are enforced, while student/parent/anonymous/unassigned/stale scopes are concealed and mutation remains denied. |
| 5 | Existing question responses hide object keys and raw OCR text. | ✓ VERIFIED | Question output removes legacy `image_s3_key`, returns only safe attachment summaries/OCR metadata, and never projects stored `ocr_text`; public attachment models have no bucket/key/version/provider/extracted-content fields. Response and log canary tests pass. |

**Score:** 5/5 truths verified.

### Requirement Adjudication

| Requirement | Status | Evidence |
|---|---|---|
| V9PRIV-01 | ✓ SATISFIED | OCR receives only a server-resolved active owner image pinned to immutable promoted bytes. Fresh upload consumption, attachment creation, association, and question creation are one conditional transaction; foreign/missing/reused/non-image inputs fail before OCR or question effects. |
| V9PRIV-02 | ✓ SATISFIED | Supported extension/MIME/magic/container and byte/image bounds, 30-minute lifecycle, post-upload validation, stable redacted errors, exact provider-operation recovery, and unusable cleanup states are substantive and wired. The residual delivery warning suppresses on dependency ambiguity rather than exposing content and is outside the upload acceptance boundary. |
| V9PRIV-03 | ✓ SATISFIED | Overview/path/lesson/catalog/exercise previews are structurally answer-free. Both correct and incorrect attempts are immutably recorded before result construction; failed writes return an answer-free 503. |

No orphaned Phase 473 requirements were found. `.planning/REQUIREMENTS.md` maps exactly V9PRIV-01/02/03 to this phase.

## Prior Finding Closure

| Prior finding | Status | Independent adjudication |
|---|---|---|
| CR-01 — active deletion lease theft and stale branch/final writes | ✓ CLOSED | Claim takeover compares stored expiry to explicit `now_epoch`; scheduled and service paths carry `DeletionCommandClaim`; renewal, each branch result, and finalization condition owner, generation, command version, result digest, and current lease. Two-worker/stale-write/stale-finalizer tests pass. |
| CR-02 — missing owner-generation directly delivers private notification content | ✓ CLOSED | Digest, push, and WebSocket strongly load the persisted event, resolve a closed authoritative owner or exact sealed-global row, and execute only through a durable delivery begin. Missing/malformed/stale/mixed metadata produces zero lower provider calls in the focused matrix. |
| WR-01 (prior report) — blank production deletion timestamps | ✓ CLOSED | `AccountDeletionService` now defaults to timezone-aware UTC and repository lifecycle boundaries reject blank, naive, malformed, and non-string times. |
| WR-02 (prior report) — stale full-row parent scrub | ⚠ PARTIALLY CLOSED, NON-BLOCKING | The scrub now uses a row version and advances it, so a version-aware writer conflicts. Ordinary `user_repo.update_profile_fields`, however, does not advance that version; the original lost-update race remains for those writers. This is the latest review's profile-version warning. |
| WR-03 (prior report) — claimed delivery intent unrecoverable forever | ✓ CLOSED FOR ORIGINAL DEFECT | Expired `claimed_pre_effect` work is recoverable by explicit-time claim/version CAS; `effect_inflight` becomes provider-acceptance-unknown and is not blindly retried. The latest dependency-classification warning is a distinct error-mapping defect. |

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/stoa/models/attachment.py` and `attachment_errors.py` | Opaque coordinate-free contracts and stable redacted errors | ✓ VERIFIED | Substantive extra-forbid models and exhaustive error registry; imported by routers/services and exercised through public routes. |
| `file_validation_service.py`, `attachment_service.py`, `attachment_repo.py` | Bounded validation, immutable promotion, owner lifecycle, atomic association, recovery/cleanup | ✓ VERIFIED | Real validation/state/transaction logic, not stubs; upload, question, conversation, purge, and recovery callers are wired. |
| `questions.py` and OCR boundary | Owner-resolved image only, atomic question association, safe response | ✓ VERIFIED | Reservation precedes counter/OCR; unresolved input has zero downstream effects; atomic commit is used for attached questions. |
| Practice models/projection/repository/routes | Answer-free previews and durable-attempt result | ✓ VERIFIED | One typed projection family serves all student reads; result construction validates a complete immutable attempt snapshot. |
| Privileged answer authorization and route | Exact teacher/admin read without mutation | ✓ VERIFIED | Distinct response and authorization purpose; negative actor/scope matrix and OpenAPI contract pass. |
| Account-deletion claim/finalizer and private delivery services | No stale deletion proof or post-fence private provider effect | ✓ VERIFIED FOR PRIVACY GOAL | Former blocker paths are fenced and pass lower-bound matrices. Four residual non-disclosure warnings are documented below. |
| Boundary/private-store inventories | Deterministic source-sealed lower-bound coverage | ✓ VERIFIED | Both generators pass `--check`; 66 read boundaries, 232 writes, and the exact 17 deletion branches remain composed in checked evidence. |
| Immutable Plan 40 evidence publication | Candidate-bound receipts and hash-valid four-document publication | ⚠ VERIFIED HISTORICALLY / FINAL-HEAD CLI WARNING | Candidate `b43c71b...` has exact four-file child `5da6936...`; all three manifest artifacts rehash from that commit and are unchanged at current HEAD. The CLI cannot select that publication commit from current HEAD. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| authenticated upload intent | exact validated immutable bytes | fenced multipart ledger, bounded validation, checksum/version promotion | ✓ WIRED | No public storage coordinate; exact provider acknowledgements and recovery state are required. |
| owner upload/image | question and OCR | reservation followed by conditional question/attachment transaction | ✓ WIRED | Missing/foreign/reused/non-image fails before OCR and question persistence. |
| stored practice content | student preview | typed allowlist projection | ✓ WIRED | Answer fields cannot enter serialized preview models. |
| recorded attempt | answer-bearing result | immutable create receipt then `build_attempt_result` | ✓ WIRED | Failed persistence cannot construct or return the result. |
| teacher/admin request | privileged answer | exact assignment/admin READ dependency | ✓ WIRED | Separate from student routes and mutation policy. |
| deletion scanner | current branch worker/finalizer | explicit current time and opaque owner/version/digest claim | ✓ WIRED | Stale workers lose renewal, branch persistence, and finalization. |
| private event | email/push/WebSocket provider effect | strong event scope resolution then delivery-intent begin/fence | ✓ WIRED | Invalid scope has zero provider effects; no direct fallback remains. |

## Data-Flow Trace

| Artifact | Data | Source | Produces real data | Status |
|---|---|---|---|---|
| Question response | attachment summary and OCR metadata | owner-resolved immutable attachment plus committed question record | Yes; repository transaction and OCR adapter | ✓ FLOWING |
| Practice preview | challenge/lesson/exercise preview | curriculum/practice repositories through allowlist builders | Yes; source records projected without answer fields | ✓ FLOWING |
| Attempt result | standard answer/explanation/feedback | immutable owner attempt snapshot created before response | Yes; exact complete snapshot required | ✓ FLOWING |
| Privileged answer | answer/explanation/feedback | authorized challenge loaded once by central policy | Yes; explicit scoped source record | ✓ FLOWING |

## Behavioral Verification

| Check | Result | Status |
|---|---|---|
| Focused upload/question/practice/deletion/delivery/evidence matrix | `449 passed in 5.84s` | ✓ PASS |
| Complete repository pytest | `2009 passed in 69.97s` | ✓ PASS |
| Private-store and boundary inventory `--check` | Both passed | ✓ PASS |
| Targeted Ruff and `git diff --check` | `All checks passed` | ✓ PASS |
| Current-HEAD `verify-publication --candidate b43c71b...` | Exit 1: direct-child requirement | ⚠ WARNING |
| Historical publication artifact hashes | All manifest byte counts/SHA-256 values reproduce from commit `5da6936`; artifacts unchanged through HEAD | ✓ PASS |

### Probe Execution

No `probe-*.sh` path is declared by any of Plans 473-01 through 473-40, and no conventional Phase 473 shell probe exists. Probe execution is therefore not applicable; executable evidence uses pytest lower-bound selectors and deterministic inventory/evidence commands.

## Current Non-Blocking Warnings

### 1. Profile version CAS is not shared by ordinary writers

`scrub_parent_profile_child` uses a version-conditioned full-row replacement. `user_repo.update_profile_fields` performs an active-fence transaction but neither compares nor increments the profile version. A concurrent ordinary update can therefore be overwritten by a stale deletion scrub. This is a real data-consistency warning and means the prior profile-scrub warning is only partially closed. It does not authorize another user, expose a foreign resource, weaken upload validation, or reveal a practice answer.

### 2. Transient delivery-begin failure is mislabeled as deletion cancellation

`account_deletion_repo.transact` converts both conditional loss and nonconditional DynamoDB dependency failure into `AccountDeletionConflict`; `_delivery_conditional_loss` treats every instance as conditional. `run_delivery_intent` may then cancel a valid intent as `canceled_account_deletion`. The effect is fail-closed delivery suppression with an inaccurate terminal reason, not a provider call or private-content disclosure. It does not block V9PRIV-02's upload contract.

### 3. Completed deletion receipt cannot replay

The terminal command intentionally minimizes branch proof fields, but `begin_or_replay_deletion` still requires `branch_ids` and `branch_contracts`. A retry after a lost successful response receives a replay conflict instead of the stored `deleted` receipt. The permanent deleted fence and completed cleanup remain intact; this is an availability/idempotent-response defect rather than a privacy failure.

### 4. Publication verification is not callable from the final metadata HEAD

`verify-publication` requires clean `HEAD^ == candidate`. Current HEAD is two metadata commits after publication, so the documented command fails. Independent Git-blob checks still prove that `5da6936` is the candidate's single direct four-file child, its manifest hashes/byte counts reproduce, and those four files are byte-identical at current HEAD. This warning weakens tooling ergonomics and final-HEAD reproducibility, not the implementation or the historical evidence integrity.

## Anti-Patterns

No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, `PLACEHOLDER`, `NotImplementedError`, or equivalent debt marker appears in the nine source/script files changed after the last immutable candidate base. No project-local skill/rule overrides and no verification overrides exist.

The four warnings above are not hidden by the green suite: the current tests prove version-aware scrub cooperation, conditional delivery-begin loss, pre-effect crash recovery, and direct-child publication, but do not exercise ordinary unversioned profile mutation, nonconditional begin dependency failure, real terminal-row deletion replay, or later metadata commits. They should become focused regression tests in follow-up work.

## Deferred External Boundaries

Real S3 multipart/version behavior is explicitly owned by Phase 479. Deployed cleanup scheduler/IaC and production/deployed log capture are explicitly owned by Phase 480. ROADMAP provides clear, specific later-phase ownership, so these are informational deferred items and do not reduce the local Phase 473 score.

## Gaps Summary

No blocker remains against the Phase 473 goal or V9PRIV-01/02/03. The two prior blockers are closed, all five roadmap truths are observable in source and passing tests, and the local phase can proceed. The four warnings should remain visible follow-up work, especially the profile lost-update and delivery misclassification defects, but escalation is not required to decide whether the student upload/practice privacy goal was achieved.

---

_Verified: 2026-07-18T17:03:21Z_
_Verifier: Codex (gsd-verifier)_
